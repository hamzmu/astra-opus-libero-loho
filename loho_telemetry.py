"""Durable API-attempt accounting; missing usage never means zero cost."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import time
import uuid
from loho_scoring import FINISHED_REASONS

DEFAULT_PRICING = Path(__file__).resolve().parent / "pricing.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def validate_pricing(pricing):
    if pricing.get("currency") != "USD" or not isinstance(pricing.get("model"), str):
        raise ValueError("Pricing must specify a model and USD currency")
    threshold = token_count(pricing.get("long_context_threshold"))
    if threshold is None or threshold == 0:
        raise ValueError("Pricing must specify a positive long-context threshold")
    tiers = pricing.get("rates_per_million_tokens")
    if not isinstance(tiers, dict) or "default" not in tiers:
        raise ValueError("Pricing must include default service-tier rates")
    for tier in tiers.values():
        for band in ("short", "long"):
            for kind in ("input", "cached_input", "cache_write", "output"):
                value = tier[band][kind]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Pricing rates must be finite nonnegative numbers")
                rate = Decimal(str(value))
                if not rate.is_finite() or rate < 0:
                    raise ValueError("Pricing rates must be finite nonnegative numbers")


def price_attempt(attempt, pricing):
    usage = attempt.get("usage")
    if not isinstance(usage, dict):
        return None, "usage_missing"
    input_tokens = token_count(usage.get("input_tokens"))
    output_tokens = token_count(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None, "usage_incomplete"
    details = usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    cached = token_count(details.get("cached_tokens"))
    written = token_count(details.get("cache_write_tokens"))
    if input_tokens == 0:
        cached, written = 0, 0
    if cached is None or written is None:
        return None, "cache_usage_missing"
    if cached + written > input_tokens:
        return None, "invalid_cache_counts"
    model = attempt.get("returned_model") or attempt.get("requested_model")
    if model != pricing["model"] and not str(model).startswith(pricing["model"] + "-"):
        return None, "model_pricing_missing"
    tier = attempt.get("returned_service_tier") or attempt.get("requested_service_tier")
    tier = "priority" if tier == "fast" else tier
    tier_rates = pricing["rates_per_million_tokens"].get(tier)
    if tier_rates is None:
        return None, "tier_pricing_missing"
    rates = tier_rates["long" if input_tokens > pricing["long_context_threshold"] else "short"]
    ordinary = input_tokens - cached - written
    total = sum(Decimal(count) * Decimal(str(rates[kind])) for count, kind in [
        (ordinary, "input"), (cached, "cached_input"),
        (written, "cache_write"), (output_tokens, "output"),
    ]) / Decimal(1000000)
    return float(total), "priced"


def summarize_attempts(attempts):
    input_tokens = output_tokens = cached_tokens = write_tokens = 0
    unknown_usage = unresolved_cost = 0
    known_cost = Decimal(0)
    latencies = []
    for attempt in attempts:
        usage = attempt.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        incoming = token_count(usage.get("input_tokens"))
        outgoing = token_count(usage.get("output_tokens"))
        input_tokens += incoming or 0
        output_tokens += outgoing or 0
        if incoming is None or outgoing is None:
            unknown_usage += 1
        details = usage.get("input_tokens_details")
        details = details if isinstance(details, dict) else {}
        cached_tokens += token_count(details.get("cached_tokens")) or 0
        write_tokens += token_count(details.get("cache_write_tokens")) or 0
        cost = attempt.get("estimated_api_cost_usd")
        if cost is None:
            unresolved_cost += 1
        else:
            known_cost += Decimal(str(cost))
        if attempt.get("api_latency_seconds") is not None:
            latencies.append(attempt["api_latency_seconds"])
    return {
        "api_attempts_total": len(attempts),
        "known_api_attempts_total": len(attempts),
        "attempt_coverage_complete": True,
        "api_attempts_unknown_usage": unknown_usage,
        "api_attempts_unresolved_cost": unresolved_cost,
        "token_totals_complete": unknown_usage == 0,
        "total_input_tokens": input_tokens, "total_output_tokens": output_tokens,
        "total_cached_input_tokens": cached_tokens, "total_cache_write_tokens": write_tokens,
        "known_estimated_api_cost_usd": float(known_cost),
        "estimated_api_cost_usd": float(known_cost) if unresolved_cost == 0 else None,
        "cost_complete": unresolved_cost == 0,
        "total_api_latency_seconds": sum(latencies),
        "mean_api_latency_seconds": sum(latencies) / len(latencies) if latencies else None,
        "api_latency_totals_complete": len(latencies) == len(attempts),
    }


class AttemptLedger:
    def __init__(self, path=None, context=None, pricing=None, on_change=None):
        self.path = Path(path) if path is not None else None
        self.context = context or {}
        self.pricing = pricing or json.loads(DEFAULT_PRICING.read_text(encoding="utf-8"))
        validate_pricing(self.pricing)
        self.on_change = on_change
        self.run_id = str(uuid.uuid4())
        self.attempts = []
        self._starts = {}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size:
                raise FileExistsError("API ledger already exists; choose a fresh --outdir")
        self._append({"event": "run_started", "run_id": self.run_id,
                      "time_utc": utc_now(), "context": self.context, "pricing": self.pricing})

    def _append(self, event):
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def _emit(self, attempt, event):
        cost, status = price_attempt(attempt, self.pricing)
        attempt.update(estimated_api_cost_usd=cost, cost_status=status)
        self._append({"event": event, "time_utc": utc_now(), "attempt": dict(attempt)})
        if self.on_change is not None:
            self.on_change()

    def begin(self, decision_index, model, service_tier, **request_fields):
        attempt = {"attempt_id": str(uuid.uuid4()), "run_id": self.run_id,
                   "decision_index": decision_index, "started_at_utc": utc_now(),
                   "requested_model": model, "requested_service_tier": service_tier,
                   "returned_model": None, "returned_service_tier": None,
                   "request_id": None, "response_id": None, "http_status": None,
                   "response_status": None, "usage": None,
                   "api_latency_seconds": None, "outcome": "pending", **self.context,
                   **request_fields}
        self.attempts.append(attempt)
        self._starts[attempt["attempt_id"]] = time.monotonic()
        self._emit(attempt, "request_started")
        return attempt

    def update(self, attempt, event, **fields):
        attempt.update(fields)
        self._emit(attempt, event)

    def elapsed(self, attempt):
        return time.monotonic() - self._starts[attempt["attempt_id"]]


def read_attempt_journal(path):
    """Replay latest snapshots; a truncated last write stays unresolved."""
    attempts = {}
    pricing = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "run_started":
            pricing = event.get("pricing")
        if "attempt" in event:
            attempt = event["attempt"]
            attempts[attempt["attempt_id"]] = attempt
    return list(attempts.values()), pricing


def aggregate_episode_reports(reports):
    groups = {}
    for report in reports:
        if "model_id" not in report or report.get("runtime", {}).get("test"):
            continue
        key = (report["model_id"], report.get("observation_mode", "rgb"), report["task_id"],
               report.get("prompt_profile", "legacy-v1"), report.get("camera_configuration", "agentview"),
               json.dumps(report.get("camera_orientations", {"agentview": report.get("orientation", "rotate180")}), sort_keys=True),
               report.get("action_interface", "normalized_osc_delta"), report.get("effort", "high"),
               report.get("control_hz", 20), report.get("max_decisions"), report.get("max_action_steps"),
               report.get("image_history_observations", 2), report.get("max_output_tokens_per_call"),
               report.get("effort_fallback"))
        group = groups.setdefault(key, {"model_id": key[0], "observation_mode": key[1],
            "task_id": key[2], "prompt_profile": key[3], "camera_configuration": key[4],
            "camera_orientations": json.loads(key[5]), "action_interface": key[6], "effort": key[7],
            "control_hz": key[8], "max_decisions": key[9], "max_action_steps": key[10],
            "image_history_observations": key[11], "max_output_tokens_per_call": key[12], "effort_fallback": key[13],
            "episodes": 0, "successful_episodes": 0,
            "error_episodes": 0, "completed_episodes": 0, "unresolved_cost_episodes": 0,
            "known_estimated_api_cost_usd": 0, "total_input_tokens": 0,
            "total_output_tokens": 0, "total_api_latency_seconds": 0,
            "total_episode_elapsed_seconds": 0, "api_attempts_total": 0,
            "known_api_attempts_total": 0, "attempt_coverage_complete": True,
            "token_totals_complete": True, "api_latency_totals_complete": True,
            "termination_reasons": {}, "scored_episodes": 0, "unscored_episodes": 0,
            "goal_completion_percent_sum": 0, "peak_goal_completion_percent_sum": 0,
            "scored_finished_episodes": 0, "finished_goal_completion_percent_sum": 0})
        group["episodes"] += 1
        group["successful_episodes"] += int(report.get("success") is True)
        reason = report.get("termination_reason", "unknown")
        group["error_episodes"] += int(reason in ("error", "interrupted", "running", "tool_errors"))
        group["completed_episodes"] += int(reason in FINISHED_REASONS)
        score = report.get("trial_score", {})
        if score.get("available") is True and isinstance(score.get("completion_percent"), (int, float)):
            group["scored_episodes"] += 1
            group["goal_completion_percent_sum"] += score["completion_percent"]
            group["peak_goal_completion_percent_sum"] += score["peak_simultaneous_completion_percent"]
            if reason in FINISHED_REASONS:
                group["scored_finished_episodes"] += 1
                group["finished_goal_completion_percent_sum"] += score["completion_percent"]
        else:
            group["unscored_episodes"] += 1
        group["termination_reasons"][reason] = group["termination_reasons"].get(reason, 0) + 1
        group["unresolved_cost_episodes"] += int(report.get("cost_complete") is not True)
        group["known_api_attempts_total"] += report.get("known_api_attempts_total", report.get("api_attempts_total") or 0)
        group["attempt_coverage_complete"] &= report.get("attempt_coverage_complete", report.get("api_attempts_total") is not None)
        group["token_totals_complete"] &= report.get("token_totals_complete") is True
        group["api_latency_totals_complete"] &= report.get("api_latency_totals_complete") is True
        for name in ["known_estimated_api_cost_usd", "total_input_tokens", "total_output_tokens",
                     "total_api_latency_seconds", "api_attempts_total"]:
            group[name] += report.get(name) or 0
        group["total_episode_elapsed_seconds"] += report.get("elapsed_seconds") or 0
    for group in groups.values():
        group["cost_complete"] = group["unresolved_cost_episodes"] == 0
        group["estimated_api_cost_usd"] = group["known_estimated_api_cost_usd"] if group["cost_complete"] else None
        group["success_rate"] = group["successful_episodes"] / group["episodes"]
        group["full_task_completions"] = group["successful_episodes"]
        group["task_completion_rate"] = group["success_rate"]
        group["finished_trials"] = group["completed_episodes"]
        goal_sum = group.pop("goal_completion_percent_sum")
        peak_sum = group.pop("peak_goal_completion_percent_sum")
        finished_sum = group.pop("finished_goal_completion_percent_sum")
        group["mean_goal_completion_percent"] = (goal_sum / group["scored_episodes"]
                                                  if group["scored_episodes"] else None)
        group["mean_peak_goal_completion_percent"] = (peak_sum / group["scored_episodes"]
                                                       if group["scored_episodes"] else None)
        group["mean_goal_completion_percent_finished_trials"] = (
            finished_sum / group["scored_finished_episodes"]
            if group["scored_finished_episodes"] else None)
        group["success_rate_completed_episodes"] = (group["successful_episodes"] / group["completed_episodes"]
                                                    if group["completed_episodes"] else None)
        if not group["attempt_coverage_complete"]:
            group["api_attempts_total"] = None
    return sorted(groups.values(), key=lambda item: (item["model_id"], item["observation_mode"], item["task_id"], item["prompt_profile"], item["camera_configuration"], json.dumps(item["camera_orientations"], sort_keys=True), item["action_interface"], item["effort"], item["control_hz"], item["max_decisions"] or 0, item["max_action_steps"] or 0))

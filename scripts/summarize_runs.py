"""Aggregate API cost, request latency, and success by model/observation/task."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
from loho_telemetry import aggregate_episode_reports, read_attempt_journal, summarize_attempts
from loho_scoring import trial_status

parser = argparse.ArgumentParser(description=__doc__)
default_root = workspace / "loho_runs"
parser.add_argument("--root", type=Path, default=default_root,
                    help="Run directory; the default also includes results/ and loho-study/.")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
reports = []
sources = []
seen_runs = set()
roots = [args.root]
if args.root.resolve() == default_root.resolve():
    roots.append(workspace / "results")
    roots.append(workspace / "loho-study")
summary_paths = sorted({path for root in roots if root.exists()
                        for path in root.rglob("summary.json")})
for path in summary_paths:
    report = json.loads(path.read_text(encoding="utf-8"))
    if "model_id" not in report or report.get("runtime", {}).get("test"):
        continue
    run_id = report.get("run_id")
    if run_id is not None and run_id in seen_runs:
        continue
    if run_id is not None:
        seen_runs.add(run_id)
    journal = path.parent / report.get("api_attempts_file", "api_attempts.jsonl")
    if journal.exists():
        attempts, _ = read_attempt_journal(journal)
        report.update(summarize_attempts(attempts))
    else:
        # Historical traces have incomplete attempt coverage; don't assign zero cost.
        report["cost_complete"] = False
        report["known_estimated_api_cost_usd"] = 0
        report["api_attempts_total"] = None
        report["known_api_attempts_total"] = len(report.get("decisions", []))
        report["attempt_coverage_complete"] = False
        report["total_api_latency_seconds"] = sum(d.get("api_latency_seconds", 0) for d in report.get("decisions", []))
    score_file = path.parent / "trial_score.json"
    if "trial_score" not in report and score_file.exists():
        replay = json.loads(score_file.read_text(encoding="utf-8"))
        if (replay.get("replay_verified") is True and replay.get("source_run_id") == report.get("run_id")
                and replay.get("source_summary_sha256") == hashlib.sha256(path.read_bytes()).hexdigest()):
            report["trial_score"] = replay["trial_score"]
    report["trial_status"] = trial_status(report.get("termination_reason", "unknown"))
    reports.append(report)
    sources.append(str(path))
trials = [{"summary_file": path, "model_id": report["model_id"], "task_id": report["task_id"],
           "prompt_profile": report.get("prompt_profile", "legacy-v1"),
           "policy": report.get("policy", "direct"),
           "action_interface": report.get("action_interface", "normalized_osc_delta"),
           "effort": report.get("effort", "high"), "control_hz": report.get("control_hz", 20),
           "max_decisions": report.get("max_decisions"), "max_action_steps": report.get("max_action_steps"),
           "max_estimated_api_cost_usd": report.get("max_estimated_api_cost_usd"),
           "cost_guard_enabled": report.get("cost_guard_enabled", report.get("max_estimated_api_cost_usd") is not None),
           "provider": report.get("provider", "openai"),
           "image_history_observations": report.get("image_history_observations", 2),
           "max_output_tokens_per_call": report.get("max_output_tokens_per_call"),
           "effective_effort": report.get("effective_effort", report.get("effort", "high")),
           "effort_fallback": report.get("effort_fallback"),
           "observation_mode": report.get("observation_mode", "rgb"),
           "camera_configuration": report.get("camera_configuration", "agentview"),
           "cameras": report.get("cameras", [report.get("camera", "agentview")]),
           "camera_orientations": report.get("camera_orientations", {"agentview": report.get("orientation", "rotate180")}),
           "trial_status": report["trial_status"], "task_complete": report.get("success"),
           "termination_reason": report.get("termination_reason"),
           "trial_score": report.get("trial_score", {"available": False, "completion_percent": None}),
           "executed_actions": len(report.get("decisions", [])),
           "elapsed_seconds": report.get("elapsed_seconds"),
           "estimated_api_cost_usd": report.get("estimated_api_cost_usd"),
           "known_estimated_api_cost_usd": report.get("known_estimated_api_cost_usd"),
           "cost_complete": report.get("cost_complete")}
          for path, report in zip(sources, reports)]
budget_cohorts = {}
for report in reports:
    cap = report.get("max_estimated_api_cost_usd")
    guard = report.get("cost_guard_enabled", cap is not None)
    budget_cohorts.setdefault((guard, cap), []).append(report)
groups = []
for (guard, cap), episodes in budget_cohorts.items():
    cohort = aggregate_episode_reports(episodes)
    for group in cohort:
        group.update(cost_guard_enabled=guard, max_estimated_api_cost_usd=cap)
    groups.extend(cohort)
result = {"groups": groups, "episode_summaries": sources, "trials": trials,
          "note": "Groups separate spending-guard/cap policies as well as robot/model settings. USD estimates use recorded public rates. Unknown usage and legacy coverage remain unresolved."}
receipt_path = args.root / "removed_run_costs.json"
receipts = json.loads(receipt_path.read_text(encoding="utf-8-sig"))["receipts"] if receipt_path.exists() else []
receipts = [receipt for receipt in receipts if receipt["run_id"] not in seen_runs]
result["removed_run_cost_receipts"] = receipts
result["spending_accounting"] = {
    "retained_known_estimated_api_cost_usd": sum(report.get("known_estimated_api_cost_usd", 0) or 0 for report in reports),
    "removed_known_estimated_api_cost_usd": sum(receipt["known_estimated_api_cost_usd"] for receipt in receipts),
    "all_known_estimated_api_cost_usd": sum(report.get("known_estimated_api_cost_usd", 0) or 0 for report in reports) + sum(receipt["known_estimated_api_cost_usd"] for receipt in receipts),
    "cost_complete": all(report.get("cost_complete") for report in reports) and all(receipt["cost_complete"] for receipt in receipts),
    "note": "Removing result artifacts does not remove already incurred charges. Financial receipts are separate from retained trial scores."
}
output = args.output or args.root / "task_metrics.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
score_output = output.with_name("trial_scores.json")
score_output.write_text(json.dumps({"trials": trials}, indent=2, allow_nan=False), encoding="utf-8")
print("Saved {} task groups from {} episodes to {}".format(len(result["groups"]), len(reports), output))
for trial in trials:
    score = trial["trial_score"].get("completion_percent")
    print("{} task {}: goal_completion={}%, task_complete={}, status={}".format(
        trial["model_id"], trial["task_id"], score, trial["task_complete"], trial["trial_status"]))

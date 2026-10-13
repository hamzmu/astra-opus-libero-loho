"""Record an existing Opus/Astra pose-tools trial, verify artifacts, and make no API calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import cv2

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
from loho_frontier_eval import write_json
from loho_telemetry import read_attempt_journal, summarize_attempts


def record_trial(directory, reference, model="opus"):
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8-sig"))
    baseline = json.loads((reference / "summary.json").read_text(encoding="utf-8-sig"))
    if report["termination_reason"] == "running":
        raise ValueError("Wait until the trial has stopped before recording it.")
    attempts, _ = read_attempt_journal(directory / "api_attempts.jsonl")
    fields = ("model_id", "provider", "task_id", "initial_state_id", "sim_seed", "policy",
              "prompt_profile", "context_mode", "effort", "effort_fallback", "control_hz",
              "max_decisions", "max_action_steps", "max_estimated_api_cost_usd",
              "max_output_tokens_per_call", "max_speed_fraction", "rgb_resolution", "cameras",
              "camera_orientations", "image_history_observations", "image_history_mode",
              "simulator_horizon", "system_prompt", "workspace_bounds", "start_grasp_site_rotation_xyzw")
    model_id, provider, fallback, label = {
        "opus": ("claude-opus-5-5", "anthropic", None, "OPUS 5.5 MAX"),
        "astra": ("gpt-6-astra", "openai", "xhigh", "GPT-6 ASTRA MAX"),
    }[model]
    expected = {field: baseline.get(field) for field in fields}
    expected.update(model_id=model_id, provider=provider, effort_fallback=fallback)
    budget_policy_change = None
    if report.get("cost_guard_enabled") is False:
        expected["max_estimated_api_cost_usd"] = None
    if report.get("cost_guard_enabled") is False and baseline.get("max_estimated_api_cost_usd") is not None:
        budget_policy_change = {
            "reason": "Spending guard removed for new trials; historical limits are retained in the reference.",
            "reference_max_estimated_api_cost_usd": baseline.get("max_estimated_api_cost_usd"),
            "trial_max_estimated_api_cost_usd": None}
    configuration = {field: report.get(field) == expected.get(field) for field in fields}
    for field in ("revision", "versions", "render_backend"):
        configuration["runtime_" + field] = report["runtime"].get(field) == baseline["runtime"].get(field)
    if attempts:
        configuration["initial_camera_hashes_match"] = (
            attempts[0].get("image_jpeg_sha256_by_camera") == baseline["api_attempts"][0].get("image_jpeg_sha256_by_camera"))
        configuration["initial_proprioception_matches"] = (
            json.loads(attempts[0]["input_text"])["robot_proprioception"] ==
            json.loads(baseline["api_attempts"][0]["input_text"])["robot_proprioception"])
    reference_link = Path(os.path.relpath(reference, directory)).as_posix()
    write_json(directory / "configuration_verification.json", {
        "configuration_verified": all(configuration.values()), "reference_trial": reference_link,
        "checks": configuration, "expected": {field: value for field, value in expected.items() if field != "system_prompt"},
        "model_differences": {"model_id": model_id, "provider": provider, "effort_fallback": fallback},
        "budget_policy_change": budget_policy_change})
    steps = report["simulator_action_steps"]
    video_results = {}
    checks = {"configuration": all(configuration.values()),
              "calls_accounted": report["decisions_used"] == len(attempts) == report["api_attempts_total"],
              "steps_accounted": steps == len(report["executed_actions"]) == sum(d["executed_steps"] for d in report["decisions"]),
              "goal_score_consistent": report["success"] == report["trial_score"]["task_complete"] ==
                  all(goal["satisfied"] for goal in report["trial_score"]["goals"]),
              "budgets_respected": len(attempts) <= report["max_decisions"] and steps <= report["max_action_steps"],
              "all_calls_expected_model": all(a["requested_model"] == model_id for a in attempts),
              "effort_matches_requested_policy": all(a.get("reasoning_effort") == "max" or
                  (model == "astra" and a.get("reasoning_effort") == "xhigh" and
                   any(event.get("to_effort") == "xhigh" and event.get("from_effort") == "max"
                       for event in report.get("fallback_events", []))) for a in attempts)}
    telemetry = summarize_attempts(attempts)
    checks["cost_accounting_matches_journal"] = all(report.get(field) == telemetry.get(field) for field in (
        "known_estimated_api_cost_usd", "estimated_api_cost_usd", "cost_complete",
        "total_input_tokens", "total_output_tokens", "api_attempts_total"))
    for camera, filename in report["video_files"].items():
        capture = cv2.VideoCapture(str(directory / filename))
        if not capture.isOpened():
            raise ValueError("Cannot decode " + filename)
        fps, count, sizes = capture.get(cv2.CAP_PROP_FPS), 0, set()
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            count += 1
            sizes.add((frame.shape[1], frame.shape[0]))
        capture.release()
        checks["video_" + camera] = count == steps + 1 and fps == report["control_hz"] and sizes == {tuple(report["rgb_resolution"])}
        video_results[camera] = {"file": filename, "decoded_frames": count, "fps": fps,
                                 "frame_sizes": [list(size) for size in sorted(sizes)]}
    write_json(directory / "run_verification.json", {
        "passed": all(checks.values()), "checks": checks, "video_verification": video_results,
        "summary_sha256": hashlib.sha256((directory / "summary.json").read_bytes()).hexdigest(),
        "note": "Verifies recording and accounting integrity; task success is reported separately."})
    result_fields = ("run_id", "model_id", "provider", "task_id", "initial_state_id", "sim_seed", "policy",
                     "action_interface", "prompt_profile", "context_mode", "image_history_observations",
                     "media_mode", "png_frames_saved", "final_video_frames",
                     "image_history_mode", "cameras", "camera_configuration", "camera_orientations",
                     "rgb_resolution", "observation_mode", "effort", "effective_effort", "effort_fallback",
                     "fallback_events", "control_hz", "max_speed_fraction", "max_decisions", "max_action_steps",
                     "max_output_tokens_per_call", "max_estimated_api_cost_usd", "termination_reason",
                     "trial_status", "success", "trial_score", "decisions_used", "simulator_action_steps",
                     "elapsed_seconds", "mean_api_latency_seconds", "total_api_latency_seconds",
                     "estimated_api_cost_usd", "known_estimated_api_cost_usd", "cost_complete", "api_attempts_total",
                     "total_input_tokens", "total_output_tokens", "total_cached_input_tokens", "total_cache_write_tokens", "tool_error_count")
    result = {field: report.get(field) for field in result_fields}
    for field in ("cost_guard_enabled", "next_request_cost_reservation_usd", "unresolved_request_cost_reservation_usd"):
        if field in report:
            result[field] = report[field]
    result["budget_policy_change"] = budget_policy_change
    motions = [d for d in report["decisions"] if d.get("tool_name") == "move_to" and "tool_arguments" in d]
    result.update(local_runner_running=False, automatic_retries=0, verification_passed=all(checks.values()),
                  video_verification=video_results,
                  api_errors=sum(a.get("outcome") not in ("valid_tool_call", "invalid_tool_call", "tool_rejected") for a in attempts),
                  pose_targets_reached=sum(d.get("tool_result", {}).get("pose_target_reached") is True for d in motions),
                  pose_targets_not_reached=sum(d.get("tool_result", {}).get("pose_target_reached") is False for d in motions),
                  total_thinking_tokens_reported=sum((a.get("usage") or {}).get("output_tokens_details", {}).get("reasoning_tokens", 0) or 0 for a in attempts)
                      if model == "astra" else sum(a.get("raw_usage", {}).get("output_tokens_details", {}).get("thinking_tokens", 0) or 0 for a in attempts),
                  max_effort_requests=sum(a.get("reasoning_effort") == "max" for a in attempts),
                  xhigh_effort_requests=sum(a.get("reasoning_effort") == "xhigh" for a in attempts),
                  reference_trial=reference_link)
    if "error" in report:
        result["error"] = report["error"]
    write_json(directory / "run_result.json", result)
    (directory / "system_prompt.txt").write_text(report["system_prompt"] + "\n", encoding="utf-8")
    lines = [label + " TASK {} - RECORDED TRIAL".format(report["task_id"]), "",
             "Task: " + report["goal"],
             "State 0, seed 0; fresh conversation; no prior-run hindsight.",
             "Configuration verified against reference: {}; budget policy change: {}.".format(
                 all(configuration.values()), "spending guard removed" if budget_policy_change else "none"),
             "Termination: {}; simulator-verified completion: {}%; success: {}.".format(
                 report["termination_reason"], report["trial_score"]["completion_percent"], report["success"]),
             "Calls: {}; action steps: {}; settling steps: {}.".format(len(attempts), steps, report["settle_steps"]),
             "Elapsed: {:.3f}s; API latency total: {:.3f}s; mean: {:.3f}s.".format(
                 report["elapsed_seconds"], report["total_api_latency_seconds"], report["mean_api_latency_seconds"] or 0),
             "Estimated USD: {}; known USD: {}; complete cost: {}.".format(
                 report["estimated_api_cost_usd"], report["known_estimated_api_cost_usd"], report["cost_complete"]),
             "Limits: {} calls, {} steps, {} output tokens/call, {}.".format(
                 report["max_decisions"], report["max_action_steps"], report["max_output_tokens_per_call"],
                 "no spending cap" if report["max_estimated_api_cost_usd"] is None else
                 "${} estimated USD".format(report["max_estimated_api_cost_usd"])),
             "No automatic HTTP retries. All received usage, including failed responses, is retained.",
             "Requested effort: max; effective effort: {}; explicit effort fallback events: {}.".format(
                 report["effective_effort"], len(report.get("fallback_events", []))),
             "Model notes below are narration; scores come from private simulator goal predicates.",
             "", "EXECUTED TOOLS AND MEASURED RESULTS"]
    for decision in report["decisions"]:
        lines.extend(["Call {:02d}: {} {}".format(decision["decision_index"], decision.get("tool_name", "invalid"),
                       json.dumps(decision.get("tool_arguments", {}), ensure_ascii=False)),
                      "  Note: " + decision.get("memory", ""),
                      "  Executed steps: " + str(decision["executed_steps"]),
                      "  Result: " + json.dumps(decision.get("tool_result", {}), ensure_ascii=False)])
    (directory / "STEPS_TAKEN.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise ValueError("Verification failed: " + ", ".join(key for key, passed in checks.items() if not passed))
    print(json.dumps({"run": directory.name, "verified": True, "success": report["success"],
                      "completion_percent": report["trial_score"]["completion_percent"],
                      "cost_usd": report["estimated_api_cost_usd"], "calls": len(attempts), "steps": steps}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model", choices=["opus", "astra"], default="opus")
    parser.add_argument("--reference", type=Path, default=workspace / "loho-study" / "task 0" / "opus55_task0_max_128k_20261011_125617")
    args = parser.parse_args()
    record_trial(args.directory.resolve(), args.reference.resolve(), args.model)

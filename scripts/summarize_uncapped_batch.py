"""Verify and summarize one or more uncapped trial batches; no API access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
from loho_frontier_eval import write_json
from loho_telemetry import read_attempt_journal, summarize_attempts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="+")
    args = parser.parse_args()
    manifest_paths = [path.resolve() for path in args.manifest]
    manifest_path = manifest_paths[-1]
    root = manifest_path.parent
    manifests = [json.loads(path.read_text(encoding="utf-8-sig")) for path in manifest_paths]
    if any(path.parent != root for path in manifest_paths) or any(batch["status"] != "complete" for batch in manifests):
        raise ValueError("All selected batches must be complete and stored in the same results folder")
    manifest = dict(manifests[-1])
    task_id = manifest["task_id"]
    if any(batch["task_id"] != task_id for batch in manifests):
        raise ValueError("Cannot combine different task IDs")
    manifest["runs"] = [entry for batch in manifests for entry in batch["runs"]]
    if len(manifests) > 1:
        manifest["batch_id"] += "_combined"
    if not manifest["runs"]:
        raise ValueError("Expected nonzero trial counts")
    total_trials = len(manifest["runs"])
    trial_counts = {model: sum(entry["model"] == model for entry in manifest["runs"])
                    for model in ("opus", "astra")}
    if any(count == 0 for count in trial_counts.values()):
        raise ValueError("Select manifests containing both comparison models")
    per_model = trial_counts["opus"] if len(set(trial_counts.values())) == 1 else None
    if len({entry["directory"] for entry in manifest["runs"]}) != total_trials:
        raise ValueError("Duplicate run directories in selected batches")
    profiles = {"opus": "claude-opus-5-5", "astra": "gpt-6-astra"}
    trials = []
    for entry in manifest["runs"]:
        directory = root / entry["directory"]
        report = json.loads((directory / "summary.json").read_text(encoding="utf-8-sig"))
        result = json.loads((directory / "run_result.json").read_text(encoding="utf-8-sig"))
        verification = json.loads((directory / "run_verification.json").read_text())
        assert entry["status"] == "complete" and result["verification_passed"] and verification["passed"]
        assert verification["summary_sha256"] == hashlib.sha256((directory / "summary.json").read_bytes()).hexdigest()
        assert report["cost_guard_enabled"] is False and report["max_estimated_api_cost_usd"] is None
        assert report["max_decisions"] == 80 and report["max_action_steps"] == 2000
        assert report["max_output_tokens_per_call"] == 128000 and report["image_history_observations"] == 0
        assert report["model_id"] == profiles[entry["model"]] and report["effort"] == "max"
        assert report["task_id"] == task_id and report["initial_state_id"] == report["sim_seed"] == 0
        assert report["cameras"] == ["agentview", "robot0_eye_in_hand"]
        assert report["termination_reason"] not in ("cost_budget", "cost_unresolved", "running")
        assert all("cost_reservation" not in key for key in report)
        attempts, _ = read_attempt_journal(directory / "api_attempts.jsonl")
        telemetry = summarize_attempts(attempts)
        assert telemetry["api_attempts_total"] == report["decisions_used"] <= 80
        assert all(all("cost_reservation" not in key for key in attempt) for attempt in attempts)
        assert all(report.get(field) == telemetry.get(field) for field in (
            "estimated_api_cost_usd", "known_estimated_api_cost_usd", "cost_complete",
            "total_input_tokens", "total_output_tokens", "api_attempts_total"))
        for camera, metadata in verification["video_verification"].items():
            assert (directory / metadata["file"]).is_file()
            assert metadata["decoded_frames"] == report["simulator_action_steps"] + 1
            assert metadata["fps"] == 10 and metadata["frame_sizes"] == [[224, 224]]
        assert len(verification["video_verification"]) == 2
        trials.append(dict(entry, model_id=report["model_id"], success=report["success"],
            completion_percent=report["trial_score"]["completion_percent"],
            goals_satisfied=report["trial_score"]["goals_satisfied"],
            goals_total=report["trial_score"]["goals_total"],
            unsatisfied_goals=[goal["label"] for goal in report["trial_score"]["goals"]
                               if not goal["satisfied"]],
            peak_completion_percent=report["trial_score"].get("peak_simultaneous_completion_percent"),
            calls=report["decisions_used"], action_steps=report["simulator_action_steps"],
            termination_reason=report["termination_reason"],
            estimated_api_cost_usd=report["estimated_api_cost_usd"],
            known_estimated_api_cost_usd=report["known_estimated_api_cost_usd"],
            cost_complete=report["cost_complete"], elapsed_seconds=report["elapsed_seconds"],
            total_api_latency_seconds=report["total_api_latency_seconds"],
            mean_api_latency_seconds=report["mean_api_latency_seconds"],
            total_input_tokens=report["total_input_tokens"], total_output_tokens=report["total_output_tokens"],
            total_cached_input_tokens=report["total_cached_input_tokens"],
            total_cache_write_tokens=report["total_cache_write_tokens"],
            fallback_events=report["fallback_events"], api_errors=result["api_errors"],
            tool_error_count=report["tool_error_count"], video_verification=verification["video_verification"],
            summary_sha256=verification["summary_sha256"]))
    trials.sort(key=lambda trial: (0 if trial["model"] == "opus" else 1, trial["trial"]))
    models = []
    for model, model_id in profiles.items():
        episodes = [trial for trial in trials if trial["model"] == model]
        model_trials = len(episodes)
        trial_suffix = {3: "three", 5: "five", 6: "six"}.get(model_trials, str(model_trials)) + "_trials"
        assert sorted(trial["trial"] for trial in episodes) == list(range(1, model_trials + 1))
        calls = sum(trial["calls"] for trial in episodes)
        latency = sum(trial["total_api_latency_seconds"] for trial in episodes)
        complete = all(trial["cost_complete"] for trial in episodes)
        known = round(sum(trial["known_estimated_api_cost_usd"] for trial in episodes), 10)
        aggregate = {"model_id": model_id, "trials": model_trials,
            "successes": sum(trial["success"] for trial in episodes),
            "success_rate_percent": sum(trial["success"] for trial in episodes) / model_trials * 100,
            "mean_goal_completion_percent": sum(trial["completion_percent"] for trial in episodes) / model_trials,
            "api_calls": calls, "action_steps": sum(trial["action_steps"] for trial in episodes),
            "cost_complete": complete, "known_estimated_api_cost_usd": known,
            "estimated_api_cost_usd": known if complete else None,
            "total_api_latency_seconds": latency, "weighted_mean_api_latency_seconds": latency / calls if calls else None,
            "total_elapsed_seconds": sum(trial["elapsed_seconds"] for trial in episodes),
            "max_effort_requests": sum(trial["max_effort_requests"] for trial in episodes),
            "xhigh_effort_requests": sum(trial["xhigh_effort_requests"] for trial in episodes),
            "api_errors": sum(trial["api_errors"] for trial in episodes),
            "tool_errors": sum(trial["tool_error_count"] for trial in episodes),
            "episodes": episodes}
        write_json(root / (manifest["batch_id"] + "_" + model + "_" + trial_suffix + ".json"), aggregate)
        models.append(aggregate)
    complete = all(trial["cost_complete"] for trial in trials)
    known = round(sum(trial["known_estimated_api_cost_usd"] for trial in trials), 10)
    comparison = {"batch_id": manifest["batch_id"], "configuration_verified": True,
        "collection_kind": manifest.get("collection_kind", "all_selected_batches"),
        "task_id": task_id, "initial_state_id": 0, "sim_seed": 0, "cost_guard_enabled": False,
        "task_instruction": manifest.get("goal"),
        "limits_per_trial": {"max_calls": 80, "max_action_steps": 2000,
                             "max_output_tokens_per_call": 128000, "estimated_api_cost_cap_usd": None},
        "models": models, "all_trial_costs_complete": complete, "trials_per_model": per_model,
        "trial_counts_by_model": trial_counts,
        "known_estimated_api_cost_usd": known, "estimated_api_cost_usd": known if complete else None,
        "videos_verified": total_trials * 2, "source_sha256_by_batch": {batch["batch_id"]: batch["source_sha256"] for batch in manifests},
        "source_manifests": [path.name for path in manifest_paths],
        "media_mode": "video_only", "standalone_pngs_retained": False,
        "note": "Fresh independent conversations on one stored task state. Public-rate estimates use actual reported cache usage. Provider caches are not forcibly cleared between trials. Historical capped episodes and their startup attempts are separate. Standalone PNGs were removed from older trials; later trials save only camera MP4s and frame references. Control, prompt, observation and budget settings are unchanged."}
    write_json(root / (manifest["batch_id"] + "_comparison.json"), comparison)
    lines = ["# Task {} comparison without a spending guard".format(task_id), "",
        "{} retained Opus 5.5 max and {} retained GPT-6 Astra max trials, each using state 0 and seed 0.".format(trial_counts["opus"], trial_counts["astra"]) if manifest.get("collection_kind") == "retained_runs" else
        "{} fresh Opus 5.5 max and {} GPT-6 Astra max trials, each using state 0 and seed 0.".format(trial_counts["opus"], trial_counts["astra"]), "",
        "Each episode had limits of 80 model calls and 2000 action steps, with static plus wrist cameras, RGB + proprioception, "
        "absolute pose tools, append-only conversation/images, 10 Hz, 224x224 and 128000 output tokens per call. "
        "No dollar cap or request reservations were applied. Initial images, robot state, prompt and runtime matched "
        "the reference. All {} videos were independently decoded. Only MP4s are retained as visual files; "
        "observation records include video frame references. "
        "Historical capped episodes are separate.".format(total_trials * 2), "",
        "| Model | Full successes | Mean goal completion | Calls | Steps | Estimated USD | Mean API latency |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for model in models:
        usd = "${:.4f}".format(model["estimated_api_cost_usd"]) if model["cost_complete"] else "unresolved"
        lines.append("| {} | {}/{} | {:.1f}% | {} | {} | {} | {:.2f}s |".format(
            model["model_id"], model["successes"], model["trials"], model["mean_goal_completion_percent"], model["api_calls"],
            model["action_steps"], usd, model["weighted_mean_api_latency_seconds"] or 0))
    lines += ["", "| Model | Trial | Completion | Stop | Calls | Steps | Estimated USD | Elapsed |",
              "|---|---:|---:|---|---:|---:|---:|---:|"]
    for trial in trials:
        usd = "${:.4f}".format(trial["estimated_api_cost_usd"]) if trial["cost_complete"] else "unresolved"
        elapsed = int(trial["elapsed_seconds"])
        lines.append("| {} | [{}]({}/run_result.json) | {:.1f}% | {} | {} | {} | {} | {}m {:02d}s |".format(
            trial["model_id"], trial["trial"], trial["directory"], trial["completion_percent"],
            trial["termination_reason"], trial["calls"], trial["action_steps"], usd, elapsed // 60, elapsed % 60))
    lines += ["", "| Model / trial | Static camera | Wrist camera | Steps and readbacks |",
              "|---|---|---|---|"]
    for trial in trials:
        directory = trial["directory"]
        lines.append("| {} / {} | [MP4]({}/episode.mp4) | [MP4]({}/wrist_episode.mp4) | [Steps]({}/STEPS_TAKEN.txt) |".format(
            trial["model_id"], trial["trial"], directory, directory, directory))
    lines += ["", "API latency and elapsed time include reported request failures. Simulated movement time is separate; "
        "API waits pause the simulator. Costs use provider-reported tokens and actual cache reads/writes. "
        "Missing usage remains unresolved, never free. Provider caches were not forcibly cleared between trials.", "",
        "Completion uses final simulator goal predicates. A model-declared `done` is not a full success unless "
        "all goals are satisfied. `give_up` records the model ending an incomplete attempt. Limits are caps, "
        "not required episode lengths.", "",
        "- [Complete comparison JSON]({}_comparison.json)".format(manifest["batch_id"])]
    lines += ["- [Launch manifest and source hashes]({})".format(path.name) for path in manifest_paths]
    lines += [""]
    (root / (manifest["batch_id"] + "_REPORT.md")).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"batch_id": manifest["batch_id"], "verified": True, "videos": total_trials * 2,
        "estimated_api_cost_usd": comparison["estimated_api_cost_usd"],
        "models": [{key: model[key] for key in ("model_id", "successes", "mean_goal_completion_percent",
            "api_calls", "action_steps", "estimated_api_cost_usd", "weighted_mean_api_latency_seconds")}
            for model in models]}, indent=2))


if __name__ == "__main__":
    main()

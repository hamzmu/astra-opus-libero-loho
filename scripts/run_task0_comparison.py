"""Run a requested number of fresh LIBERO-LoHo task episodes per provider."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
import loho_frontier_eval as runner


def now():
    return datetime.now(timezone.utc).isoformat()


def hashes():
    names = ["src/loho_frontier_eval.py", "src/loho_pose_policy.py", "src/loho_pose_tools.py",
             "src/loho_anthropic.py", "src/loho_telemetry.py", "src/loho_scoring.py",
             "src/loho_control_feedback.py", "src/loho_cameras.py", "config/pricing-astra.json",
             "config/pricing-opus.json", "config/comparison-models.json", "scripts/record_opus_trial.py"]
    return {name: hashlib.sha256((WORKSPACE / name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--task", type=int, choices=range(5), default=0)
    parser.add_argument("--models", nargs="+", choices=("opus", "astra"), default=["opus", "astra"])
    parser.add_argument("--reference", type=Path, help="Simulator reference for the selected task")
    parser.add_argument("--trials-per-model", type=int, default=3)
    parser.add_argument("--start-trial", type=int, default=1)
    parser.add_argument("--extend-manifest", type=Path)
    parser.add_argument("--launch", action="store_true", help="Execute the requested episodes")
    args = parser.parse_args()
    if not args.launch:
        parser.error("Use --launch to execute; no API requests were made")
    if not all(c.isalnum() or c == "_" for c in args.batch_id):
        parser.error("Batch ID must contain only letters, numbers and underscores")
    if args.trials_per_model < 1 or args.start_trial < 1:
        parser.error("Trial counts and starting trial number must be positive")
    if len(set(args.models)) != len(args.models):
        parser.error("Select each model at most once")
    repo = Path("/root/projects/LIBERO-LOHO")
    os.environ.update(MUJOCO_GL="osmesa", PYOPENGL_PLATFORM="osmesa", LOHO_REPO=str(repo))
    for variable in ("OPENAI_API_KEY" if model == "astra" else "ANTHROPIC_API_KEY" for model in args.models):
        if not runner.load_key(variable):
            raise RuntimeError(variable + " is missing")
    results = WORKSPACE / "loho-study" / ("task " + str(args.task))
    results.mkdir(parents=True, exist_ok=True)
    manifest_path = results / (args.batch_id + ".json")
    if manifest_path.exists():
        raise ValueError("Batch already exists; refusing to duplicate paid episodes")
    profile = json.loads((WORKSPACE / "config/comparison-models.json").read_text())["shared_defaults"]
    profile = dict(profile, task_id=args.task)
    assert profile["max_decisions"] == 80 and profile["max_steps"] == 2000
    assert profile["max_api_cost_usd"] is None and profile["cost_guard_enabled"] is False
    source_hashes = hashes()
    reference = args.reference.resolve() if args.reference else results / "opus55_task0_max_128k_20261011_125617"
    if not (reference / "summary.json").is_file():
        raise ValueError("A completed simulator reference for this task is required")
    reference_data = json.loads((reference / "summary.json").read_text(encoding="utf-8-sig"))
    if reference_data["task_id"] != args.task:
        raise ValueError("The reference belongs to a different task")
    extension = None
    if args.extend_manifest:
        extension = json.loads(args.extend_manifest.read_text(encoding="utf-8-sig"))
        if extension["task_id"] != args.task:
            raise ValueError("The extension belongs to a different task")
        if extension["source_sha256"] != source_hashes:
            raise ValueError("The extension must use the same frozen controller/configuration")
        for model in args.models:
            previous = [item for item in extension["runs"] if item["model"] == model]
            if not previous or any(item["status"] != "complete" or not item.get("verification_passed") for item in previous):
                raise ValueError("The selected provider's preceding trials must be complete and verified")
            if sorted(item["trial"] for item in previous) != list(range(1, args.start_trial)):
                raise ValueError("Trial numbering must extend the existing cohort without gaps or duplicates")
    runs = []
    for model in args.models:
        for trial in range(args.start_trial, args.start_trial + args.trials_per_model):
            prefix = "opus55" if model == "opus" else "astra"
            name = "{}_task{}_max_nocost_trial{}_{}".format(prefix, args.task, trial, args.batch_id)
            directory = results / name
            if directory.exists():
                raise ValueError("Trial directory already exists: " + name)
            runs.append({"model": model, "trial": trial, "directory": name, "status": "queued"})
    manifest = {"batch_id": args.batch_id, "created_at": now(), "status": "running",
                "task_id": args.task, "initial_state_id": 0, "sim_seed": 0,
                "goal": reference_data["goal"], "reference_trial": str(reference),
                "reference_summary_sha256": hashlib.sha256((reference / "summary.json").read_bytes()).hexdigest(),
                "shared_defaults": profile, "source_sha256": source_hashes,
                "trials_per_model_requested": args.trials_per_model,
                "models_requested": args.models,
                "trial_numbers": list(range(args.start_trial, args.start_trial + args.trials_per_model)),
                "extends_batch_id": extension["batch_id"] if extension else None,
                "existing_trials_manifest": str(args.extend_manifest.resolve()) if args.extend_manifest else None,
                "provider_concurrency": "One fresh trial at a time per selected provider. Other providers may run concurrently in another batch.",
                "automatic_episode_retries": 0, "runs": runs}
    lock, stop = threading.Lock(), threading.Event()
    processes = {}

    def save():
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(manifest_path)

    def interrupt(signum, frame):
        stop.set()
        with lock:
            manifest["stop_requested_at"] = now()
            for process in processes.values():
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    process.loho_interrupted = True
            save()

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    with lock:
        save()

    def provider_sequence(model):
        for trial in [item for item in runs if item["model"] == model]:
            if stop.is_set():
                with lock:
                    trial["status"] = "canceled_before_start"
                    save()
                continue
            if hashes() != source_hashes:
                with lock:
                    trial.update(status="blocked_source_changed", error="Frozen source or configuration changed")
                    save()
                continue
            directory = results / trial["directory"]
            directory.mkdir()
            command = [sys.executable, "-u", str(WORKSPACE / "src/loho_frontier_eval.py"), "control",
                       "--repo", str(repo), "--model", model, "--task", str(args.task), "--initial-state", "0", "--seed", "0",
                       "--policy", "pose-tools", "--prompt-profile", "pose-tools-v1", "--effort", "max",
                       "--cameras", "agentview-wrist", "--orientation", "rotate180", "--wrist-orientation", "flip_vertical",
                       "--observation", "rgb-proprio", "--max-decisions", "80", "--max-steps", "2000",
                       "--control-hz", "10", "--resolution", "224", "--max-output-tokens", "128000",
                       "--image-history-observations", "0", "--outdir", str(directory)]
            if model == "astra":
                command += ["--effort-fallback", "xhigh"]
            launch = {"batch_id": args.batch_id, "requested_at": now(), "trial_number": trial["trial"],
                      "model": runner.MODEL_IDS[model], "command": command, "shared_defaults": profile,
                      "cost_guard_enabled": False, "estimated_trial_cost_cap_usd": None,
                      "task_id": args.task,
                      "reference_trial": Path(os.path.relpath(reference, directory)).as_posix(), "source_sha256": source_hashes,
                      "pricing": json.loads((WORKSPACE / ("config/pricing-opus.json" if model == "opus" else "config/pricing-astra.json")).read_text()),
                      "automatic_retries": 0, "fresh_conversation": True, "prior_run_hindsight_supplied": False}
            runner.write_json(directory / "launch_record.json", launch)
            with (directory / "controller.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE))
                with lock:
                    processes[model] = process
                    trial.update(status="running", started_at=now(), pid=process.pid)
                    save()
                print("START {} trial {} pid={} folder={}".format(model, trial["trial"], process.pid, directory.name), flush=True)
                while process.poll() is None:
                    if stop.is_set() or manifest_path.with_suffix(".stop").exists():
                        stop.set()
                        if not getattr(process, "loho_interrupted", False):
                            process.send_signal(signal.SIGINT)
                            process.loho_interrupted = True
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                code = process.returncode
            with lock:
                processes.pop(model, None)
                trial.update(controller_exit_code=code, finished_at=now(), status="recording")
                save()
            summary_path = directory / "summary.json"
            if summary_path.exists():
                report = json.loads(summary_path.read_text(encoding="utf-8-sig"))
                verification = subprocess.run([sys.executable, str(WORKSPACE / "scripts/record_opus_trial.py"),
                    str(directory), "--model", model, "--reference", str(reference)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(WORKSPACE))
                (directory / "recording.log").write_text(verification.stdout, encoding="utf-8")
                valid = verification.returncode == 0 and hashes() == source_hashes and not list(directory.glob("*.png"))
                with lock:
                    trial.update(status="complete" if valid else "verification_failed",
                        success=report["success"], completion_percent=report["trial_score"]["completion_percent"],
                        termination_reason=report["termination_reason"], calls=report["decisions_used"],
                        action_steps=report["simulator_action_steps"], estimated_api_cost_usd=report["estimated_api_cost_usd"],
                        known_estimated_api_cost_usd=report["known_estimated_api_cost_usd"], cost_complete=report["cost_complete"],
                        elapsed_seconds=report["elapsed_seconds"], mean_api_latency_seconds=report["mean_api_latency_seconds"],
                        total_api_latency_seconds=report["total_api_latency_seconds"],
                        max_effort_requests=sum(a.get("reasoning_effort") == "max" for a in report["api_attempts"]),
                        xhigh_effort_requests=sum(a.get("reasoning_effort") == "xhigh" for a in report["api_attempts"]),
                        cost_guard_enabled=report.get("cost_guard_enabled"), verification_passed=valid)
                    save()
                print("FINISH {} trial {}: {}%, stop={}, calls={}, steps={}, cost={}, verified={}".format(
                    model, trial["trial"], trial["completion_percent"], trial["termination_reason"],
                    trial["calls"], trial["action_steps"], trial["estimated_api_cost_usd"], valid), flush=True)
            else:
                with lock:
                    trial.update(status="error_no_summary", error="Controller ended without a summary; inspect controller.log")
                    save()
    try:
        with ThreadPoolExecutor(max_workers=len(args.models)) as executor:
            futures = [executor.submit(provider_sequence, model) for model in args.models]
            for future in futures:
                future.result()
    finally:
        with lock:
            manifest["finished_at"] = now()
            manifest["status"] = "complete" if all(item["status"] == "complete" for item in runs) else "needs_review"
            save()
    print("BATCH {} {}".format(args.batch_id, manifest["status"]), flush=True)


if __name__ == "__main__":
    main()

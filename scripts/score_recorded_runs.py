"""Score saved robot actions by verified simulator replay. No API/key access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_scoring import GoalScorer, trial_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=workspace / "loho_runs")
    parser.add_argument("--run", action="append", help="Replay only these run folder names under root")
    parser.add_argument("--include-tests", action="store_true", help="Allow explicitly selected offline integration fixtures")
    parser.add_argument("--repo", type=Path, default=Path(os.environ.get("LOHO_REPO", "C:/loho-libero" if os.name == "nt" else Path.home() / "projects/LIBERO-LOHO")))
    args = parser.parse_args()
    os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
    if os.environ["MUJOCO_GL"] == "osmesa":
        os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
    runner.setup_paths(args.repo)
    from libero.libero import benchmark
    import cv2
    import numpy as np
    suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
    for path in sorted(args.root.glob("*/summary.json")):
        if args.run and path.parent.name not in args.run:
            continue
        source_bytes = path.read_bytes()
        source = json.loads(source_bytes)
        if "model_id" not in source or (source.get("runtime", {}).get("test") and not args.include_tests):
            continue
        names = source.get("cameras", [source.get("camera", "agentview")])
        is_pose = source.get("action_interface") == "absolute_pose_tools"
        env = runner.make_env(suite, source["task_id"], source["rgb_resolution"][0], cameras=names,
                              control_freq=source.get("control_hz", 20), horizon=source.get("simulator_horizon", 1000))
        try:
            obs = runner.reset_episode(env, suite.get_task_init_states(source["task_id"])[source["initial_state_id"]],
                                       source["sim_seed"], source["settle_steps"])
            scorer = GoalScorer(env)
            scorer.update(env.env.timestep)
            if is_pose:
                from loho_pose_tools import PoseTools
                tools = PoseTools(env)
            initial = scorer.snapshot(bool(env.check_success()))
            errors = []
            timeline = []
            verified_images = 0
            for decision in source["decisions"]:
                if decision.get("proprioception") is not None:
                    measured = runner.robot_proprioception(obs)
                    errors.append(max(float(np.max(np.abs(np.asarray(measured[key]) - expected)))
                                      for key, expected in decision["proprioception"].items()))
                images = decision.get("input_frames") or {name: None for name in names}
                orientations = source.get("camera_orientations", {names[0]: source["orientation"]})
                for name, filename in images.items():
                    image_path = path.parent / filename if filename else None
                    rgb = runner.frame(obs, orientations[name], name)
                    if image_path is not None and image_path.exists():
                        saved = cv2.imread(str(image_path))
                        if saved is None or not np.array_equal(cv2.cvtColor(saved, cv2.COLOR_BGR2RGB), rgb):
                            raise ValueError("Replay image mismatch: " + str(image_path))
                    else:
                        expected_hash = decision.get("image_jpeg_sha256_by_camera", {}).get(name)
                        ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                                                  [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                        if not ok or expected_hash is None or hashlib.sha256(encoded.tobytes()).hexdigest() != expected_hash:
                            raise ValueError("Replay observation JPEG hash mismatch for " + name)
                verified_images += len(images)
                if is_pose:
                    actions = [item for item in source["executed_actions"] if item["decision_index"] == decision["decision_index"]]
                    if len(actions) != decision["executed_steps"]:
                        raise ValueError("Incomplete pose waypoint trace")
                    for item in actions:
                        (obs, _, _, _), native = tools.step(item["absolute_waypoint"])
                        if not np.allclose(native, item["native_action"], atol=1e-8):
                            raise ValueError("Pose action replay mismatch")
                        scorer.update(env.env.timestep)
                else:
                    for _ in range(decision["executed_steps"]):
                        obs, _, _, _ = env.step(decision["action"])
                        scorer.update(env.env.timestep)
                timeline.append({"decision_index": decision["decision_index"],
                                 "completion_percent": scorer.snapshot(bool(env.check_success()))["completion_percent"]})
            maximum_error = max(errors, default=0.0)
            if maximum_error > 0.00001 or bool(env.check_success()) != source["success"]:
                raise ValueError("Replay does not match the recorded robot state or success")
            result = {"source_run_id": source.get("run_id"),
                      "source_summary_sha256": hashlib.sha256(source_bytes).hexdigest(),
                      "real_api_calls": 0, "replay_verified": True,
                      "verified_observation_images": verified_images,
                      "maximum_proprioception_error": maximum_error,
                      "trial_status": trial_status(source["termination_reason"]),
                      "initial_trial_score": initial,
                      "trial_score": scorer.snapshot(bool(env.check_success())), "timeline": timeline}
            runner.write_json(path.parent / "trial_score.json", result)
            print("{}: {}% goal completion, task_complete={}, replay verified".format(
                path.parent.name, result["trial_score"]["completion_percent"], source["success"]), flush=True)
        finally:
            env.close()


if __name__ == "__main__":
    main()

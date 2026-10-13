"""Replay recorded actions for physics diagnostics. No API or credential access."""
import argparse
import json
import os
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
from loho_frontier_eval import make_env, reset_episode, robot_proprioception, setup_paths, write_json


def contacts(env):
    pairs = {}
    for i in range(env.sim.data.ncon):
        contact = env.sim.data.contact[i]
        names = [env.sim.model.geom_id2name(int(g)) for g in (contact.geom1, contact.geom2)]
        if not any(name and ("gripper" in name or "robot0" in name) for name in names):
            continue
        key = " / ".join(str(name) for name in names)
        pairs[key] = min(pairs.get(key, 0.0), float(contact.dist))
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(os.environ.get("LOHO_REPO", WORKSPACE / "LIBERO-LOHO")))
    args = parser.parse_args()
    source = json.loads(args.summary.read_text(encoding="utf-8"))
    setup_paths(args.repo)
    from libero.libero import benchmark
    import numpy as np
    suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
    env = make_env(suite, source["task_id"], source["rgb_resolution"][0],
                   cameras=source.get("cameras", [source.get("camera", "agentview")]))
    result = {"api_calls": 0, "diagnostics_only_privileged_state": True,
              "source_run_id": source["run_id"], "decisions": [], "replay_matches_trace": False}
    try:
        obs = reset_episode(env, suite.get_task_init_states(source["task_id"])[source["initial_state_id"]],
                            source["sim_seed"], source["settle_steps"])
        controller = env.robots[0].controller
        result["controller"] = {"input_min": controller.input_min.tolist(),
                                "input_max": controller.input_max.tolist(),
                                "output_min": controller.output_min.tolist(),
                                "output_max": controller.output_max.tolist()}
        errors = []
        for decision in source["decisions"]:
            measured = robot_proprioception(obs)
            error = max(float(np.max(np.abs(np.array(measured[key]) - np.array(expected))))
                        for key, expected in decision["proprioception"].items())
            errors.append(error)
            before = np.array(measured["end_effector_position_m"])
            row = {"decision_index": decision["decision_index"], "action": decision["action"],
                   "maximum_logged_proprioception_error": error, "eef_before_m": before.tolist(),
                   "contacts_before": contacts(env)}
            for _ in range(decision["executed_steps"]):
                obs, _, _, _ = env.step(decision["action"])
            after = np.array(robot_proprioception(obs)["end_effector_position_m"])
            row.update(eef_after_m=after.tolist(), observed_eef_delta_m=(after - before).tolist(),
                       contacts_after=contacts(env), success=bool(env.check_success()))
            result["decisions"].append(row)
        result["maximum_logged_proprioception_error"] = max(errors)
        result["replay_matches_trace"] = max(errors) < 0.00001
        result["final_success"] = bool(env.check_success())
    finally:
        env.close()
        write_json(args.summary.parent / "physics_audit.json", result)
    print(json.dumps({key: result[key] for key in ["api_calls", "replay_matches_trace", "maximum_logged_proprioception_error", "final_success"]}))
    for row in result["decisions"]:
        if row["decision_index"] in [0, 32, 34, 35, 40, 73]:
            print(json.dumps(row))


if __name__ == "__main__":
    main()

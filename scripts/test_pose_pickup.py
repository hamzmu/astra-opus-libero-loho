"""Privileged scripted pickup diagnostic only; never an LLM evaluation."""
import os
from pathlib import Path
import sys

import numpy as np

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_pose_tools import PoseTools

repo = Path.home() / "projects/LIBERO-LOHO"
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
runner.setup_paths(repo)
from libero.libero import benchmark
suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
env = runner.make_env(suite, 0, 224, cameras=["agentview", "robot0_eye_in_hand"], control_freq=10)
out = workspace / "loho_runs" / "pose_pickup_diagnostic"
out.mkdir(exist_ok=True)
try:
    obs = runner.reset_episode(env, suite.get_task_init_states(0)[0], 0)
    tools = PoseTools(env)
    body = env.sim.model.body_name2id(env.env.objects_dict["butter_1"].root_body)
    initial = env.sim.data.body_xpos[body].copy()
    moves = []
    for name, targets in [
        ("above", {"x": float(initial[0]), "y": float(initial[1]), "z": tools.table_z + .16, "gripper": 1}),
        ("descend", {"z": float(initial[2])}),
        ("close", {"gripper": 0}),
        ("lift", {"z": tools.table_z + .16}),
    ]:
        target, waypoints = tools.plan({"targets": targets, "note": "Privileged diagnostic " + name}, obs)
        steps = 0
        for point in list(waypoints) + [target] * 5:
            (obs, _, _, _), _ = tools.step(point)
            steps += 1
        moves.append({"phase": name, "result": tools.result(target, obs, len(waypoints), steps),
                      "private_object_position": env.sim.data.body_xpos[body].copy().tolist()})
        runner.save_frame(out / (name + "_agentview.png"), runner.frame(obs, "rotate180"))
        runner.save_frame(out / (name + "_wrist.png"), runner.frame(obs, "flip_vertical", "robot0_eye_in_hand"))
    final = env.sim.data.body_xpos[body].copy()
    lifted = float(final[2] - initial[2])
    result = {"real_api_calls": 0, "privileged_diagnostic_not_model_evaluation": True,
              "initial_object_position": initial.tolist(), "final_object_position": final.tolist(),
              "object_lift_m": lifted, "pickup_verified": lifted > .05, "moves": moves}
    runner.write_json(out / "test_result.json", result)
    print("Privileged pickup diagnostic: lift={:.4f}m, verified={}".format(lifted, lifted > .05), flush=True)
finally:
    env.close()

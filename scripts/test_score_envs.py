"""Offline integration of fixed rig facts and goal scoring on all five tasks."""
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_control_feedback import panda_rig_facts
from loho_scoring import GoalScorer

repo = Path("C:/loho-libero") if os.name == "nt" else Path.home() / "projects/LIBERO-LOHO"
os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
if os.name != "nt":
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
runner.setup_paths(repo)
from libero.libero import benchmark
suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
results = []
for task_id in range(5):
    env = runner.make_env(suite, task_id, 256)
    try:
        obs = runner.reset_episode(env, suite.get_task_init_states(task_id)[0], 0)
        facts = panda_rig_facts(env, "rotate180")
        assert facts["tabletop_world_z_m"] == (.41 if task_id in [1, 2, 3] else .9)
        assert "image-left" in facts["camera_axes"] and "image-down" in facts["camera_axes"]
        assert facts["translation_target_scale_m"] == [.05] * 3
        assert facts["rotation_target_scale_rad"] == [.5] * 3
        scorer = GoalScorer(env)
        scorer.update(env.env.timestep)
        score = scorer.snapshot(bool(env.check_success()))
        assert score["available"] and score["goals_total"] == (4 if task_id == 4 else 3)
        assert (score["completion_percent"] == 100) == bool(env.check_success())
        results.append({"task_id": task_id, "rig_facts": facts, "initial_trial_score": score})
        print("Task {}: fixed rig facts and {} goal predicates verified".format(task_id, score["goals_total"]), flush=True)
    finally:
        env.close()
runner.write_json(workspace / "loho_runs" / ("score_env_test_" + os.name) / "test_result.json",
                  {"passed": True, "real_api_calls": 0, "tasks": results})

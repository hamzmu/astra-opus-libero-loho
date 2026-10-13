"""Offline regression: LoHo hides horizon in returned done, so stop privately."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner

repo = Path("C:/loho-libero") if os.name == "nt" else Path.home() / "projects" / "LIBERO-LOHO"
os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
if os.name != "nt":
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
runner.setup_paths(repo)
from libero.libero import benchmark
suite = benchmark.get_benchmark_dict()["libero_loho_new"]()

calls = []
step_observations = []
real_make_env = runner.make_env


def make_short_env(suite, task_id, resolution):
    env = real_make_env(suite, task_id, resolution, horizon=7)
    real_step = env.step

    def tracked_step(action):
        result = real_step(action)
        step_observations.append({"timestep": env.env.timestep,
                                  "returned_done": bool(result[2]),
                                  "private_done": bool(env.env.done)})
        return result

    env.step = tracked_step
    return env


def offline_action(*unused):
    calls.append(True)
    return {"action": [0, 0, 0, 0, 0, 0, -1], "memory": "offline test"}, {
        "api_latency_seconds": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "returned_model": "offline_stub_no_api_request",
    }


runner.make_env = make_short_env
runner.load_key = lambda: "offline-test-no-credential"
runner.select_action = offline_action
args = SimpleNamespace(task=0, initial_state=0, seed=0, resolution=256,
                       observation="rgb-proprio",
                       orientation="rotate180", chunk=5, max_decisions=5,
                       max_output_tokens=2048,
                       outdir=Path(tempfile.mkdtemp(prefix="horizon_regression_" + os.name + "_",
                                                  dir=str(workspace / "loho_runs"))))
args.outdir.mkdir(parents=True, exist_ok=True)
runner.control(args, suite, {"test": "offline horizon regression", "real_model_calls": 0})
summary = json.loads((args.outdir / "summary.json").read_text())
assert len(calls) == 1, "Another model decision was requested after horizon"
assert summary["simulator_action_steps"] == 2, summary
assert summary["termination_reason"] == "horizon", summary
assert summary["success"] is False
assert step_observations[-1] == {"timestep": 7, "returned_done": False, "private_done": True}
runner.write_json(args.outdir / "test_result.json", {
    "passed": True, "real_api_calls": 0, "stub_decisions": len(calls),
    "settle_steps": 5, "action_steps": 2, "simulator_horizon": 7,
    "last_step": step_observations[-1],
})
print("Passed: LoHo returned done=False at horizon; runner stopped after two action steps, with no extra model call.")

"""Capture a real-simulator task reference with an offline API reply, never a paid request."""
import argparse
import os
from pathlib import Path
import sys
from unittest.mock import patch

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner


class Reply:
    ok, status_code = True, 200
    headers = {"x-request-id": "offline-task-reference"}
    def json(self):
        return {"id": "offline-reference", "status": "completed", "model": "gpt-6-astra",
                "service_tier": "default", "usage": {"input_tokens": 0, "output_tokens": 0,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}},
                "output": [{"type": "function_call", "call_id": "offline-done", "name": "done",
                    "arguments": '{"summary":"Simulator-only preflight; no model inference","hindsight":"Not supplied to paid trials"}'}]}


class Session:
    def post(self, *args, **kwargs):
        return Reply()
    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=int, choices=range(5))
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    if args.outdir.exists():
        raise ValueError("Reference directory already exists")
    os.environ.update(MUJOCO_GL="osmesa", PYOPENGL_PLATFORM="osmesa")
    real_runtime_info = runner.runtime_info
    def info(repo):
        result = real_runtime_info(repo)
        result.update(test="Simulator-only task reference", real_api_calls=0)
        return result
    argv = ["loho_frontier_eval.py", "control", "--repo", "/root/projects/LIBERO-LOHO",
            "--model", "astra", "--task", str(args.task), "--initial-state", "0", "--seed", "0",
            "--policy", "pose-tools", "--effort", "max", "--effort-fallback", "xhigh",
            "--max-decisions", "80", "--max-steps", "2000", "--max-output-tokens", "128000",
            "--cameras", "agentview-wrist", "--image-history-observations", "0", "--control-hz", "10",
            "--resolution", "224", "--outdir", str(args.outdir)]
    with patch.object(sys, "argv", argv), patch.object(runner, "load_key", lambda: "offline-no-secret"), \
         patch.object(runner, "runtime_info", info), patch("requests.Session", Session):
        runner.main()
    runner.write_json(args.outdir / "preflight_verification.json", {
        "passed": True, "task_id": args.task, "real_api_calls": 0,
        "robot_action_steps": 0, "reference_only": True,
        "note": "Real reset/cameras/calibration/proprioception with a local fake done reply. No prior-run actions or hindsight are supplied to the benchmark models."})


if __name__ == "__main__":
    main()

"""Real Panda pose-tool control with fake Responses; no key or paid API access."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import cv2
import numpy as np

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "src"))
import loho_frontier_eval as runner
from loho_pose_tools import PoseTools

repo = Path("C:/loho-libero") if os.name == "nt" else Path.home() / "projects/LIBERO-LOHO"
os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
if os.name != "nt":
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
runner.setup_paths(repo)
from libero.libero import benchmark
suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
base = workspace / "loho_runs" / ("pose_tools_test_" + os.name)
base.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix="run_", dir=str(base)))


class Reply:
    ok, status_code = True, 200
    headers = {"x-request-id": "offline-pose-test"}

    def __init__(self, index, name, arguments, status="completed"):
        self.index, self.name, self.arguments = index, name, arguments
        self.status = status

    def json(self):
        return {"status": self.status, "incomplete_details": {"reason": "max_output_tokens"} if self.status == "incomplete" else None,
                "model": "gpt-6-luna", "id": "reply{}".format(self.index),
                "service_tier": "default", "usage": {"input_tokens": 1000, "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}},
                "output": [{"type": "reasoning", "id": "reason{}".format(self.index), "summary": [], "encrypted_content": "opaque{}".format(self.index)},
                           {"type": "function_call", "id": "function{}".format(self.index), "call_id": "call{}".format(self.index),
                            "name": self.name, "arguments": json.dumps(self.arguments)}]}


class Session:
    def __init__(self, scenario):
        self.scenario, self.bodies, self.client_ids = scenario, [], []

    def post(self, url, json, headers, timeout):
        index = len(self.bodies)
        assert json["reasoning"]["effort"] == "medium"
        assert json["parallel_tool_calls"] is False and json["tool_choice"] == "required"
        assert "text" not in json
        self.bodies.append(json)
        self.client_ids.append(headers["X-Client-Request-Id"])
        latest = [item for item in json["input"] if item.get("role") == "user"][-1]
        state = __import__("json").loads(latest["content"][0]["text"])["measured_absolute_pose"]
        if self.scenario == "default":
            return Reply(index, "done", {"summary": "offline declaration", "hindsight": "test"})
        if self.scenario == "incomplete":
            return Reply(index, "done", {"summary": "offline", "hindsight": "test"}, "incomplete")
        if self.scenario == "steps":
            return Reply(index, "move_to", {"targets": {"gripper": 0}, "note": "close"})
        if self.scenario == "errors":
            return Reply(index, "move_to", {"targets": {"x": 99}, "note": "invalid test"})
        if self.scenario == "calls":
            return Reply(index, "move_to", {"targets": {"x": state["x"]}, "note": "hold test"})
        if index == 0:
            return Reply(index, "move_to", {"targets": {"x": state["x"] + .02, "z": state["z"] + .02}, "note": "small free-space motion"})
        return Reply(index, "give_up", {"reason": "offline test complete", "hindsight": "readback retained"})

    def close(self):
        pass


results = []
for scenario in ["default", "motion", "steps", "errors", "calls", "incomplete"]:
    folder = out / scenario
    session = Session(scenario)
    argv = ["src/loho_frontier_eval.py", "control", "--model", "luna", "--repo", str(repo), "--task", "0", "--outdir", str(folder)]
    if scenario == "steps":
        argv += ["--max-steps", "3"]
    with patch.object(sys, "argv", argv), patch.object(runner, "load_key", lambda: "offline-no-secret"), \
         patch.object(runner, "runtime_info", lambda unused: {"test": "offline pose integration", "real_api_calls": 0}), \
         patch("requests.Session", lambda: session):
        try:
            runner.main()
        except RuntimeError:
            assert scenario == "incomplete"
        else:
            assert scenario != "incomplete"
    r = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert r["policy"] == "pose-tools" and r["effort"] == "medium"
    assert r["cameras"] == ["agentview", "robot0_eye_in_hand"] and r["control_hz"] == 10
    assert r["max_decisions"] == 80 and r["rgb_resolution"] == [224, 224]
    assert r["max_action_steps"] == (3 if scenario == "steps" else 2000)
    assert r["max_estimated_api_cost_usd"] is None and r["cost_guard_enabled"] is False
    assert r["media_mode"] == "video_only" and r["png_frames_saved"] is False
    assert not list(folder.glob("*.png"))
    for decision in r["decisions"]:
        assert set(decision["input_video_frames"]) == set(r["cameras"])
        for camera, reference in decision["input_video_frames"].items():
            assert reference["file"] == r["video_files"][camera]
            assert reference["frame_index"] == decision["observation_simulator_step"] - r["settle_steps"]
            assert reference["timestamp_seconds"] == reference["frame_index"] / r["control_hz"]
    assert r["simulator_horizon"] == r["max_action_steps"] + 5
    assert r["cost_complete"] and r["api_attempts_total"] == len(session.bodies)
    assert len(set(session.client_ids)) == len(session.client_ids)
    if scenario == "default":
        assert r["termination_reason"] == "model_done" and not r["success"]
        expected_prompt = (workspace / "prompts/pose-tools-v1_task0_max.txt").read_text().strip()
        expected_prompt = expected_prompt.replace("with max reasoning.", "with medium reasoning.")
        expected_prompt = expected_prompt.replace(
            "All image-bearing observations retain their image payloads unchanged.",
            "Only the latest two image-bearing observations retain their image payloads.")
        assert r["system_prompt"].strip() == expected_prompt
    elif scenario == "motion":
        assert r["termination_reason"] == "give_up" and r["decisions_used"] == 2
        motion = r["decisions"][0]["tool_result"]
        assert motion["position_error_m"] < .015, motion
        assert len(r["executed_actions"]) == r["simulator_action_steps"]
        second = session.bodies[1]["input"]
        assert any(item.get("type") == "function_call" and item["call_id"] == "call0" for item in second)
        assert any(item.get("type") == "function_call_output" and item["call_id"] == "call0" for item in second)
        assert any(item.get("encrypted_content") == "opaque0" for item in second)
    elif scenario == "steps":
        assert r["simulator_action_steps"] == 3 and r["api_attempts_total"] == 1
        assert r["termination_reason"] == "step_budget"
        assert r["decisions"][0]["tool_result"]["playout_complete"] is False
    elif scenario == "errors":
        assert r["tool_error_count"] == 3 and r["termination_reason"] == "tool_errors"
        assert r["simulator_action_steps"] == 0 and r["api_attempts_total"] == 3
        assert r["total_input_tokens"] == 3000 and r["total_output_tokens"] == 300
    elif scenario == "calls":
        assert r["decisions_used"] == 80 and r["termination_reason"] == "decision_budget"
        images = sum(part.get("type") == "input_image" for item in session.bodies[-1]["input"]
                     for part in item.get("content", []) if isinstance(part, dict))
        assert images == 4
    elif scenario == "incomplete":
        assert r["decisions_used"] == 1 and r["api_attempts_total"] == 1
        assert r["total_input_tokens"] == 1000 and r["total_output_tokens"] == 100
        assert r["simulator_action_steps"] == 0 and r["termination_reason"] == "error"
    for body in session.bodies:
        assert "private_trial_score" not in json.dumps(body)
        assert "wooden_cabinet_1_top_region" not in json.dumps(body)
    for filename in r["video_files"].values():
        cap = cv2.VideoCapture(str(folder / filename))
        assert cap.isOpened() and cap.get(cv2.CAP_PROP_FPS) == 10
        frames = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            assert image.shape == (224, 224, 3)
            frames += 1
        cap.release()
        assert frames == r["simulator_action_steps"] + 1
    results.append({"scenario": scenario, "passed": True, "calls": r["decisions_used"],
                    "action_steps": r["simulator_action_steps"], "stop": r["termination_reason"]})
    print("Pose integration {} passed".format(scenario), flush=True)
runner.write_json(base / "test_result.json", {"passed": True, "real_api_calls": 0,
                                            "run_directory": str(out), "scenarios": results})

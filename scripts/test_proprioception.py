"""Offline integration: real robot sensors, exact API payload, no oracle state."""
import base64
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np

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


class OfflineResponse:
    ok = True
    status_code = 200
    headers = {"x-request-id": "offline-no-api-call"}

    def json(self):
        return {"status": "completed", "id": "offline",
                "model": runner.MODEL_IDS["luna"],
                "service_tier": "default",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "output": [{"type": "message", "content": [{
                    "type": "output_text",
                    "text": '{"action":[0,0,0,0,0,0,-1],"memory":"offline test"}',
                }]}]}


class OfflineSession:
    def __init__(self):
        self.bodies = []

    def post(self, url, json, headers, timeout):
        assert url == "https://api.openai.com/v1/responses"
        self.bodies.append(json)
        return OfflineResponse()


session = OfflineSession()
args = SimpleNamespace(chunk=5, observation="rgb-proprio", max_output_tokens=2048)
env = runner.make_env(suite, 0, 256)
try:
    obs = runner.reset_episode(env, suite.get_task_init_states(0)[0], 0)
    # Poison unrelated fields to ensure the whitelist never forwards them.
    obs["oracle_object_coordinates"] = "FORBIDDEN_OBJECT_ORACLE"
    obs["reward"] = "FORBIDDEN_REWARD"
    obs["success"] = "FORBIDDEN_SUCCESS"
    snapshot = runner.robot_proprioception(obs)
    expected = {
        "joint_positions_rad": "robot0_joint_pos",
        "joint_velocities_rad_s": "robot0_joint_vel",
        "end_effector_position_m": "robot0_eef_pos",
        "end_effector_quaternion_xyzw": "robot0_eef_quat",
        "gripper_joint_positions_m": "robot0_gripper_qpos",
        "gripper_joint_velocities_m_s": "robot0_gripper_qvel",
    }
    assert set(snapshot) == set(expected)
    for label, key in expected.items():
        np.testing.assert_allclose(snapshot[label], obs[key], rtol=0, atol=0.00000051)
    assert len(snapshot["joint_positions_rad"]) == 7
    assert len(snapshot["end_effector_quaternion_xyzw"]) == 4
    assert abs(np.linalg.norm(snapshot["end_effector_quaternion_xyzw"]) - 1) < 0.000002
    rgb = runner.frame(obs, "rotate180")
    runner.select_action(session, "offline-key", rgb, suite.get_task(0).language, "", args, snapshot)
    body = session.bodies[-1]
    assert body["model"] == "gpt-6-luna"
    encoded = json.dumps(body)
    assert "FORBIDDEN_" not in encoded
    assert "oracle_object_coordinates" not in encoded
    user_content = body["input"][1]["content"]
    assert [p["type"] for p in user_content] == ["input_text", "input_image"]
    state_line = user_content[0]["text"].splitlines()[3]
    assert json.loads(state_line) == snapshot
    jpeg = base64.b64decode(user_content[1]["image_url"].split(",", 1)[1])
    assert cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR).shape == (256, 256, 3)

    # A new action must result in a fresh measured snapshot, not reused state.
    for _ in range(5):
        obs, _, _, _ = env.step([0.1, 0, 0, 0, 0, 0, -1])
    next_snapshot = runner.robot_proprioception(obs)
    assert next_snapshot["end_effector_position_m"] != snapshot["end_effector_position_m"]
    runner.select_action(session, "offline-key", runner.frame(obs, "rotate180"),
                       suite.get_task(0).language, "", args, next_snapshot)
    assert json.loads(session.bodies[-1]["input"][1]["content"][0]["text"].splitlines()[3]) == next_snapshot

    # RGB-only requests must keep the previous prompt and exclude all measurements.
    args.observation = "rgb"
    args.prompt_profile = "legacy-v1"
    runner.select_action(session, "offline-key", rgb, suite.get_task(0).language, "", args)
    rgb_text = session.bodies[-1]["input"][1]["content"][0]["text"]
    assert all(label not in rgb_text for label in expected)
    previous = json.loads((workspace / "loho_runs" / "luna_wsl_smoke" / "summary.json").read_text())
    assert session.bodies[-1]["input"][0]["content"] == previous["system_prompt"]

    # Reject incomplete/non-finite state and a mode mismatch before a request.
    for broken in [dict(obs, robot0_joint_pos=np.full(7, np.nan)),
                   {key: value for key, value in obs.items() if key != "robot0_eef_quat"}]:
        try:
            runner.robot_proprioception(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid robot state was accepted")
    attempts = len(session.bodies)
    try:
        runner.select_action(session, "offline-key", rgb, "task", "", args, snapshot)
    except ValueError:
        pass
    else:
        raise AssertionError("RGB-only request accepted a proprioception payload")
    assert len(session.bodies) == attempts
    result = {"passed": True, "real_api_calls": 0, "platform": os.name,
              "fields": list(snapshot), "first_snapshot": snapshot,
              "next_snapshot": next_snapshot, "robot_state_refreshed": True,
              "oracle_fields_excluded": True, "rgb_baseline_prompt_preserved": True}
    runner.write_json(workspace / "loho_runs" / ("proprioception_test_" + os.name) / "test_result.json", result)
    print("Passed: real sensors, fresh state, RGB-only compatibility, invalid-state rejection, and no oracle fields.")
finally:
    env.close()

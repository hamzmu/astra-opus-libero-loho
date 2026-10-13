"""Real simulator cameras plus mocked model requests. No credentials/API access."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_cameras import camera_frames, camera_names

repo = Path("C:/loho-libero") if os.name == "nt" else Path.home() / "projects/LIBERO-LOHO"
os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
if os.name != "nt":
    os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
runner.setup_paths(repo)
from libero.libero import benchmark
suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
out = workspace / "loho_runs" / ("wrist_test_" + os.name)
out.mkdir(parents=True, exist_ok=True)
args = SimpleNamespace(cameras="agentview-wrist", orientation="rotate180", wrist_orientation="flip_vertical", resolution=256)
tasks = []
for task_id in range(5):
    env = runner.make_env(suite, task_id, 256, cameras=camera_names(args))
    try:
        obs = runner.reset_episode(env, suite.get_task_init_states(task_id)[0], 0)
        first = camera_frames(obs, args)
        for name, image in first.items():
            assert image.std() > 1
            runner.save_frame(out / ("task_{}_{}.png".format(task_id, name)), image)
        wrist_id = env.sim.model.camera_name2id("robot0_eye_in_hand")
        fixed_id = env.sim.model.camera_name2id("agentview")
        wrist_position = env.sim.data.cam_xpos[wrist_id].copy()
        fixed_position = env.sim.data.cam_xpos[fixed_id].copy()
        for _ in range(5):
            obs, _, _, _ = env.step([.1, .1, .1, 0, 0, 0, -1])
        second = camera_frames(obs, args)
        assert not np.array_equal(first["robot0_eye_in_hand"], second["robot0_eye_in_hand"])
        assert np.linalg.norm(wrist_position - env.sim.data.cam_xpos[wrist_id]) > .00001
        np.testing.assert_allclose(fixed_position, env.sim.data.cam_xpos[fixed_id], atol=1e-10)
        tasks.append({"task_id": task_id, "both_views_nonblank": True, "wrist_follows_arm": True,
                      "same_observation_timestep": int(env.env.timestep),
                      "initial_rgb_sha256": {name: hashlib.sha256(image.tobytes()).hexdigest() for name, image in first.items()}})
        print("Task {}: both cameras available; wrist follows arm; fresh RGB".format(task_id), flush=True)
    finally:
        env.close()


class Reply:
    ok = True
    status_code = 200
    headers = {"x-request-id": "offline-wrist-test"}

    def json(self):
        return {"model": "gpt-6-luna", "id": "offline", "status": "completed",
                "service_tier": "default", "usage": {"input_tokens": 0, "output_tokens": 0},
                "output": [{"type": "message", "content": [{"type": "output_text",
                    "text": '{"action":[0.1,0.1,-0.1,0,0,0,-1],"memory":"offline camera test"}'}]}]}


class Session:
    def __init__(self):
        self.bodies = []

    def post(self, url, json, headers, timeout):
        self.bodies.append(json)
        return Reply()

    def close(self):
        pass


controls = []
for config in ["wrist", "agentview-wrist"]:
    directory = out / ("control_" + config)
    session = Session()
    argv = ["loho_frontier_eval.py", "control", "--repo", str(repo), "--task", "0",
            "--policy", "direct", "--max-decisions", "2", "--outdir", str(directory), "--cameras", config]
    with patch.object(sys, "argv", argv), patch.object(runner, "load_key", lambda: "offline-no-credential"), \
         patch.object(runner, "runtime_info", lambda unused: {"test": "offline wrist integration", "real_api_calls": 0}), \
         patch("requests.Session", lambda: session):
        runner.main()
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    expected = ["robot0_eye_in_hand"] if config == "wrist" else ["agentview", "robot0_eye_in_hand"]
    assert report["cameras"] == expected
    assert report["decisions_used"] == 2 and report["simulator_action_steps"] == 10
    assert report["trial_score"]["available"] and report["trial_status"] == "budget_exhausted"
    assert len(session.bodies) == 2
    for body, decision in zip(session.bodies, report["decisions"]):
        content = body["input"][1]["content"]
        images = [item for item in content if item["type"] == "input_image"]
        assert len(images) == len(expected)
        assert set(decision["input_frames"]) == set(expected)
        assert set(decision["image_jpeg_sha256_by_camera"]) == set(expected)
        assert all((directory / name).exists() for name in decision["input_frames"].values())
        assert "private_trial_score" not in json.dumps(body)
        assert "wooden_cabinet_1_top_region" not in json.dumps(body)
    if config == "wrist":
        assert report["camera_configuration"] == "wrist"
        assert "camera_axes" not in report["rig_calibration"]
        assert "no fixed overview" in report["system_prompt"]
    else:
        assert "TWO current RGB" in report["system_prompt"]
    video_counts = {}
    for name, filename in report["video_files"].items():
        cap = cv2.VideoCapture(str(directory / filename))
        assert cap.isOpened() and cap.get(cv2.CAP_PROP_FPS) == 20
        frames = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            assert image.shape == (256, 256, 3)
            frames += 1
        cap.release()
        assert frames == 11
        video_counts[name] = frames
    controls.append({"requested": config, "effective": report["camera_configuration"],
                     "cameras": expected, "verified_video_frames": video_counts,
                     "recorded_observation_steps": [d["observation_simulator_step"] for d in report["decisions"]]})
    print("Control {}: labeled API payload and synchronized recordings verified".format(config), flush=True)
runner.write_json(out / "test_result.json", {"passed": True, "real_api_calls": 0, "tasks": tasks, "controls": controls})

"""Local LIBERO-LoHo diagnostics and RGB/proprioceptive LLM control. Python 3.8+."""
import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from loho_telemetry import AttemptLedger, DEFAULT_PRICING, summarize_attempts
from loho_scoring import GoalScorer, trial_status
from loho_control_feedback import PROMPT_PROFILE, decision_context, motion_feedback, panda_rig_facts
from loho_cameras import CAMERA_CONFIGS, CAMERA_LABELS, camera_configuration, camera_names, camera_orientations, camera_frames, validate_camera_frame

WORKSPACE = Path(__file__).resolve().parents[1]
MODEL_IDS = {"luna": "gpt-6-luna", "astra": "gpt-6-astra", "opus": "claude-opus-5-5"}
MODEL_PRICING = {"luna": DEFAULT_PRICING, "astra": WORKSPACE / "config/pricing-astra.json",
                 "opus": WORKSPACE / "config/pricing-opus.json"}
NEUTRAL = [0, 0, 0, 0, 0, 0, -1]


class UnsupportedEffort(RuntimeError):
    pass

PROPRIOCEPTION_FIELDS = (
    ("robot0_joint_pos", "joint_positions_rad", 7),
    ("robot0_joint_vel", "joint_velocities_rad_s", 7),
    ("robot0_eef_pos", "end_effector_position_m", 3),
    ("robot0_eef_quat", "end_effector_quaternion_xyzw", 4),
    ("robot0_gripper_qpos", "gripper_joint_positions_m", 2),
    ("robot0_gripper_qvel", "gripper_joint_velocities_m_s", 2),
)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def setup_paths(repo):
    """Use project-local LIBERO configuration without an interactive import."""
    import yaml
    root = repo / "libero" / "libero"
    if not (root / "bddl_files" / "libero_loho_new").is_dir():
        raise RuntimeError("LIBERO-LoHo source not found at {}".format(repo))
    config = repo / ".loho-config"
    config.mkdir(exist_ok=True)
    datasets = repo / "libero" / "datasets"
    datasets.mkdir(exist_ok=True)
    paths = {
        "benchmark_root": str(root),
        "bddl_files": str(root / "bddl_files"),
        "init_states": str(root / "init_files"),
        "assets": str(root / "assets"),
        "datasets": str(datasets),
    }
    (config / "config.yaml").write_text(yaml.safe_dump(paths), encoding="utf-8")
    os.environ["LIBERO_CONFIG_PATH"] = str(config)
    sys.path.insert(0, str(repo))


def runtime_info(repo):
    names = ["numpy", "mujoco", "robosuite", "torch", "gym", "opencv-python"]
    versions = {name: importlib.metadata.version(name) for name in names}
    revision_file = repo / "UPSTREAM_REVISION.txt"
    if revision_file.exists():
        revision = revision_file.read_text().strip()
    else:
        revision = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
    return {
        "platform": platform.platform(), "python": sys.version,
        "repo": str(repo), "revision": revision, "versions": versions,
        "render_backend": os.environ.get("MUJOCO_GL"),
        "local_windows_binding_patch": os.name == "nt",
    }


def make_env(suite, task_id, resolution, horizon=1000, cameras=None, control_freq=20):
    from libero.libero import get_libero_path
    from libero.libero.envs import OffScreenRenderEnv
    task = suite.get_task(task_id)
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    return OffScreenRenderEnv(
        bddl_file_name=str(bddl), controller="OSC_POSE", robots=["Panda"],
        camera_names=cameras or ["agentview"], camera_heights=resolution,
        camera_widths=resolution, camera_depths=False,
        camera_segmentations=None, horizon=horizon, control_freq=control_freq,
    )


def reset_episode(env, initial_state, seed, settle_steps=5):
    env.seed(seed)
    env.reset()
    obs = env.set_init_state(initial_state)
    for _ in range(settle_steps):
        obs, _, done, _ = env.step(NEUTRAL)
        if done:
            raise RuntimeError("Episode terminated during settling")
    return obs


def simulator_horizon_reached(env):
    """LoHo returns success as done; inspect the private step limit separately."""
    simulator = env.env
    return bool(simulator.done or simulator.timestep >= simulator.horizon)


def frame(obs, orientation, camera="agentview"):
    import numpy as np
    rgb = obs[camera + "_image"]
    if orientation == "rotate180":
        rgb = rgb[::-1, ::-1]
    elif orientation == "flip_vertical":
        rgb = rgb[::-1]
    return np.ascontiguousarray(rgb, dtype=np.uint8)


def save_frame(path, rgb):
    import cv2
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise RuntimeError("Failed to save camera frame")


def video_frame_references(video_files, frame_index, hz):
    """Locate an observation in each video: initial frame 0, then one per action step."""
    return {name: {"file": filename, "frame_index": int(frame_index),
                   "timestamp_seconds": frame_index / hz}
            for name, filename in video_files.items()}


def video_writer(path, resolution, fps=20):
    import cv2
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                             (resolution, resolution))
    if not writer.isOpened():
        raise RuntimeError("Could not open MP4 writer")
    return writer


def append_video(writer, rgb):
    import cv2
    writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def smoke(args, suite, info):
    import numpy as np
    tasks = range(suite.n_tasks) if args.task is None else [args.task]
    names = camera_names(args)
    primary = names[0]
    report = {"runtime": info, "benchmark": "libero_loho_new", "tasks": [],
              "model_calls": 0, "orientation": args.orientation,
              "camera_configuration": camera_configuration(args), "cameras": names,
              "camera_orientations": camera_orientations(args)}
    if suite.n_tasks != 5:
        raise RuntimeError("Expected the five-task LoHo suite")
    for task_id in tasks:
        task = suite.get_task(task_id)
        states = suite.get_task_init_states(task_id)
        if len(states) < 5:
            raise RuntimeError("Task {} has fewer than five fixed starts".format(task_id))
        env = make_env(suite, task_id, args.resolution, cameras=names, control_freq=getattr(args, "control_hz", 20))
        item = {"task_id": task_id, "goal": task.language,
                "available_initial_states": len(states), "tested_initial_states": []}
        writers = {name: video_writer(args.outdir / ("task_{}_smoke{}.mp4".format(task_id, "" if name == primary else "_wrist")),
                                     args.resolution, getattr(args, "control_hz", 20)) for name in names}
        try:
            for state_id in range(min(args.states, len(states))):
                start = time.monotonic()
                obs = reset_episode(env, states[state_id], args.seed)
                images = camera_frames(obs, args)
                rgb = images[primary]
                for name, camera_rgb in images.items():
                    assert camera_rgb.std() > 1, "Camera frame is blank: " + name
                    save_frame(args.outdir / "task_{}_state_{}{}.png".format(task_id, state_id, "" if name == primary else "_wrist"), camera_rgb)
                if state_id == 0:
                    save_frame(args.outdir / "task_{}_raw.png".format(task_id), frame(obs, "raw", primary))
                    save_frame(args.outdir / "task_{}_vertical.png".format(task_id), frame(obs, "flip_vertical", primary))
                for name, camera_rgb in images.items():
                    append_video(writers[name], camera_rgb)
                for _ in range(5):
                    obs, _, done, _ = env.step(NEUTRAL)
                    for name, camera_rgb in camera_frames(obs, args).items():
                        append_video(writers[name], camera_rgb)
                    if done:
                        raise RuntimeError("Unexpected smoke-test termination")
                item["tested_initial_states"].append({
                    "initial_state_id": state_id, "image_shape": list(rgb.shape),
                    "initial_frame_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
                    "initial_frame_sha256_by_camera": {name: hashlib.sha256(image.tobytes()).hexdigest() for name, image in images.items()},
                    "success": bool(env.check_success()), "simulator_steps": 10,
                    "elapsed_seconds": time.monotonic() - start,
                })
                print("Smoke task {} state {}: RGB and stepping passed".format(task_id, state_id), flush=True)
        finally:
            for writer in writers.values():
                writer.release()
            env.close()
        report["tasks"].append(item)
        write_json(args.outdir / "summary.json", report)
    print("Simulator smoke tests passed: {} tasks".format(len(report["tasks"])), flush=True)


def private_robot_state(env, obs):
    robot = env.robots[0]
    return {
        "eef_position": env.sim.data.site_xpos[robot.eef_site_id].copy().tolist(),
        "eef_rotation_matrix": env.sim.data.site_xmat[robot.eef_site_id].copy().reshape(3, 3).tolist(),
        "gripper_qpos": obs["robot0_gripper_qpos"].copy().tolist(),
    }


def robot_proprioception(obs):
    """Allow only measured Panda state, never the full simulator observation."""
    import numpy as np
    snapshot = {}
    for source, label, length in PROPRIOCEPTION_FIELDS:
        if source not in obs:
            raise ValueError("Required proprioception field is missing: " + source)
        values = np.asarray(obs[source], dtype=np.float64)
        if values.shape != (length,) or not np.isfinite(values).all():
            raise ValueError("Invalid proprioception field: " + source)
        snapshot[label] = np.round(values, 6).tolist()
    return snapshot


def calibrate(args, suite, info):
    import numpy as np
    from scipy.spatial.transform import Rotation
    task_id = 0 if args.task is None else args.task
    states = suite.get_task_init_states(task_id)
    names = camera_names(args)
    env = make_env(suite, task_id, args.resolution, cameras=names, control_freq=getattr(args, "control_hz", 20))
    results = {"runtime": info, "model_calls": 0, "axes": [],
               "camera_configuration": camera_configuration(args), "cameras": names,
               "camera_orientations": camera_orientations(args),
               "note": "Private calibration diagnostics; this mode makes no model calls."}
    try:
        labels = ["positive_x", "positive_y", "positive_z", "positive_rx",
                  "positive_ry", "positive_rz", "close_gripper", "open_gripper"]
        for axis, label in enumerate(labels):
            obs = reset_episode(env, states[0], args.seed)
            if label == "open_gripper":
                for _ in range(15):
                    obs, _, _, _ = env.step([0, 0, 0, 0, 0, 0, 1])
            before = private_robot_state(env, obs)
            for name, rgb in camera_frames(obs, args).items():
                save_frame(args.outdir / (label + "_before" + ("" if name == names[0] else "_wrist") + ".png"), rgb)
            action = list(NEUTRAL)
            if axis < 6:
                action[axis] = 0.1
            elif label == "close_gripper":
                action[6] = 1
            for _ in range(5 if axis < 6 else 15):
                obs, _, _, _ = env.step(action)
            after = private_robot_state(env, obs)
            for name, rgb in camera_frames(obs, args).items():
                save_frame(args.outdir / (label + "_after" + ("" if name == names[0] else "_wrist") + ".png"), rgb)
            delta = (np.array(after["eef_position"]) - np.array(before["eef_position"])).tolist()
            rotation_delta = Rotation.from_matrix(
                np.array(after["eef_rotation_matrix"]) @ np.array(before["eef_rotation_matrix"]).T
            ).as_rotvec().tolist()
            if axis < 3:
                assert delta[axis] > 1e-4, "Translation axis did not move in the expected direction"
            elif axis < 6:
                assert rotation_delta[axis - 3] > 1e-4, "Rotation axis did not move in the expected direction"
            elif label == "close_gripper":
                assert abs(after["gripper_qpos"][0]) < abs(before["gripper_qpos"][0])
            else:
                assert abs(after["gripper_qpos"][0]) > abs(before["gripper_qpos"][0])
            results["axes"].append({"label": label, "action": action,
                                    "before": before, "after": after, "eef_delta": delta,
                                    "eef_rotation_delta": rotation_delta, "passed": True})
            print("Calibration {}: passed".format(label), flush=True)
        results["controller"] = env.robots[0].controller.name
        results["controller_input_min"] = np.asarray(env.robots[0].controller.input_min).tolist()
        results["controller_input_max"] = np.asarray(env.robots[0].controller.input_max).tolist()
        results["controller_output_min"] = np.asarray(env.robots[0].controller.output_min).tolist()
        results["controller_output_max"] = np.asarray(env.robots[0].controller.output_max).tolist()
        results["all_checks_passed"] = True
        write_json(args.outdir / "calibration.json", results)
    finally:
        env.close()


def load_key(variable="OPENAI_API_KEY"):
    """Read only the requested credential; never print or persist its value."""
    key = os.environ.get(variable, "").strip()
    if not key and (WORKSPACE / ".env").exists():
        for line in (WORKSPACE / ".env").read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == variable:
                key = value.strip().strip('"').strip("'")
                break
    if not key:
        raise RuntimeError(variable + " is missing")
    return key


def validate_action(decoded):
    import numpy as np
    values = decoded["action"]
    if not isinstance(values, list) or len(values) != 7:
        raise ValueError("Expected seven action numbers")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        raise ValueError("Action values must be numbers")
    action = np.asarray(values, dtype=np.float64)
    if not np.isfinite(action).all():
        raise ValueError("Non-finite action")
    clipped = np.clip(action, -1, 1)
    clipped[6] = 1 if clipped[6] >= 0 else -1
    return clipped, bool(np.any(np.abs(action[:6]) > 1))


def legacy_system_prompt(repeat, observation_mode="rgb-proprio"):
    if observation_mode == "rgb":
        observations = """You control a simulated Panda robot arm using visual feedback only.
Complete the user's manipulation task. Each decision receives ONE current RGB
image from the same fixed camera. You have no depth, object coordinates, joint
positions, end-effector pose, reward, success checks, or hidden simulation state."""
    elif observation_mode == "rgb-proprio":
        observations = """You control a simulated Panda robot arm using RGB and proprioceptive feedback.
Complete the user's manipulation task. Each decision receives ONE current RGB
image from the same fixed camera and measured robot proprioception from that
same observation. The robot state has these labeled fields:
- joint_positions_rad: seven Panda arm joints, joints 1 through 7, in radians.
- joint_velocities_rad_s: the same seven joints in radians per second.
- end_effector_position_m: [x,y,z] of the gripper site in world coordinates, in meters.
- end_effector_quaternion_xyzw: [x,y,z,w] world orientation of the end-effector body
  as reported by robosuite; this is a quaternion, not Euler angles.
- gripper_joint_positions_m: two signed finger-slide positions in meters.
- gripper_joint_velocities_m_s: their signed velocities in meters per second.
The finger positions have opposite signs; larger absolute positions mean a more
open gripper. These measured values are not normalized controller commands.
You have no depth, object coordinates, rewards, success checks or other hidden
simulation state. Use RGB to locate objects and robot state to track your arm."""
    else:
        raise ValueError("Unknown observation mode: " + observation_mode)
    return observations + "\n" + """Return ONE normalized 7D OSC_POSE action in this order:
[dx, dy, dz, dRx, dRy, dRz, gripper].
The first six numbers are relative controller commands in [-1,1], not meters or
degrees. Translation is in the world/base frame; +Z moves upward. The gripper
uses -1 to open and +1 to close. The action repeats for %d simulation steps.
Use small corrections and the next image. No higher-level grasp/place or motion
planning tools. Return only JSON with action and memory. Keep memory under 300
characters. All seven action values must be finite.""" % repeat


def system_prompt(repeat, observation_mode="rgb-proprio", profile=PROMPT_PROFILE, rig_facts=None, cameras=None, wrist_orientation="flip_vertical"):
    cameras = cameras or ["agentview"]
    baseline = legacy_system_prompt(repeat, observation_mode)
    if profile == "legacy-v1":
        if cameras != ["agentview"]:
            raise ValueError("legacy-v1 supports only the original agentview camera")
        return baseline
    if profile != PROMPT_PROFILE:
        raise ValueError("Unknown prompt profile: " + profile)
    text = baseline.replace("world/base frame", "world frame")
    if cameras == ["agentview", "robot0_eye_in_hand"]:
        text = text.replace("ONE current RGB\nimage from the same fixed camera",
                            "TWO current RGB\nimages: fixed agentview and moving robot0_eye_in_hand wrist camera")
    elif cameras == ["robot0_eye_in_hand"]:
        text = text.replace("ONE current RGB\nimage from the same fixed camera",
                            "ONE current RGB\nimage from the moving robot0_eye_in_hand wrist camera")
    elif cameras != ["agentview"]:
        raise ValueError("Unsupported policy cameras: " + str(cameras))
    text += "\n\n" + """Panda control and manipulation guidance:
- At 20 Hz each simulator step is 0.05 seconds. Inference pauses the simulator.
  A normalized translation of 1 requests a 0.05 m servo target offset per axis;
  a normalized rotation of 1 requests 0.5 rad. These are target offsets, not
  guaranteed achieved motion. Repeating an action recomputes relative targets
  from the current pose each step; it does not command one fixed destination.
- Use the fixed rig calibration below. World coordinates are not image pixels.
  The camera is oblique. Do not guess table height from general Panda examples.
  The reported grip site is not the lowest fingertip: fingers can touch the table
  while the reported site is still above its surface. Never descend through it.
- First align above an object with open fingers and safe clearance. Correct XY
  before lowering; avoid the cabinet, rims, handles and other obstacles. Near an
  object use small translations (typically 0.05-0.2 normalized) and reassess.
- Open with -1 and close with +1. A tabletop contact is not a grasp. Align the
  fingers around the object's narrow dimension; use a small yaw correction if
  needed. Close when the object is between the fingers, then lift a little and
  check visually that the object moved with the gripper before transporting it.
- Carry with clearance. Lower gently for placement, open, lift clear, and verify
  the object stayed at its destination after the hand moves out of the way.
- Break the task into subgoals and retain your current subgoal, axis mapping,
  alignment, grasp evidence and recovery plan in memory. Verify each transition.
  Attempt all requested objects and final operations before claiming completion.
- A commanded motion is not evidence that motion occurred. Compare consecutive
  observations. If lowering stops working, do not keep pushing down or assume
  you are still descending. Re-check alignment, lift clear and correct sideways,
  or close only when the visual grasp alignment supports doing so. After two
  stalled translations, change the move; do not repeat the same blocked strategy.
- Spend the remaining decisions on verified task progress. Do not repeatedly
  calibrate or describe a future grasp without attempting and checking it."""
    if observation_mode == "rgb-proprio":
        text += "\n" + """- Treat measured arm motion as the readback. The user message includes the last
  three actions and their measured results; a stall warning is based on robot
  motion only and does not reveal the contact object. Finger qpos magnitudes are
  about 0.04 m when fully open and near zero on an empty close. A nonzero settled
  close can indicate an obstruction or object; verify by lifting and observing."""
    else:
        text += "\n- In RGB-only mode infer motion and grasp evidence from successive images and memory; no measured robot feedback is supplied."
    if len(cameras) == 2:
        text += "\n\n" + """Use the two labeled camera views together:
- Both images and the robot measurements come from the same simulation observation.
- agentview is the fixed overview: use it to identify the required objects, locate
  the destination, check clearance and verify that a lifted object follows the hand.
- robot0_eye_in_hand moves with the Panda wrist: use the close view to inspect
  finger/object alignment before closing and to refine small approach corrections.
  At the neutral start, finger tips and the gripper appear near its lower edge.
- The overview's +X/+Y image mapping does not apply to the wrist camera. Wrist
  image axes move when the arm rotates. Compare small moves with both views and
  measured robot motion rather than assuming a fixed wrist-to-world pixel map.
- A held object may be occluded or leave the wrist view. Its absence there does
  not prove a grasp; verify in agentview after lifting. Do not move blindly when
  both views are occluded: lift clear or reorient, then reassess."""
    elif cameras == ["robot0_eye_in_hand"]:
        text = text.replace("The camera is oblique.", "The camera moves with the wrist.")
        text += "\n\n" + """Wrist camera guidance:
- The attached image is robot0_eye_in_hand, mounted on the Panda wrist. There is
  no fixed overview in this condition. At the neutral start, the finger tips and
  gripper appear near the lower edge. Use the close view for alignment before closing.
- Wrist image axes change as the arm rotates. Do not apply a fixed +X/+Y pixel
  mapping. Use small corrections and measured robot motion when available.
- Objects can become occluded or leave the view during a lift. Disappearance
  alone does not verify a grasp. Use finger readback when available and reorient
  or move clear to inspect the scene; retain uncertainty in memory.
- A distant drawer or target may leave the wrist view. Reacquire it before an
  approach or placement instead of assuming its previous pixel location is current."""
    if "robot0_eye_in_hand" in cameras and wrist_orientation == "raw":
        text = text.replace("lower edge", "upper edge")
    if rig_facts is not None:
        text += "\n\nFixed rig calibration (no object locations or task-state oracle):\n"
        text += json.dumps(rig_facts, separators=(",", ":"), allow_nan=False)
    return text


def request_system_prompt(args):
    return system_prompt(args.chunk, args.observation, getattr(args, "prompt_profile", PROMPT_PROFILE),
                         getattr(args, "_rig_facts", None), camera_names(args), getattr(args, "wrist_orientation", "flip_vertical"))


def build_user_prompt(goal, memory, proprioception=None, context=None):
    lines = ["Task: " + goal, "Previous self-generated memory: " + memory]
    if proprioception is not None:
        lines.append("Current robot proprioception (same observation as the attached RGB image):")
        lines.append(json.dumps(proprioception, separators=(",", ":"), allow_nan=False))
        lines.append("Choose the next action using the attached camera image and current robot proprioception.")
    else:
        lines.append("Choose the next action using only the attached camera image.")
    if context is not None:
        lines.append("Decision budget and recent executed actions (measured motion is not task-success evidence):")
        lines.append(json.dumps(context, separators=(",", ":"), allow_nan=False))
    return "\n".join(lines)


def request_user_prompt(args, goal, memory, proprioception):
    text = build_user_prompt(goal, memory, proprioception, getattr(args, "_decision_context", None))
    if len(camera_names(args)) == 2:
        text = text.replace("attached camera image", "two labeled camera images")
    elif camera_names(args) == ["robot0_eye_in_hand"]:
        text = text.replace("attached camera image", "attached wrist camera image")
    return text


def selected_model(args):
    name = getattr(args, "model", "luna")
    if name not in MODEL_IDS:
        raise ValueError("Unsupported model: " + str(name))
    return MODEL_IDS[name]


def model_pricing(args):
    name = getattr(args, "model", "luna")
    path = getattr(args, "pricing_file", None) or MODEL_PRICING[name]
    pricing = json.loads(Path(path).read_text(encoding="utf-8"))
    if pricing.get("model") != selected_model(args):
        raise ValueError("The pricing snapshot does not match the selected model")
    return pricing


def send_response(session, key, body, ledger, attempt):
    import requests
    start = time.monotonic()
    # No automatic retries: a failed request stops the smoke test.
    try:
        response = session.post("https://api.openai.com/v1/responses", json=body,
                                headers={"Authorization": "Bearer " + key,
                                         "X-Client-Request-Id": attempt["attempt_id"]},
                                timeout=(15, 600 if body.get("reasoning", {}).get("effort") in ("max", "xhigh") else 180))
    except BaseException as exc:
        ledger.update(attempt, "transport_failed", api_latency_seconds=time.monotonic() - start,
                      outcome="timeout" if isinstance(exc, requests.exceptions.Timeout) else "transport_error",
                      error_type=type(exc).__name__, error=str(exc).replace(key, "[REDACTED]"))
        raise
    latency = time.monotonic() - start
    ledger.update(attempt, "response_headers", api_latency_seconds=latency,
                  http_status=response.status_code, request_id=response.headers.get("x-request-id"),
                  outcome="response_received")
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object from the API")
    except (ValueError, TypeError) as exc:
        ledger.update(attempt, "response_invalid", outcome="invalid_response",
                      error=str(exc).replace(key, "[REDACTED]"))
        raise
    # Persist usage before checking HTTP status, completion, refusal, JSON, or action validity.
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = None
    elif not all(isinstance(v, (dict, int, float, str, type(None), bool)) for v in usage.values()):
        usage = None
    if usage is not None:
        try:
            json.dumps(usage, allow_nan=False)
        except (TypeError, ValueError):
            usage = None
    ledger.update(attempt, "response_metadata", response_id=payload.get("id"),
                  returned_model=payload.get("model"), returned_service_tier=payload.get("service_tier"),
                  response_status=payload.get("status"), usage=usage,
                  incomplete_details=payload.get("incomplete_details"))
    if not response.ok:
        error = payload.get("error")
        error = error if isinstance(error, dict) else {}
        message = str(error.get("message", "Request failed")).replace(key, "[REDACTED]")
        ledger.update(attempt, "http_failed", outcome="api_error", error_code=error.get("code"), error=message)
        exception = (UnsupportedEffort if response.status_code == 400 and
                     (error.get('param') == 'reasoning.effort' or ('effort' in message.lower() and 'reasoning' in message.lower()))
                     and any(word in message.lower() for word in ('unsupported', 'not supported', 'invalid value')) else RuntimeError)
        raise exception("OpenAI HTTP {}: {}: {}".format(response.status_code, error.get("code"), message))
    if payload.get("status") != "completed":
        ledger.update(attempt, "response_incomplete", outcome="incomplete")
        raise RuntimeError("{} response status: {} ({})".format(body["model"], payload.get("status"), payload.get("incomplete_details")))
    return payload, {
        "attempt_id": attempt["attempt_id"],
        "request_id": response.headers.get("x-request-id"), "response_id": payload.get("id"),
        "returned_model": payload.get("model"), "usage": usage,
        "returned_service_tier": payload.get("service_tier"),
        "api_latency_seconds": latency,
    }


def select_action(session, key, rgb, goal, memory, args, proprioception=None,
                ledger=None, decision_index=None):
    import cv2
    import requests
    names = camera_names(args)
    frames = rgb if isinstance(rgb, dict) else {names[0]: rgb}
    if set(frames) != set(names):
        raise ValueError("Camera image payload does not match the configured cameras")
    if (args.observation == "rgb-proprio") != (proprioception is not None):
        raise ValueError("Proprioception payload does not match observation mode")
    user_text = request_user_prompt(args, goal, memory, proprioception)
    content = [{"type": "input_text", "text": user_text}]
    image_hashes = {}
    for name in names:
        # Older direct diagnostic callers do not specify resolution.
        resolution = getattr(args, "resolution", frames[name].shape[0])
        rgb_frame = validate_camera_frame(frames[name], resolution, name)
        ok, jpeg = cv2.imencode(".jpg", cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR),
                                [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise RuntimeError("JPEG encoding failed for " + name)
        image_hashes[name] = hashlib.sha256(jpeg.tobytes()).hexdigest()
        if names != ["agentview"]:
            content.append({"type": "input_text", "text": CAMERA_LABELS[name]})
        content.append({"type": "input_image", "detail": "high",
                        "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")})
    body = {
        "model": selected_model(args), "reasoning": {"effort": getattr(args, "effort", "high")},
        "max_output_tokens": args.max_output_tokens, "store": False,
        "service_tier": "default",
        "input": [
            {"role": "system", "content": request_system_prompt(args)},
            {"role": "user", "content": content},
        ],
        "text": {"format": {
            "type": "json_schema", "name": "robot_action", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "properties": {"action": {"type": "array", "items": {"type": "number"},
                                                   "minItems": 7, "maxItems": 7},
                                      "memory": {"type": "string"}},
                       "required": ["action", "memory"]},
        }},
    }
    ledger = ledger if ledger is not None else AttemptLedger(pricing=model_pricing(args))
    jpeg_sha256 = image_hashes[names[0]]
    attempt = ledger.begin(decision_index, body["model"], body["service_tier"],
                           input_text=user_text, image_jpeg_sha256=jpeg_sha256,
                           observation_mode=args.observation, camera_configuration=camera_configuration(args),
                           image_jpeg_sha256_by_camera=image_hashes,
                           input_video_frames=getattr(args, "_input_video_frames", {}))
    payload, api = send_response(session, key, body, ledger, attempt)
    try:
        parts = [c for item in payload.get("output", []) if item.get("type") == "message"
                 for c in item.get("content", [])]
        if any(c.get("type") == "refusal" for c in parts):
            ledger.update(attempt, "response_refused", outcome="refusal")
            raise RuntimeError(body["model"] + " returned a refusal")
        texts = [c["text"] for c in parts if c.get("type") == "output_text"]
        output_text = "".join(texts)
        ledger.update(attempt, "output_received", output_text=output_text.replace(key, "[REDACTED]"))
        decoded = json.loads(output_text)
    except (ValueError, TypeError, KeyError) as exc:
        ledger.update(attempt, "output_invalid", outcome="invalid_json",
                      error=str(exc).replace(key, "[REDACTED]"))
        raise
    ledger.update(attempt, "output_decoded", outcome="decoded")
    return decoded, {
        **api, "input_text": user_text, "image_jpeg_sha256": jpeg_sha256,
        "image_jpeg_sha256_by_camera": image_hashes,
    }


def control(args, suite, info):
    import requests
    task_id = 0 if args.task is None else args.task
    states = suite.get_task_init_states(task_id)
    if not 0 <= args.initial_state < len(states):
        raise ValueError("Invalid stored initial state index")
    key = load_key()
    task = suite.get_task(task_id)
    names = camera_names(args)
    primary_camera = names[0]
    config = camera_configuration(args)
    env = (make_env(suite, task_id, args.resolution) if names == ["agentview"]
           else make_env(suite, task_id, args.resolution, cameras=names))
    args._rig_facts = panda_rig_facts(env, args.orientation) if getattr(args, "prompt_profile", PROMPT_PROFILE) != "legacy-v1" else None
    if args._rig_facts is not None and names != ["agentview"]:
        args._rig_facts["camera_orientations"] = camera_orientations(args)
        if "agentview" not in names:
            args._rig_facts.pop("camera_axes", None)
            args._rig_facts.pop("camera_orientation", None)
    args._decision_context = None
    report = {
        "runtime": info, "benchmark": "libero_loho_new", "task_id": task_id,
        "goal": task.language, "initial_state_id": args.initial_state,
        "sim_seed": args.seed, "model_id": selected_model(args), "effort": getattr(args, "effort", "high"),
        "policy": "direct", "action_interface": "normalized_osc_delta", "control_hz": 20,
        "camera": primary_camera, "cameras": names, "camera_configuration": config,
        "camera_orientations": camera_orientations(args),
        "video_files": {name: "episode.mp4" if name == primary_camera else "wrist_episode.mp4" for name in names},
        "media_mode": "video_only", "png_frames_saved": False,
        "rgb_resolution": [args.resolution, args.resolution],
        "observation_mode": args.observation,
        "proprioception_fields": [label for _, label, _ in PROPRIOCEPTION_FIELDS]
            if args.observation == "rgb-proprio" else [],
        "orientation": args.orientation, "action_repeat": args.chunk,
        "max_decisions": args.max_decisions, "settle_steps": 5,
        "simulator_horizon": int(env.env.horizon),
        "max_action_steps": getattr(args, "max_steps", int(env.env.horizon) - 5),
        "max_output_tokens_per_call": args.max_output_tokens,
        "max_estimated_api_cost_usd": None, "cost_guard_enabled": False,
        "prompt_profile": getattr(args, "prompt_profile", PROMPT_PROFILE),
        "rig_calibration": args._rig_facts,
        "system_prompt": request_system_prompt(args), "decisions": [],
        "consecutive_translation_stalls": 0, "translation_stall_count": 0,
        "success": False, "simulator_action_steps": 0, "decisions_used": 0,
        "invalid_action_count": 0, "estimated_api_cost_usd": None,
        "termination_reason": "running", "telemetry_schema_version": 2,
    }
    pricing = model_pricing(args)
    try:
        ledger = AttemptLedger(args.outdir / "api_attempts.jsonl", pricing=pricing,
                               context={"task_id": task_id, "initial_state_id": args.initial_state,
                                        "sim_seed": args.seed, "observation_mode": args.observation,
                                        "camera_configuration": config, "cameras": names})
    except BaseException:
        env.close()
        raise
    report.update(run_id=ledger.run_id, pricing=ledger.pricing,
                  api_attempts_file="api_attempts.jsonl", api_attempts=ledger.attempts)
    writers = {}
    try:
        for name in names:
            writers[name] = video_writer(args.outdir / report["video_files"][name], args.resolution)
    except BaseException:
        for writer in writers.values():
            writer.release()
        env.close()
        raise
    scorer = GoalScorer(env)
    start = time.monotonic()
    session = requests.Session()

    def persist_telemetry():
        report.update(summarize_attempts(ledger.attempts))
        report["elapsed_seconds"] = time.monotonic() - start
        write_json(args.outdir / "summary.json", report)

    ledger.on_change = persist_telemetry
    persist_telemetry()
    try:
        obs = reset_episode(env, states[args.initial_state], args.seed)
        report["success"] = bool(env.check_success())
        scorer.update(env.env.timestep)
        report["trial_score"] = scorer.snapshot(report["success"])
        memory = ""
        for name, rgb in camera_frames(obs, args).items():
            append_video(writers[name], rgb)
        for decision in range(args.max_decisions):
            if report["success"]:
                report["termination_reason"] = "success"
                break
            if simulator_horizon_reached(env):
                report["termination_reason"] = "horizon"
                break
            if report["simulator_action_steps"] >= report["max_action_steps"]:
                report["termination_reason"] = "step_budget"
                break
            images = camera_frames(obs, args)
            observation_step = int(env.env.timestep)
            proprioception = robot_proprioception(obs) if args.observation == "rgb-proprio" else None
            args._decision_context = (decision_context(report, args.observation)
                                      if report["prompt_profile"] != "legacy-v1" else None)
            input_video_frames = video_frame_references(report["video_files"], report["simulator_action_steps"], 20)
            args._input_video_frames = input_video_frames
            decoded, api = select_action(session, key, images, task.language, memory, args,
                                       proprioception, ledger, decision)
            report["decisions_used"] += 1
            try:
                action, clipped = validate_action(decoded)
                if not isinstance(decoded["memory"], str):
                    raise ValueError("Memory must be a string")
            except (KeyError, ValueError, TypeError) as exc:
                report["invalid_action_count"] += 1
                attempt = next(a for a in ledger.attempts if a["attempt_id"] == api["attempt_id"])
                ledger.update(attempt, "action_invalid", outcome="invalid_action",
                              error=str(exc).replace(key, "[REDACTED]"))
                raise
            attempt = next((a for a in ledger.attempts if a["attempt_id"] == api.get("attempt_id")), None)
            if attempt is not None:
                ledger.update(attempt, "action_validated", outcome="valid_action")
            memory = decoded["memory"][:300]
            record = {"decision_index": decision, "input_video_frames": input_video_frames,
                      "observation_simulator_step": observation_step,
                      "raw_action": decoded["action"], "action": action.tolist(),
                      "action_clipped": clipped, "memory": memory, **api,
                      "proprioception": proprioception,
                      "executed_steps": 0}
            report["decisions"].append(record)
            done = False
            for _ in range(args.chunk):
                if report["simulator_action_steps"] >= report["max_action_steps"]:
                    done = True
                    break
                obs, _, done, _ = env.step(action)
                record["executed_steps"] += 1
                report["simulator_action_steps"] += 1
                for name, rgb in camera_frames(obs, args).items():
                    append_video(writers[name], rgb)
                report["success"] = bool(env.check_success())
                scorer.update(env.env.timestep)
                report["trial_score"] = scorer.snapshot(report["success"])
                done = done or simulator_horizon_reached(env)
                if report["success"] or done:
                    break
            after = robot_proprioception(obs) if args.observation == "rgb-proprio" else None
            record["motion_feedback"] = motion_feedback(proprioception, after, action.tolist(), record["executed_steps"])
            stalled = bool(record["motion_feedback"] and record["motion_feedback"]["translation_stalled"])
            report["translation_stall_count"] += int(stalled)
            report["consecutive_translation_stalls"] = report["consecutive_translation_stalls"] + 1 if stalled else 0
            record["private_trial_score"] = report["trial_score"]
            print("{} decision {}: action={}, {:.2f}s, usage={}".format(
                selected_model(args), decision, action.tolist(), api["api_latency_seconds"], api["usage"]), flush=True)
            write_json(args.outdir / "summary.json", report)
            if done or report["success"]:
                report["termination_reason"] = ("success" if report["success"] else
                    "horizon" if simulator_horizon_reached(env) else "step_budget")
                break
        else:
            report["termination_reason"] = "decision_budget"
        report["final_video_frames"] = video_frame_references(report["video_files"], report["simulator_action_steps"], 20)
    except KeyboardInterrupt:
        report["termination_reason"] = "interrupted"
        raise
    except Exception as exc:
        report["termination_reason"] = "error"
        report["error"] = str(exc).replace(key, "[REDACTED]")
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - start
        report.update(summarize_attempts(ledger.attempts))
        report["trial_score"] = scorer.snapshot(report["success"])
        report["trial_status"] = trial_status(report["termination_reason"])
        for writer in writers.values():
            writer.release()
        session.close()
        try:
            env.close()
        finally:
            write_json(args.outdir / "summary.json", report)
            score = report["trial_score"]
            print("Trial {}: task_complete={}, goal_completion={}%, cost_usd={}".format(
                report["trial_status"], report["success"], score["completion_percent"],
                report["estimated_api_cost_usd"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["smoke", "calibrate", "control"])
    parser.add_argument("--repo", type=Path, default=Path(os.environ.get("LOHO_REPO", WORKSPACE / "LIBERO-LOHO")))
    parser.add_argument("--task", type=int, choices=range(5))
    parser.add_argument("--states", type=int, default=5)
    parser.add_argument("--initial-state", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resolution", type=int)
    parser.add_argument("--orientation", choices=["rotate180", "flip_vertical", "raw"], default="rotate180")
    parser.add_argument("--cameras", choices=list(CAMERA_CONFIGS),
                        help="Camera input: agentview-wrist (default), agentview (fixed), or wrist")
    parser.add_argument("--wrist-orientation", choices=["rotate180", "flip_vertical", "raw"], default="flip_vertical")
    parser.add_argument("--model", choices=list(MODEL_IDS), default="astra")
    parser.add_argument("--observation", choices=["rgb", "rgb-proprio"], default="rgb-proprio",
                        help="Model input: RGB plus measured robot state (default), or RGB only")
    parser.add_argument("--policy", choices=["pose-tools", "direct"],
                        help="Absolute pose tools and conversation (default), or historical normalized direct actions")
    parser.add_argument("--prompt-profile", choices=["legacy-v1", PROMPT_PROFILE, "pose-tools-v1"])
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--effort-fallback", choices=["xhigh", "high", "medium", "low"],
                        help="Astra max fallback for explicit unsupported-effort errors (default xhigh)")
    parser.add_argument("--image-history-observations", type=int,
                        help="Image observations to retain; 0 keeps all. Max comparisons and Opus require append-only images.")
    parser.add_argument("--control-hz", type=int, choices=[10, 20])
    parser.add_argument("--max-steps", type=int, help="Action-step budget; default 2000 for pose tools")
    parser.add_argument("--chunk", type=int, default=5, help="Direct policy only: repetitions per normalized action")
    parser.add_argument("--max-decisions", type=int, help="API-call budget; default 80 for pose tools")
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--pricing-file", type=Path,
                        help="USD pricing snapshot to record and use for request-cost estimates")
    args = parser.parse_args()
    args.policy = args.policy or ("direct" if args.prompt_profile in ("legacy-v1", PROMPT_PROFILE) else "pose-tools")
    args.prompt_profile = args.prompt_profile or ("pose-tools-v1" if args.policy == "pose-tools" else PROMPT_PROFILE)
    if (args.policy == "pose-tools") != (args.prompt_profile == "pose-tools-v1"):
        parser.error("pose-tools requires pose-tools-v1; direct requires legacy-v1 or calibrated-v2")
    args.effort = args.effort or ("max" if args.policy == "pose-tools" and args.model in ("astra", "opus")
                                else "medium" if args.policy == "pose-tools" else "high")
    args.effort_fallback = args.effort_fallback or ('xhigh' if args.model == 'astra' and args.effort == 'max' and args.policy == 'pose-tools' else None)
    args.image_history_observations = args.image_history_observations if args.image_history_observations is not None else (
        0 if args.model == "opus" or args.effort == "max" else 2)
    if args.image_history_observations < 0:
        parser.error("Image history must be nonnegative; zero retains all observations")
    if args.model == "opus" and (args.policy != "pose-tools" or args.image_history_observations != 0):
        parser.error("Opus uses pose tools and append-only image history to preserve bound thinking")
    args.max_decisions = args.max_decisions if args.max_decisions is not None else (80 if args.policy == "pose-tools" else 5)
    args.max_steps = args.max_steps if args.max_steps is not None else (2000 if args.policy == "pose-tools" else 995)
    args.control_hz = args.control_hz or (10 if args.policy == "pose-tools" else 20)
    if args.mode == "control" and args.policy == "direct" and args.control_hz != 20:
        parser.error("The historical direct control profile uses 20 Hz; pose-tools supports 10 or 20 Hz")
    args.resolution = args.resolution if args.resolution is not None else (224 if args.policy == "pose-tools" else 256)
    args.max_output_tokens = args.max_output_tokens if args.max_output_tokens is not None else (
        128000 if args.policy == "pose-tools" and args.effort in ("max", "xhigh") else 8192 if args.policy == "pose-tools" else 2048)
    args.cameras = args.cameras or ("agentview" if args.prompt_profile == "legacy-v1" else "agentview-wrist")
    if args.prompt_profile == "legacy-v1" and args.cameras != "agentview":
        parser.error("legacy-v1 preserves the original agentview-only condition; use calibrated-v2 for wrist images")
    if args.policy == "pose-tools" and args.observation != "rgb-proprio":
        parser.error("Absolute pose tools require robot proprioception for named targets and readback")
    if min(args.states, args.resolution, args.chunk, args.max_decisions, args.max_output_tokens, args.max_steps) < 1:
        parser.error("Budgets and dimensions must be positive")
    # Preserve the short Windows junction; resolve() expands it to the long
    # OneDrive path and defeats the task-4 MAX_PATH workaround.
    args.repo = Path(os.path.abspath(str(args.repo)))
    if args.outdir is None:
        mode_label = args.mode + ("_" + args.policy + "_" + args.model + "_" + args.observation + "_" + args.cameras if args.mode == "control" else "")
        args.outdir = WORKSPACE / "loho_runs" / (platform.system().lower() + "_" + mode_label + "_" + time.strftime("%Y%m%d_%H%M%S"))
    args.outdir = args.outdir.resolve()
    args.outdir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MUJOCO_GL", "glfw" if os.name == "nt" else "osmesa")
    if os.environ["MUJOCO_GL"] == "osmesa":
        os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
    setup_paths(args.repo)
    from libero.libero import benchmark
    suite = benchmark.get_benchmark_dict()["libero_loho_new"]()
    info = runtime_info(args.repo)
    print("{} on {}, output={}".format(args.mode, platform.system(), args.outdir), flush=True)
    if args.mode == "control" and args.policy == "pose-tools":
        from loho_pose_policy import control_pose
        control_pose(args, suite, info)
    else:
        {"smoke": smoke, "calibrate": calibrate, "control": control}[args.mode](args, suite, info)


if __name__ == "__main__":
    main()

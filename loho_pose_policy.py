"""Persistent Responses conversation driving Panda absolute-pose motion tools."""
import copy
import hashlib
import json
import time
from scipy.spatial.transform import Rotation

from loho_cameras import CAMERA_LABELS, camera_frames, camera_names, camera_configuration, camera_orientations
from loho_pose_tools import MotionRejected, PoseTools, POSE_PROFILE
from loho_scoring import GoalScorer, trial_status
from loho_telemetry import AttemptLedger, summarize_attempts


def image_content(images):
    import base64
    import cv2
    content, hashes = [], {}
    for name, rgb in images.items():
        ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise ValueError("Cannot encode camera " + name)
        hashes[name] = hashlib.sha256(encoded.tobytes()).hexdigest()
        content += [{"type": "input_text", "text": CAMERA_LABELS[name]},
                    {"type": "input_image", "detail": "high",
                     "image_url": "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")}]
    return content, hashes


class Conversation:
    def __init__(self, system, image_history=2):
        self.items = [{"role": "system", "content": system}]
        self.image_history = image_history

    def observe(self, text, images):
        content, hashes = image_content(images)
        self.items.append({"role": "user", "content": [{"type": "input_text", "text": text}] + content})
        return hashes

    def reply(self, output):
        # Preserve complete output, including encrypted reasoning and assistant phase.
        self.items.extend(copy.deepcopy(output))

    def result(self, call_id, result):
        self.items.append({"type": "function_call_output", "call_id": call_id,
                           "output": json.dumps(result, separators=(",", ":"), allow_nan=False)})

    def nudge(self, text):
        self.items.append({"role": "user", "content": text})

    def outgoing(self):
        result = copy.deepcopy(self.items)
        observations = [i for i, item in enumerate(result) if isinstance(item.get("content"), list)
                        and any(part.get("type") == "input_image" for part in item["content"])]
        for index in (observations[:-self.image_history] if self.image_history else []):
            result[index]["content"] = [part for part in result[index]["content"] if part.get("type") != "input_image"]
            result[index]["content"].append({"type": "input_text", "text": "[Earlier camera payloads elided; observation text retained.]"})
        return result

    def transcript(self):
        result = copy.deepcopy(self.items)
        for item in result:
            item.pop("encrypted_content", None)
            if isinstance(item.get("content"), list):
                for index, part in enumerate(item["content"]):
                    if part.get("type") == "input_image":
                        item["content"][index] = {"type": "input_text", "text": "[Camera observation is in the recorded MP4 at its input_video_frames index.]"}
        return result


def pose_prompt(tools, args, rig_facts):
    history = getattr(args, 'image_history_observations', 2)
    image_history_text = ("All image-bearing observations retain their image payloads unchanged."
                          if history == 0 else "Only the latest two image-bearing observations retain their image payloads."
                          if history == 2 else "Only the latest {} image-bearing observations retain their image payloads.".format(history))
    return """You operate a simulated Panda arm through motion tools. Work toward the task
using the measured robot state and the labeled RGB views. Use one tool call per
turn and include a short human-readable note explaining each move.

move_to accepts named ABSOLUTE grasp-site targets: x/y/z in world meters,
roll/pitch/yaw in radians relative to the trial's start orientation, and gripper
in [0,1] (0 fully closed, 1 fully open). Omitted pose dimensions hold measured
values; an omitted gripper preserves its last command to maintain grip pressure.
Euler rotation order is xyz; yaw rotates about world vertical
relative to the start pose. These are physical targets, not normalized deltas.
Use measured_absolute_pose for targeting. The raw robot proprioception quaternion
describes the end-effector body in world coordinates, not these relative site angles.
The executor interpolates at 25%% of each dimension's range per second with a
5%%-of-range per-step ceiling. A move is limited to 10 seconds; split longer moves.
The result reports actual steps played, measured pose and remaining target error.
Motion can fall short through contact, reach limits or tracking lag. Change a
blocked target rather than repeating it. A short settling hold may be included.

The reported position is the grasp site between the fingers, not the wrist or
palm. With downward fingers, table contact occurs with this site only about
0.01 m above the tabletop: do not assume a 0.1 m wrist-to-finger height offset.
Use the table reference and visual object height when choosing a grasp height.
Align above the object while open, descend gently, close, lift about 0.05 m and
verify in the fixed view that the object follows before carrying it. A nonzero
finger opening on a close can indicate an object or obstruction; it is not proof.
Use clearance for transport. Lower for placement, open, lift clear, then verify.
Both static agentview and moving robot0_eye_in_hand images are available by
default. Use the overview to locate objects/destinations and verify lifts, and
the wrist view for close alignment. Wrist axes change when the arm rotates;
do not apply the fixed camera's pixel mapping to it. Occlusion is not success.
You receive no object coordinates, depth, rewards or private goal checks.

Your observation/action/tool-result text history is retained for the trial.
%s
Use past readbacks and tool results to improve the plan. done ends the trial
when you believe the goal is achieved; give_up ends an unsuccessful attempt.
Both ask for hindsight: concrete rig/task facts you wish you knew at the start.
The evaluator determines full-task success independently of your declaration.
You have %d model calls and %d action steps at %.0f Hz, with %s reasoning.

Workspace bounds: %s
Fixed rig facts (no object locations): %s""" % (
        image_history_text, args.max_decisions, args.max_steps, tools.hz, args.effort, json.dumps(tools.bounds()), json.dumps(rig_facts))


def control_pose(args, suite, info):
    import requests
    import loho_frontier_eval as runner
    task_id = 0 if args.task is None else args.task
    states = suite.get_task_init_states(task_id)
    if not 0 <= args.initial_state < len(states):
        raise ValueError("Invalid stored initial state")
    is_opus = args.model == 'opus'
    if is_opus:
        import loho_anthropic as anthropic
    key = runner.load_key('ANTHROPIC_API_KEY') if is_opus else runner.load_key()
    names = camera_names(args)
    task = suite.get_task(task_id)
    pricing = runner.model_pricing(args)
    ledger = AttemptLedger(args.outdir / "api_attempts.jsonl", pricing=pricing,
        context={"task_id": task_id, "initial_state_id": args.initial_state, "sim_seed": args.seed,
                 "observation_mode": args.observation, "camera_configuration": camera_configuration(args),
                 "action_interface": "absolute_pose_tools", "prompt_profile": POSE_PROFILE})
    env = runner.make_env(suite, task_id, args.resolution, cameras=names,
                          horizon=args.max_steps + 5, control_freq=args.control_hz)
    report = {"runtime": info, "benchmark": "libero_loho_new", "task_id": task_id, "goal": task.language,
              "model_id": runner.selected_model(args), "effort": args.effort,
              "effective_effort": args.effort, "effort_fallback": args.effort_fallback,
              "fallback_events": [], "cost_guard_enabled": False,
              "policy": "pose-tools", "action_interface": "absolute_pose_tools", "prompt_profile": POSE_PROFILE,
              "provider": "anthropic" if is_opus else "openai",
              "context_mode": "conversation_and_tool_results", "image_history_observations": args.image_history_observations,
              "image_history_mode": "all" if args.image_history_observations == 0 else "latest",
              "initial_state_id": args.initial_state, "sim_seed": args.seed,
              "camera": names[0], "cameras": names, "camera_configuration": camera_configuration(args),
              "camera_orientations": camera_orientations(args), "orientation": args.orientation,
              "rgb_resolution": [args.resolution] * 2, "observation_mode": args.observation,
              "control_hz": args.control_hz, "max_speed_fraction": .25, "max_decisions": args.max_decisions,
              "max_action_steps": args.max_steps, "settle_steps": 5, "simulator_horizon": args.max_steps + 5,
              "max_output_tokens_per_call": args.max_output_tokens, "max_estimated_api_cost_usd": None,
              "run_id": ledger.run_id, "pricing": ledger.pricing, "api_attempts_file": "api_attempts.jsonl",
              "api_attempts": ledger.attempts, "decisions": [], "executed_actions": [],
              "simulator_action_steps": 0, "decisions_used": 0, "success": False,
              "termination_reason": "running", "tool_error_count": 0, "telemetry_schema_version": 3,
              "media_mode": "video_only", "png_frames_saved": False,
              "video_files": {name: "episode.mp4" if i == 0 else "wrist_episode.mp4" for i, name in enumerate(names)}}
    writers, session, conversation, scorer = {}, requests.Session(), None, GoalScorer(env)
    started = time.monotonic()

    def persist():
        report.update(summarize_attempts(ledger.attempts))
        report["decisions_used"] = len(ledger.attempts)
        report["trial_score"] = scorer.snapshot(report["success"])
        report["elapsed_seconds"] = time.monotonic() - started
        runner.write_json(args.outdir / "summary.json", report)

    ledger.on_change = persist
    try:
        for name in names:
            writers[name] = runner.video_writer(args.outdir / report["video_files"][name], args.resolution, args.control_hz)
        obs = runner.reset_episode(env, states[args.initial_state], args.seed)
        tools = PoseTools(env)
        facts = runner.panda_rig_facts(env, args.orientation)
        facts.pop("translation_target_scale_m", None)
        facts.pop("rotation_target_scale_rad", None)
        facts["camera_orientations"] = camera_orientations(args)
        facts["grasp_site_table_contact_clearance_m_approx"] = .01
        facts["fully_open_finger_position_m_approx"] = .04
        if "agentview" not in names:
            facts.pop("camera_axes", None)
            facts.pop("camera_orientation", None)
        report["rig_calibration"] = facts
        report["workspace_bounds"] = tools.bounds()
        report["start_grasp_site_rotation_xyzw"] = Rotation.from_matrix(tools.start_rotation).as_quat().tolist()
        report["system_prompt"] = pose_prompt(tools, args, facts)
        if names != ["agentview", "robot0_eye_in_hand"]:
            report["system_prompt"] += "\nThis trial selects only {}. Use the available view; no unselected camera is attached.".format(
                ", ".join(names))
        conversation = anthropic.OpusConversation(report["system_prompt"]) if is_opus else Conversation(
            report["system_prompt"], args.image_history_observations)
        report["success"] = bool(env.check_success())
        scorer.update(env.env.timestep)
        for name, rgb in camera_frames(obs, args).items():
            runner.append_video(writers[name], rgb)
        consecutive_errors = 0
        for index in range(args.max_decisions):
            if len(ledger.attempts) >= args.max_decisions:
                report['termination_reason'] = 'decision_budget'
                break
            if report["success"]:
                report["termination_reason"] = "success"
                break
            if report["simulator_action_steps"] >= args.max_steps:
                report["termination_reason"] = "step_budget"
                break
            images = camera_frames(obs, args)
            proprio = runner.robot_proprioception(obs)
            text = json.dumps({"task": task.language, "observation_step": int(env.env.timestep),
                               "model_calls_remaining_including_this": args.max_decisions - len(ledger.attempts),
                               "action_steps_remaining": args.max_steps - report["simulator_action_steps"],
                               "measured_absolute_pose": tools.readback(obs), "robot_proprioception": proprio}, allow_nan=False)
            image_hashes = conversation.observe(text, images)
            input_video_frames = runner.video_frame_references(
                report["video_files"], report["simulator_action_steps"], args.control_hz)
            body = anthropic.request_body(conversation, tools.schemas(), args) if is_opus else {"model": runner.selected_model(args), "reasoning": {"effort": report['effective_effort']},
                    "max_output_tokens": args.max_output_tokens, "store": False, "service_tier": "default",
                    "include": ["reasoning.encrypted_content"], "input": conversation.outgoing(),
                    "tools": tools.schemas(), "tool_choice": "required", "parallel_tool_calls": False}
            persist()
            payload = None
            while len(ledger.attempts) < args.max_decisions:
                actual_effort = args.effort if is_opus else body['reasoning']['effort']
                attempt = ledger.begin(index, body['model'], 'default', input_text=text,
                    provider=report['provider'], reasoning_effort=actual_effort,
                    image_jpeg_sha256_by_camera=image_hashes, input_video_frames=input_video_frames,
                    conversation_input_items=len(body.get('input', body.get('messages', []))))
                report['effective_effort'] = actual_effort
                if report['fallback_events'] and actual_effort != args.effort:
                    report['fallback_events'][-1].setdefault('fallback_attempt_id', attempt['attempt_id'])
                try:
                    payload, api = (anthropic.send_response(session, key, body, ledger, attempt) if is_opus else
                                    runner.send_response(session, key, body, ledger, attempt))
                    api['reasoning_effort'] = actual_effort
                    break
                except runner.UnsupportedEffort:
                    if args.model != 'astra' or actual_effort != 'max' or not args.effort_fallback:
                        raise
                    # Missing failure usage stays unresolved; never invent tokens.
                    ledger.update(attempt, 'effort_fallback')
                    report['fallback_events'].append({'attempt_id': attempt['attempt_id'],
                        'from_effort': 'max', 'to_effort': args.effort_fallback,
                        'reason': 'API explicitly rejected max reasoning effort'})
                    body['reasoning']['effort'] = args.effort_fallback
                    updated = json.loads(text)
                    updated['model_calls_remaining_including_this'] = args.max_decisions - len(ledger.attempts)
                    text = json.dumps(updated, allow_nan=False)
                    conversation.items[-1]['content'][0]['text'] = text
                    body['input'] = conversation.outgoing()
                    persist()
            if payload is None:
                if report['termination_reason'] == 'running':
                    report['termination_reason'] = 'decision_budget'
                break
            output = payload.get("output", [])
            if not isinstance(output, list):
                raise ValueError("Expected response output items")
            conversation.reply(payload['anthropic_content'] if is_opus else output)
            calls = [item for item in output if item.get("type") == "function_call"]
            record = {"decision_index": index, "input_video_frames": input_video_frames,
                      "image_jpeg_sha256_by_camera": image_hashes, "proprioception": proprio,
                      "observation_simulator_step": int(env.env.timestep), "executed_steps": 0, **api}
            report["decisions"].append(record)
            if len(calls) != 1:
                message = "Return exactly one tool call per turn; none of these motions was executed."
                for call in calls:
                    conversation.result(call["call_id"], {"error": message})
                if not calls:
                    conversation.nudge(message)
                consecutive_errors += 1
                report["tool_error_count"] += 1
                ledger.update(attempt, "tool_invalid", outcome="invalid_tool_call", error=message)
                if consecutive_errors >= 3:
                    report["termination_reason"] = "tool_errors"
                    break
                continue
            call = calls[0]
            record["tool_name"], record["tool_call_id"] = call.get("name"), call["call_id"]
            try:
                arguments = json.loads(call.get("arguments", ""))
                if call.get("name") in ("done", "give_up"):
                    field = "summary" if call["name"] == "done" else "reason"
                    if not isinstance(arguments, dict) or set(arguments) != {field, "hindsight"} or not all(isinstance(v, str) for v in arguments.values()):
                        raise MotionRejected("Stop tool requires {} and hindsight strings".format(field))
                    result = {"trial_ended": True, "declaration": call["name"]}
                    record.update(tool_arguments=arguments, tool_result=result)
                    conversation.result(call["call_id"], result)
                    report["hindsight"] = arguments["hindsight"]
                    report["termination_reason"] = "model_done" if call["name"] == "done" else "give_up"
                    ledger.update(attempt, "tool_valid", outcome="valid_tool_call")
                    break
                if call.get("name") != "move_to":
                    raise MotionRejected("Use move_to, done or give_up")
                target, waypoints = tools.plan(arguments, obs)
            except (ValueError, TypeError, KeyError) as error:
                result = {"error": str(error)}
                record["tool_result"] = result
                conversation.result(call["call_id"], result)
                report["tool_error_count"] += 1
                consecutive_errors += 1
                ledger.update(attempt, "tool_rejected", outcome="tool_rejected", error=str(error))
                if consecutive_errors >= 3:
                    report["termination_reason"] = "tool_errors"
                    break
                continue
            consecutive_errors = 0
            record["tool_arguments"] = arguments
            record["memory"] = arguments["note"]  # Backward-compatible readable note, never truncated.
            ledger.update(attempt, "tool_valid", outcome="valid_tool_call")
            stop_reason = None
            planned = len(waypoints)
            holds = min(5, max(0, tools.max_steps_per_move - planned))
            for waypoint in list(waypoints) + [target] * holds:
                if report["simulator_action_steps"] >= args.max_steps:
                    stop_reason = "step_budget"
                    break
                (obs, _, _, _), action = tools.step(waypoint)
                record["executed_steps"] += 1
                report["simulator_action_steps"] += 1
                report["executed_actions"].append({"simulator_step": int(env.env.timestep),
                    "decision_index": index, "absolute_waypoint": waypoint.tolist(), "native_action": action.tolist()})
                for name, rgb in camera_frames(obs, args).items():
                    runner.append_video(writers[name], rgb)
                report["success"] = bool(env.check_success())
                scorer.update(env.env.timestep)
                if report["success"]:
                    stop_reason = "success"
                    break
                if record["executed_steps"] >= planned and tools.result(target, obs, planned, record["executed_steps"])["pose_target_reached"]:
                    break
            result = tools.result(target, obs, planned, record["executed_steps"], stop_reason)
            record["tool_result"] = result
            record["private_trial_score"] = scorer.snapshot(report["success"])
            conversation.result(call["call_id"], result)
            print("{} call {}: move_to {}, {} steps, residual {:.4f}m".format(
                body["model"], index, arguments["targets"], record["executed_steps"], result["position_error_m"]), flush=True)
            persist()
            if stop_reason:
                report["termination_reason"] = stop_reason
                break
        else:
            report["termination_reason"] = "decision_budget"
        report["final_video_frames"] = runner.video_frame_references(
            report["video_files"], report["simulator_action_steps"], args.control_hz)
    except KeyboardInterrupt:
        report["termination_reason"] = "interrupted"
        raise
    except Exception as error:
        report["termination_reason"] = "error"
        report["error"] = str(error).replace(key, "[REDACTED]")
        raise
    finally:
        report["trial_score"] = scorer.snapshot(report["success"])
        report["trial_status"] = trial_status(report["termination_reason"])
        if conversation is not None:
            runner.write_json(args.outdir / "conversation.json", conversation.transcript())
        for writer in writers.values():
            writer.release()
        session.close()
        env.close()
        persist()
        print("Trial {}: completion={}%, calls={}, action_steps={}".format(report["trial_status"],
            report["trial_score"]["completion_percent"], report["decisions_used"], report["simulator_action_steps"]), flush=True)

"""Fixed Panda rig facts and feedback derived only from allowed robot sensors."""
import math

PROMPT_PROFILE = "calibrated-v2"
HISTORY_LENGTH = 3


def panda_rig_facts(env, orientation):
    """Read fixed controller/arena calibration, excluding objects and goal state."""
    simulator = env.env
    offset = next((getattr(simulator, key) for key in
                   ("kitchen_table_offset", "living_room_table_offset", "table_offset")
                   if hasattr(simulator, key)), None)
    if offset is None:
        return None  # Offline test doubles have no physical rig.
    controller = env.robots[0].controller
    facts = {"tabletop_world_z_m": float(offset[2]), "control_hz": float(simulator.control_freq),
             "translation_target_scale_m": controller.output_max[:3].tolist(),
             "rotation_target_scale_rad": controller.output_max[3:6].tolist(),
             "camera_orientation": orientation}
    # Both LoHo tabletop camera rigs have this axis convention. Check their fixed
    # camera rotation before publishing it, rather than guessing from an object.
    camera = env.sim.model.camera_name2id("agentview")
    matrix = env.sim.data.cam_xmat[camera].reshape(3, 3)
    if matrix[1, 0] > 0.99 and matrix[0, 1] < -0.1:
        horizontal = "left" if orientation == "rotate180" else "right"
        vertical = "up" if orientation == "raw" else "down"
        facts["camera_axes"] = ("Near the tabletop, +Y generally projects image-{} and +X image-{}. "
                                "The view is oblique; perspective and height change the apparent displacement."
                                .format(horizontal, vertical))
    return facts


def motion_feedback(before, after, action, executed_steps):
    """Tracking failure is a sensor-based warning, not an oracle contact verdict."""
    if before is None or after is None:
        return None
    start = before["end_effector_position_m"]
    end = after["end_effector_position_m"]
    delta = [round(b - a, 6) for a, b in zip(start, end)]
    moved = math.sqrt(sum(value * value for value in delta))
    command = math.sqrt(sum(value * value for value in action[:3]))
    stalled = command >= 0.1 and executed_steps > 0 and moved < 0.001
    return {"executed_steps": int(executed_steps), "eef_before_m": start,
            "eef_after_m": end, "observed_eef_delta_m": delta,
            "observed_translation_m": round(moved, 6),
            "gripper_after_m": after["gripper_joint_positions_m"],
            "translation_stalled": stalled,
            "interpretation": ("Translation requested but less than 1 mm achieved. Possible contact, reach limit "
                               "or tracking failure; re-check RGB and change the move."
                               if stalled else "Measured motion only; this does not verify a grasp or task progress.")}


def decision_context(report, observation_mode):
    history = []
    for record in report["decisions"][-HISTORY_LENGTH:]:
        item = {"decision_index": record["decision_index"], "action": record["action"],
                "executed_steps": record["executed_steps"]}
        if observation_mode == "rgb-proprio":
            item["motion_feedback"] = record.get("motion_feedback")
        history.append(item)
    context = {"decision_index": report["decisions_used"],
               "decisions_remaining_including_this": report["max_decisions"] - report["decisions_used"],
               "simulator_action_steps_used": report["simulator_action_steps"],
               "simulator_steps_remaining": report.get("max_action_steps", report["simulator_horizon"] - report["settle_steps"]) - report["simulator_action_steps"],
               "recent_executed_actions": history}
    if observation_mode == "rgb-proprio":
        context["consecutive_translation_stalls"] = report.get("consecutive_translation_stalls", 0)
    return context

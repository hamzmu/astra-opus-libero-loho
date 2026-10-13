"""Panda absolute-pose tool surface and native OSC waypoint execution."""
import math

import numpy as np
from scipy.spatial.transform import Rotation

LABELS = ("x", "y", "z", "roll", "pitch", "yaw", "gripper")
POSE_PROFILE = "pose-tools-v1"


class MotionRejected(ValueError):
    pass


class PoseTools:
    def __init__(self, env, speed_fraction=.25, max_duration_s=10):
        self.env = env
        self.robot = env.robots[0]
        self.hz = float(env.env.control_freq)
        self.speed_fraction = float(speed_fraction)
        if not 0 < self.speed_fraction <= .5:
            raise ValueError("speed_fraction must be in (0, 0.5]")
        self.max_steps_per_move = int(math.ceil(max_duration_s * self.hz))
        self.start_rotation = env.sim.data.site_xmat[self.robot.eef_site_id].reshape(3, 3).copy()
        simulator = env.env
        if hasattr(simulator, "kitchen_table_offset"):
            offset, size = simulator.kitchen_table_offset, simulator.kitchen_table_full_size
        elif hasattr(simulator, "living_room_table_offset"):
            offset, size = simulator.living_room_table_offset, simulator.living_room_table_full_size
        else:
            offset, size = simulator.table_offset, simulator.table_full_size
        self.table_z = float(offset[2])
        self.low = np.array([offset[0] - size[0] / 2, offset[1] - size[1] / 2,
                             self.table_z + .005, -math.pi / 2, -math.pi / 2, -math.pi, 0.])
        self.high = np.array([offset[0] + size[0] / 2, offset[1] + size[1] / 2,
                              self.table_z + .50, math.pi / 2, math.pi / 2, math.pi, 1.])
        self.step_limits = np.minimum((self.high - self.low) * self.speed_fraction / self.hz,
                                      (self.high - self.low) * .05)
        self.robot.controller.use_delta = False
        self.commanded = None

    def current(self, obs):
        rotation = self.env.sim.data.site_xmat[self.robot.eef_site_id].reshape(3, 3)
        angles = Rotation.from_matrix(rotation @ self.start_rotation.T).as_euler("xyz")
        fingers = np.asarray(obs["robot0_gripper_qpos"], dtype=float)
        opened = float(np.clip(np.mean(np.abs(fingers)) / .04, 0, 1))
        return np.concatenate((np.asarray(obs["robot0_eef_pos"], dtype=float), angles, [opened]))

    def readback(self, obs):
        return {key: round(float(value), 6) for key, value in zip(LABELS, self.current(obs))}

    def bounds(self):
        return {key: [float(low), float(high)] for key, low, high in zip(LABELS, self.low, self.high)}

    def schemas(self):
        properties = {key: {"type": "number", "description":
                           ("0 fully closed, 1 fully open" if key == "gripper" else
                            "World coordinate in meters" if key in ("x", "y", "z") else
                            "Radians relative to the trial start orientation")}
                      for key in LABELS}
        return [
            {"type": "function", "name": "move_to", "strict": False,
             "description": "Move to absolute named end-effector targets. Unnamed pose dimensions hold measured values; "
                            "an unnamed gripper preserves its last commanded opening to retain grasp pressure. "
                            "Motion is interpolated at 25% of dimension range per second, with a 5% per-step ceiling. "
                            "A move may last at most 10 seconds; split larger moves. Bounds: " + str(self.bounds()),
             "parameters": {"type": "object", "properties": {
                 "targets": {"type": "object", "properties": properties, "additionalProperties": False},
                 "note": {"type": "string", "description": "One or two sentences: what you see and why this move."}},
                 "required": ["targets", "note"], "additionalProperties": False}},
            {"type": "function", "name": "done", "strict": False,
             "description": "End the trial when you believe the task is complete. The evaluator determines success.",
             "parameters": {"type": "object", "properties": {
                 "summary": {"type": "string"}, "hindsight": {"type": "string"}},
                 "required": ["summary", "hindsight"], "additionalProperties": False}},
            {"type": "function", "name": "give_up", "strict": False,
             "description": "End an unsuccessful trial and explain the obstacle and what you learned.",
             "parameters": {"type": "object", "properties": {
                 "reason": {"type": "string"}, "hindsight": {"type": "string"}},
                 "required": ["reason", "hindsight"], "additionalProperties": False}},
        ]

    def plan(self, arguments, obs):
        if not isinstance(arguments, dict) or set(arguments) != {"targets", "note"}:
            raise MotionRejected("move_to requires exactly targets and note")
        values = arguments["targets"]
        if not isinstance(values, dict) or not values or not isinstance(arguments["note"], str) or not arguments["note"].strip():
            raise MotionRejected("Supply at least one named target and a nonempty note")
        current = self.current(obs)
        if self.commanded is not None:
            current[6] = self.commanded[6]
        target = current.copy()
        for key, value in values.items():
            if key not in LABELS or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise MotionRejected("Targets must use known dimension names and finite numeric values")
            index = LABELS.index(key)
            if not self.low[index] <= value <= self.high[index]:
                raise MotionRejected("{}={} is outside {}".format(key, value, self.bounds()[key]))
            target[index] = value
        steps = max(1, int(math.ceil(float(np.max(np.abs(target - current) / self.step_limits)) / (1 - 1e-6))))
        if steps > self.max_steps_per_move:
            raise MotionRejected("Move exceeds the 10-second playout cap; split it into smaller targets")
        waypoints = current + (target - current) * np.linspace(1 / steps, 1, steps)[:, None]
        waypoints[-1] = target
        return target, waypoints

    def step(self, waypoint):
        """Absolute xyz + world rotation vector; zero grip delta holds a direct finger target."""
        waypoint = np.asarray(waypoint, dtype=float)
        rotation = Rotation.from_euler("xyz", waypoint[3:6]).as_matrix() @ self.start_rotation
        rotvec = Rotation.from_matrix(rotation).as_rotvec()
        opened = float(waypoint[6])
        # PandaGripper.format_action integrates sign(action). Zero keeps this
        # explicit actuator target unchanged throughout the physics substeps.
        self.robot.gripper.current_action = np.array([2 * opened - 1, 1 - 2 * opened])
        self.commanded = waypoint.copy()
        action = np.concatenate((waypoint[:3], rotvec, [0.]))
        result = self.env.step(action)
        return result, action

    def result(self, target, obs, planned_steps, executed_steps, stop_reason=None):
        current = self.current(obs)
        requested_rotation = Rotation.from_euler("xyz", target[3:6]).as_matrix() @ self.start_rotation
        observed_rotation = self.env.sim.data.site_xmat[self.robot.eef_site_id].reshape(3, 3)
        position_error = float(np.linalg.norm(current[:3] - target[:3]))
        rotation_error = float(Rotation.from_matrix(requested_rotation @ observed_rotation.T).magnitude())
        return {"requested_targets": {key: float(value) for key, value in zip(LABELS, target)},
                "planned_steps": planned_steps, "executed_steps": executed_steps,
                "playout_seconds": executed_steps / self.hz,
                "playout_complete": executed_steps >= planned_steps,
                "stop_reason": stop_reason, "measured_pose": self.readback(obs),
                "position_error_m": round(position_error, 6), "rotation_error_rad": round(rotation_error, 6),
                "gripper_target_error_fraction": round(float(abs(current[6] - target[6])), 6),
                "pose_target_reached": position_error <= .003 and rotation_error <= .03,
                "feedback": "Readback is the measured result. A shortfall can mean contact, reach limit or tracking lag. "
                            "Do not repeat a blocked target. A partly closed gripper may hold an object or be obstructed; "
                            "verify the grasp visually after lifting."}

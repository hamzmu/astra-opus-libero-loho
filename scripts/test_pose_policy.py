"""Offline regressions for absolute pose planning and persistent tool context."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
from loho_pose_tools import PoseTools, MotionRejected
from loho_pose_policy import Conversation


class PoseTests(unittest.TestCase):
    def setUp(self):
        site = np.eye(3).reshape(1, 9)
        robot = SimpleNamespace(eef_site_id=0, controller=SimpleNamespace(use_delta=True), gripper=SimpleNamespace(current_action=None))
        self.actions = []
        env = SimpleNamespace(env=SimpleNamespace(control_freq=10, kitchen_table_offset=(0, 0, .9), kitchen_table_full_size=(1, 1.2, .05)),
            robots=[robot], sim=SimpleNamespace(data=SimpleNamespace(site_xmat=site)),
            step=lambda a: self.actions.append(a.copy()))
        self.tools = PoseTools(env)
        self.obs = {"robot0_eef_pos": np.array([-.2, 0, 1.17]), "robot0_gripper_qpos": np.array([.04, -.04])}

    def test_partial_absolute_target_holds_other_dimensions(self):
        target, waypoints = self.tools.plan({"targets": {"x": -.1}, "note": "Approach"}, self.obs)
        np.testing.assert_allclose(target[:3], [-.1, 0, 1.17])
        np.testing.assert_allclose(waypoints[-1], target)
        diffs = np.diff(np.vstack((self.tools.current(self.obs), waypoints)), axis=0)
        self.assertTrue(np.all(np.abs(diffs) <= self.tools.step_limits + 1e-10))

    def test_native_values_are_not_normalized_or_clipped(self):
        self.tools.step(np.array([-.1, .1, 1.2, 0, 0, 0, 0]))
        np.testing.assert_allclose(self.actions[0][:3], [-.1, .1, 1.2])
        self.assertFalse(self.tools.robot.controller.use_delta)
        np.testing.assert_allclose(self.tools.robot.gripper.current_action, [-1, 1])
        self.tools.step(np.array([-.1, .1, 1.2, 0, 0, 0, 1]))
        np.testing.assert_allclose(self.tools.robot.gripper.current_action, [1, -1])

    def test_invalid_targets_are_correctable_rejections(self):
        for values in [{"x": 99}, {"gripper": -1}, {"x": True}, {"x": float("nan")}, {"bogus": 0}]:
            with self.assertRaises(MotionRejected):
                self.tools.plan({"targets": values, "note": "test"}, self.obs)

    def test_lift_preserves_closed_command_despite_object_width_readback(self):
        self.tools.commanded = self.tools.current(self.obs)
        self.tools.commanded[6] = 0
        self.obs["robot0_gripper_qpos"] = np.array([.01, -.01])
        target, waypoints = self.tools.plan({"targets": {"z": 1.2}, "note": "lift held object"}, self.obs)
        self.assertEqual(target[6], 0)
        self.assertTrue(np.all(waypoints[:, 6] == 0))

    def test_tool_duration_cap_rejects_oversized_slow_move(self):
        self.tools.speed_fraction = .001
        self.tools.step_limits *= .004
        with self.assertRaises(MotionRejected):
            self.tools.plan({"targets": {"x": .4}, "note": "test"}, self.obs)

    def test_residual_uses_readback_not_requested_targets(self):
        target = self.tools.current(self.obs)
        target[0] += .03
        result = self.tools.result(target, self.obs, 2, 2)
        self.assertFalse(result["pose_target_reached"])
        self.assertAlmostEqual(result["position_error_m"], .03)
        self.assertTrue(result["playout_complete"])


class ContextTests(unittest.TestCase):
    def test_text_and_tool_history_persist_while_old_images_are_elided(self):
        c = Conversation("system")
        images = {"agentview": np.zeros((8, 8, 3), np.uint8), "robot0_eye_in_hand": np.ones((8, 8, 3), np.uint8)}
        c.observe("observation0", images)
        c.reply([{"type": "reasoning", "id": "r0", "summary": [], "encrypted_content": "opaque"},
                 {"type": "function_call", "call_id": "call0", "name": "move_to", "arguments": '{"targets":{"x":0},"note":"move"}'}])
        c.result("call0", {"position_error_m": .02})
        c.observe("observation1", images)
        c.observe("observation2", images)
        outgoing = c.outgoing()
        self.assertEqual(sum(part.get("type") == "input_image" for item in outgoing
                             for part in item.get("content", []) if isinstance(part, dict)), 4)
        self.assertIn("observation0", json.dumps(outgoing))
        self.assertTrue(any(item.get("encrypted_content") == "opaque" for item in outgoing))
        self.assertTrue(any(item.get("type") == "function_call_output" and item["call_id"] == "call0" for item in outgoing))
        saved = json.dumps(c.transcript())
        self.assertNotIn("encrypted_content", saved)
        self.assertNotIn("data:image", saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)

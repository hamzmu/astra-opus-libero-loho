"""Offline camera payload, pricing reservation and aggregation regressions."""
import base64
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_cameras import camera_frames, camera_names
from loho_telemetry import aggregate_episode_reports
from test_telemetry import FakeResponse, FakeSession, response_payload


class CaptureSession(FakeSession):
    def post(self, url, json, headers, timeout):
        self.body = json
        return super().post(url, json, headers, timeout)


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(cameras="agentview-wrist", orientation="rotate180",
            wrist_orientation="flip_vertical", resolution=256, observation="rgb-proprio",
            prompt_profile="calibrated-v2", model="luna", chunk=5, max_output_tokens=2048)
        self.images = {"agentview": np.full((256, 256, 3), [220, 15, 35], np.uint8),
                       "robot0_eye_in_hand": np.full((256, 256, 3), [20, 200, 55], np.uint8)}
        self.session = CaptureSession(FakeResponse(response_payload()))

    def test_two_labeled_rgb_images_and_hashes(self):
        _, metadata = runner.select_action(self.session, "offline-key", self.images,
                                           "task", "", self.args, {})
        content = self.session.body["input"][1]["content"]
        self.assertEqual([p["type"] for p in content],
                         ["input_text", "input_text", "input_image", "input_text", "input_image"])
        self.assertIn("agentview", content[1]["text"])
        self.assertIn("robot0_eye_in_hand", content[3]["text"])
        for item, expected in [(content[2], [220, 15, 35]), (content[4], [20, 200, 55])]:
            data = base64.b64decode(item["image_url"].split(",", 1)[1])
            decoded = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            np.testing.assert_allclose(decoded.mean(axis=(0, 1)), expected, atol=3)
        hashes = metadata["image_jpeg_sha256_by_camera"]
        self.assertEqual(set(hashes), set(self.images))
        self.assertNotEqual(hashes["agentview"], hashes["robot0_eye_in_hand"])

    def test_wrist_only_prompt_and_payload(self):
        self.args.cameras = "wrist"
        _, metadata = runner.select_action(self.session, "offline-key",
            {"robot0_eye_in_hand": self.images["robot0_eye_in_hand"]}, "task", "", self.args, {})
        system = self.session.body["input"][0]["content"]
        self.assertIn("ONE current RGB", system)
        self.assertIn("moving robot0_eye_in_hand wrist camera", system)
        self.assertIn("no fixed overview", system)
        self.assertEqual(set(metadata["image_jpeg_sha256_by_camera"]), {"robot0_eye_in_hand"})
        content = self.session.body["input"][1]["content"]
        self.assertEqual(sum(item["type"] == "input_image" for item in content), 1)
        self.assertIn("robot0_eye_in_hand", content[1]["text"])

    def test_raw_wrist_orientation_has_matching_edge_guidance(self):
        self.args.cameras = "wrist"
        self.args.wrist_orientation = "raw"
        self.assertIn("upper edge", runner.request_system_prompt(self.args))
        self.assertNotIn("lower edge", runner.request_system_prompt(self.args))

    def test_missing_or_invalid_wrist_image_sends_no_request(self):
        for images in [{"agentview": self.images["agentview"]},
                       dict(self.images, robot0_eye_in_hand=np.zeros((256, 256, 3), np.float64))]:
            with self.assertRaises(ValueError):
                runner.select_action(self.session, "offline-key", images, "task", "", self.args, {})
        self.assertEqual(self.session.client_ids, [])

    def test_camera_snapshot_rejects_missing_wrist(self):
        with self.assertRaises(ValueError):
            camera_frames({"agentview_image": self.images["agentview"]}, self.args)

    def test_legacy_camera_contract_and_payload_are_preserved(self):
        self.args.prompt_profile = "legacy-v1"
        with self.assertRaises(ValueError):
            camera_names(self.args)
        self.args.cameras = "agentview"
        self.args.observation = "rgb"
        runner.select_action(self.session, "offline-key", self.images["agentview"], "task", "", self.args)
        self.assertEqual([p["type"] for p in self.session.body["input"][1]["content"]], ["input_text", "input_image"])
        self.assertEqual(self.session.body["input"][0]["content"], runner.legacy_system_prompt(5, "rgb"))

    def test_camera_conditions_are_not_merged_in_aggregate(self):
        base = {"model_id": "gpt-6-luna", "task_id": 0, "success": False,
                "termination_reason": "decision_budget", "prompt_profile": "calibrated-v2"}
        reports = [dict(base, camera_configuration=value) for value in ["agentview", "wrist", "agentview-wrist"]]
        self.assertEqual(len(aggregate_episode_reports(reports)), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

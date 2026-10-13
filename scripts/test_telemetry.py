"""Regression tests for billed failed attempts; all API responses are offline."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import requests

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "src"))
import loho_frontier_eval as runner
from loho_telemetry import AttemptLedger, aggregate_episode_reports, price_attempt, read_attempt_journal, summarize_attempts

FAKE_KEY = "offline-secret-to-check-redaction"
USAGE = {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
         "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 250}, "total_tokens": 1300}
EXPECTED_COST = 0.0002345


def response_payload(text='{"action":[0,0,0,0,0,0,-1],"memory":"test"}', **fields):
    result = {"id": "offline-response", "model": "gpt-6-luna", "status": "completed",
              "service_tier": "default", "usage": copy.deepcopy(USAGE),
              "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
    result.update(fields)
    return result


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.ok = status < 400
        self.headers = {"x-request-id": "offline-server-request"}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response, expected_model="gpt-6-luna"):
        self.response = response
        self.expected_model = expected_model
        self.client_ids = []
        self.bodies = []

    def post(self, url, json, headers, timeout):
        assert url == "https://api.openai.com/v1/responses"
        assert json["model"] == self.expected_model
        assert json["service_tier"] == "default"
        self.client_ids.append(headers["X-Client-Request-Id"])
        self.bodies.append(copy.deepcopy(json))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self):
        pass


class FakeEnv:
    def __init__(self):
        self.env = SimpleNamespace(horizon=1000, timestep=5, done=False,
            parsed_problem={"goal_state": [["in", "FORBIDDEN_PRIVATE_OBJECT", "FORBIDDEN_PRIVATE_DRAWER"]]},
            _eval_predicate=lambda predicate: False)

    def observation(self):
        return {"agentview_image": np.zeros((256, 256, 3), np.uint8),
                "robot0_joint_pos": np.zeros(7), "robot0_joint_vel": np.zeros(7),
                "robot0_eef_pos": np.array([0, 0, .909]),
                "robot0_eef_quat": np.array([1, 0, 0, 0]),
                "robot0_gripper_qpos": np.array([.04, -.04]),
                "robot0_gripper_qvel": np.zeros(2)}

    def step(self, action):
        self.env.timestep += 1
        return self.observation(), 0, False, {}

    def check_success(self):
        return False

    def close(self):
        pass


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        (workspace / "setup_logs").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="telemetry_", dir=str(workspace / "setup_logs"))
        self.root = Path(self.directory.name).resolve()
        self.assertIn(workspace, self.root.parents)

    def tearDown(self):
        self.assertIn(workspace, self.root.resolve().parents)
        self.directory.cleanup()

    def run_episode(self, response, expected_error=None, model="luna",
                    max_decisions=1, expected_attempts=1, observation="rgb"):
        session = FakeSession(response, runner.MODEL_IDS[model])
        args = SimpleNamespace(task=0, initial_state=0, seed=0, resolution=256, observation=observation,
                               model=model,
                               orientation="rotate180", chunk=5, max_decisions=max_decisions, max_output_tokens=2048,
                               outdir=self.root)
        suite = SimpleNamespace(get_task_init_states=lambda task: [None],
                                get_task=lambda task: SimpleNamespace(language="offline task"))
        env = FakeEnv()
        writer = SimpleNamespace(release=lambda: None)
        patches = [patch.object(runner, "load_key", lambda: FAKE_KEY),
                   patch.object(runner, "make_env", lambda *unused: env),
                   patch.object(runner, "reset_episode", lambda *unused: env.observation()),
                   patch.object(runner, "video_writer", lambda *unused: writer),
                   patch.object(runner, "append_video", lambda *unused: None),
                   patch.object(runner, "save_frame", side_effect=AssertionError("Control must not write PNG frames")),
                   patch.object(requests, "Session", lambda: session)]
        for handle in patches:
            handle.start()
        try:
            if expected_error:
                with self.assertRaises(expected_error):
                    runner.control(args, suite, {"test": "offline telemetry regression"})
            else:
                runner.control(args, suite, {"test": "offline telemetry regression"})
        finally:
            for handle in reversed(patches):
                handle.stop()
        report = json.loads((self.root / "summary.json").read_text())
        self.assertEqual(report["media_mode"], "video_only")
        self.assertFalse(report["png_frames_saved"])
        self.assertFalse(list(self.root.glob("*.png")))
        for decision in report["decisions"]:
            frame = decision["input_video_frames"]["agentview"]
            self.assertEqual(frame["frame_index"], decision["observation_simulator_step"] - report["settle_steps"])
        self.sent_bodies = session.bodies
        attempts, _ = read_attempt_journal(self.root / "api_attempts.jsonl")
        self.assertEqual(len(attempts), expected_attempts)
        if attempts:
            self.assertEqual(attempts[0]["attempt_id"], session.client_ids[0])
        self.assertNotIn(FAKE_KEY, (self.root / "api_attempts.jsonl").read_text())
        return report, attempts[0] if attempts else None

    def assert_known_failure_cost(self, report, attempt, outcome):
        self.assertEqual(attempt["outcome"], outcome)
        self.assertEqual(report["termination_reason"], "error")
        self.assertEqual(report["simulator_action_steps"], 0)
        self.assertEqual(report["total_input_tokens"], 1000)
        self.assertEqual(report["total_output_tokens"], 300)
        self.assertEqual(report["api_attempts_total"], 1)
        self.assertTrue(report["cost_complete"])
        self.assertAlmostEqual(report["estimated_api_cost_usd"], EXPECTED_COST)

    def test_valid_response_is_counted_once(self):
        report, attempt = self.run_episode(FakeResponse(response_payload()))
        self.assertEqual(attempt["outcome"], "valid_action")
        self.assertEqual(report["simulator_action_steps"], 5)
        self.assertEqual(report["decisions_used"], 1)
        self.assertAlmostEqual(report["estimated_api_cost_usd"], EXPECTED_COST)
        self.assertEqual(report["total_output_tokens"], 300)  # Includes reasoning; don't add 250 again.

    def test_second_request_receives_measured_stall_without_private_goal_score(self):
        payload = response_payload(text='{"action":[0,0,-0.5,0,0,0,-1],"memory":"retry alignment"}')
        report, _ = self.run_episode(FakeResponse(payload), max_decisions=2,
                                     expected_attempts=2, observation="rgb-proprio")
        self.assertEqual(report["trial_score"]["completion_percent"], 0)
        self.assertEqual(report["translation_stall_count"], 2)
        self.assertEqual(report["trial_status"], "budget_exhausted")
        text = self.sent_bodies[1]["input"][1]["content"][0]["text"]
        context = json.loads(text.splitlines()[-1])
        self.assertEqual(context["consecutive_translation_stalls"], 1)
        self.assertTrue(context["recent_executed_actions"][0]["motion_feedback"]["translation_stalled"])
        self.assertNotIn("FORBIDDEN_PRIVATE", json.dumps(self.sent_bodies))
        self.assertNotIn("private_trial_score", json.dumps(self.sent_bodies))

    def test_astra_dispatch_uses_astra_prices(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(model="gpt-6-astra")), model="astra")
        self.assertEqual(report["model_id"], "gpt-6-astra")
        self.assertEqual(report["pricing"]["model"], "gpt-6-astra")
        self.assertEqual(attempt["requested_model"], "gpt-6-astra")
        self.assertAlmostEqual(report["estimated_api_cost_usd"], EXPECTED_COST * 100)

    def test_wrong_model_pricing_is_rejected(self):
        args = SimpleNamespace(model="astra", pricing_file=runner.DEFAULT_PRICING)
        with self.assertRaises(ValueError):
            runner.model_pricing(args)

    def test_spend_above_old_cap_does_not_stop_next_request(self):
        usage = {"input_tokens": 3000000, "output_tokens": 100000,
                 "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}
        report, attempt = self.run_episode(FakeResponse(response_payload(usage=usage, model="gpt-6-astra")),
                                           model="astra", max_decisions=2, expected_attempts=2)
        self.assertGreater(attempt["estimated_api_cost_usd"], 25)
        self.assertGreater(report["estimated_api_cost_usd"], 50)
        self.assertEqual(report["termination_reason"], "decision_budget")
        self.assertEqual(report["simulator_action_steps"], 10)
        self.assertIsNone(report["max_estimated_api_cost_usd"])
        self.assertFalse(report["cost_guard_enabled"])
        self.assertNotIn("next_request_cost_reservation_usd", report)

    def test_missing_usage_stays_unresolved_without_stopping_next_request(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(usage=None)),
                                           max_decisions=2, expected_attempts=2)
        self.assertEqual(report["termination_reason"], "decision_budget")
        self.assertEqual(report["api_attempts_total"], 2)
        self.assertEqual(report["api_attempts_unresolved_cost"], 2)
        self.assertFalse(report["cost_complete"])
        self.assertIsNone(report["estimated_api_cost_usd"])

    def test_incomplete_reply_usage_is_retained(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(status="incomplete",
                            incomplete_details={"reason": "max_output_tokens"})), RuntimeError)
        self.assert_known_failure_cost(report, attempt, "incomplete")
        self.assertEqual(report["decisions_used"], 0)

    def test_invalid_json_usage_is_retained(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(text='{"action":[')), ValueError)
        self.assert_known_failure_cost(report, attempt, "invalid_json")

    def test_invalid_action_usage_is_retained(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(text='{"action":[0,0],"memory":"bad"}')), ValueError)
        self.assert_known_failure_cost(report, attempt, "invalid_action")
        self.assertEqual(report["invalid_action_count"], 1)

    def test_http_error_reported_usage_is_retained(self):
        report, attempt = self.run_episode(FakeResponse(response_payload(status="failed",
                         error={"code": "test", "message": FAKE_KEY}), status=500), RuntimeError)
        self.assert_known_failure_cost(report, attempt, "api_error")
        self.assertEqual(attempt["http_status"], 500)

    def test_refusal_reported_usage_is_retained(self):
        payload = response_payload(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "test"}]}])
        report, attempt = self.run_episode(FakeResponse(payload), RuntimeError)
        self.assert_known_failure_cost(report, attempt, "refusal")

    def test_timeout_cost_is_unresolved_not_zero(self):
        report, attempt = self.run_episode(requests.exceptions.ReadTimeout("offline timeout"), requests.exceptions.ReadTimeout)
        self.assertEqual(attempt["outcome"], "timeout")
        self.assertFalse(report["cost_complete"])
        self.assertIsNone(report["estimated_api_cost_usd"])
        self.assertEqual(report["api_attempts_unknown_usage"], 1)
        self.assertIsNotNone(attempt["api_latency_seconds"])

    def test_http_error_without_usage_is_unresolved(self):
        payload = {"error": {"code": "rate_limit", "message": "offline"}}
        report, attempt = self.run_episode(FakeResponse(payload, status=429), RuntimeError)
        self.assertFalse(report["cost_complete"])
        self.assertIsNone(attempt["estimated_api_cost_usd"])

    def test_pending_request_survives_journal_replay(self):
        ledger = AttemptLedger(self.root / "api_attempts.jsonl")
        ledger.begin(0, "gpt-6-luna", "default")
        attempts, pricing = read_attempt_journal(ledger.path)
        self.assertEqual(pricing["model"], "gpt-6-luna")
        summary = summarize_attempts(attempts)
        self.assertEqual(summary["api_attempts_unknown_usage"], 1)
        self.assertIsNone(summary["estimated_api_cost_usd"])

    def test_bad_pricing_is_rejected_before_any_request(self):
        pricing = copy.deepcopy(AttemptLedger().pricing)
        pricing["rates_per_million_tokens"]["default"]["short"]["output"] = float("nan")
        with self.assertRaises(ValueError):
            AttemptLedger(self.root / "api_attempts.jsonl", pricing=pricing)
        self.assertFalse((self.root / "api_attempts.jsonl").exists())

    def test_actual_tier_and_long_context_rates(self):
        pricing = AttemptLedger().pricing
        attempt = {"usage": copy.deepcopy(USAGE), "requested_model": "gpt-6-luna",
                   "requested_service_tier": "default", "returned_service_tier": "priority"}
        self.assertAlmostEqual(price_attempt(attempt, pricing)[0], EXPECTED_COST * 2)
        attempt["usage"]["input_tokens"] = 272001
        self.assertAlmostEqual(price_attempt(attempt, pricing)[0],
                               ((272001 - 300) * 0.4 + 200 * 0.04 + 100 * 0.5 + 300 * 1.5) / 1000000)

    def test_aggregate_includes_failed_episode_cost(self):
        base = {"model_id": "gpt-6-luna", "observation_mode": "rgb-proprio", "task_id": 0,
                "success": True, "termination_reason": "success", "cost_complete": True,
                "known_estimated_api_cost_usd": EXPECTED_COST, "api_attempts_total": 1,
                "total_input_tokens": 1000, "total_output_tokens": 300, "total_api_latency_seconds": 2}
        failed = dict(base, success=False, termination_reason="error")
        group = aggregate_episode_reports([base, failed])[0]
        self.assertAlmostEqual(group["estimated_api_cost_usd"], 2 * EXPECTED_COST)
        self.assertEqual(group["successful_episodes"], 1)
        self.assertEqual(group["error_episodes"], 1)
        self.assertEqual(group["api_attempts_total"], 2)
        unknown = dict(failed, cost_complete=False, known_estimated_api_cost_usd=0)
        group = aggregate_episode_reports([base, failed, unknown])[0]
        self.assertIsNone(group["estimated_api_cost_usd"])
        self.assertAlmostEqual(group["known_estimated_api_cost_usd"], 2 * EXPECTED_COST)
        legacy = dict(unknown, api_attempts_total=None, known_api_attempts_total=5,
                      attempt_coverage_complete=False)
        group = aggregate_episode_reports([base, legacy])[0]
        self.assertIsNone(group["api_attempts_total"])
        self.assertEqual(group["known_api_attempts_total"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)

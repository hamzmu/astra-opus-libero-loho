"""Offline regressions for score semantics, prompt feedback and oracle exclusion."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace))
import loho_frontier_eval as runner
from loho_control_feedback import decision_context, motion_feedback
from loho_scoring import GoalScorer, trial_status
from loho_telemetry import aggregate_episode_reports


def state(position):
    return {"end_effector_position_m": position, "gripper_joint_positions_m": [0.04, -0.04]}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.values = [False, False, False]
        predicates = [["in", "butter", "drawer"], ["in", "pudding", "drawer"], ["close", "drawer"]]
        sim = SimpleNamespace(parsed_problem={"goal_state": predicates},
                              _eval_predicate=lambda p: self.values[predicates.index(p)])
        self.scorer = GoalScorer(SimpleNamespace(env=sim))

    def test_lost_goal_loses_final_credit_and_peak_is_simultaneous(self):
        self.scorer.update(5)
        self.assertEqual(self.scorer.snapshot(False)["completion_percent"], 0)
        self.values[:] = [True, False, False]
        self.scorer.update(10)
        self.assertAlmostEqual(self.scorer.snapshot(False)["completion_percent"], 100 / 3)
        self.values[:] = [False, True, False]
        self.scorer.update(15)
        score = self.scorer.snapshot(False)
        self.assertAlmostEqual(score["completion_percent"], 100 / 3)
        self.assertAlmostEqual(score["peak_simultaneous_completion_percent"], 100 / 3)
        self.assertTrue(score["goals"][0]["ever_satisfied"])
        self.assertFalse(score["goals"][0]["satisfied"])
        self.values[:] = [False, False, False]
        self.scorer.update(20)
        self.assertEqual(self.scorer.snapshot(False)["completion_percent"], 0)

    def test_full_completion_requires_all_goals_and_success_agreement(self):
        self.values[:] = [True, True, True]
        self.scorer.update(10)
        self.assertEqual(self.scorer.snapshot(True)["completion_percent"], 100)
        with self.assertRaises(ValueError):
            self.scorer.snapshot(False)

    def test_unavailable_scores_remain_unknown(self):
        scorer = GoalScorer(SimpleNamespace(env=SimpleNamespace()))
        scorer.update(5)
        self.assertIsNone(scorer.snapshot(False)["completion_percent"])

    def test_interrupted_and_budget_trials_are_distinct(self):
        self.assertEqual(trial_status("interrupted"), "interrupted")
        self.assertEqual(trial_status("decision_budget"), "budget_exhausted")
        self.assertEqual(trial_status("success"), "task_completed")

    def test_aggregation_separates_prompt_profiles_and_missing_scores(self):
        base = {"model_id": "gpt-6-luna", "task_id": 0, "success": False,
                "termination_reason": "decision_budget", "cost_complete": True,
                "trial_score": {"available": True, "completion_percent": 100 / 3,
                                "peak_simultaneous_completion_percent": 200 / 3}}
        unknown = dict(base, trial_score={"available": False})
        changed = dict(base, prompt_profile="calibrated-v2")
        groups = aggregate_episode_reports([base, unknown, changed])
        self.assertEqual(len(groups), 2)
        legacy = next(g for g in groups if g["prompt_profile"] == "legacy-v1")
        self.assertEqual(legacy["unscored_episodes"], 1)
        self.assertAlmostEqual(legacy["mean_goal_completion_percent"], 100 / 3)
        self.assertEqual(legacy["full_task_completions"], 0)

    def test_aggregation_separates_episode_budgets(self):
        base = {"model_id": "gpt-6-astra", "task_id": 0, "prompt_profile": "pose-tools-v1",
                "max_decisions": 40, "max_action_steps": 900, "success": False,
                "termination_reason": "step_budget", "cost_complete": True}
        longer = dict(base, max_decisions=80, max_action_steps=2000)
        more_steps = dict(base, max_action_steps=2000)
        unknown = dict(base)
        unknown.pop("max_decisions")
        unknown.pop("max_action_steps")
        groups = aggregate_episode_reports([base, base, longer, more_steps, unknown])
        self.assertEqual(len(groups), 4)
        old = next(g for g in groups if g["max_decisions"] == 40 and g["max_action_steps"] == 900)
        self.assertEqual(old["episodes"], 2)
        self.assertEqual(next(g for g in groups if g["max_decisions"] == 80)["episodes"], 1)


class FeedbackTests(unittest.TestCase):
    def test_stall_requires_translation_command_and_little_measured_motion(self):
        command = [0, 0, -0.5, 0, 0, 0, -1]
        result = motion_feedback(state([0, 0, .909]), state([0, 0, .90899]), command, 5)
        self.assertTrue(result["translation_stalled"])
        self.assertIn("Possible", result["interpretation"])
        self.assertFalse(motion_feedback(state([0, 0, 1]), state([0, 0, .98]), command, 5)["translation_stalled"])
        self.assertFalse(motion_feedback(state([0, 0, 1]), state([0, 0, 1]), [0, 0, 0, 0, 0, 0, 1], 5)["translation_stalled"])

    def test_history_excludes_private_score_and_limits_length(self):
        records = [{"decision_index": i, "action": [0, 0, -.5, 0, 0, 0, -1],
                    "executed_steps": 5, "private_trial_score": "FORBIDDEN_ORACLE",
                    "proprioception": {"objects": "FORBIDDEN_ORACLE"},
                    "motion_feedback": motion_feedback(state([0, 0, .909]), state([0, 0, .909]),
                                                       [0, 0, -.5, 0, 0, 0, -1], 5)} for i in range(5)]
        report = {"decisions": records, "decisions_used": 5, "max_decisions": 74,
                  "simulator_action_steps": 25, "simulator_horizon": 1000, "settle_steps": 5}
        context = decision_context(report, "rgb-proprio")
        self.assertEqual(len(context["recent_executed_actions"]), 3)
        self.assertEqual(context["recent_executed_actions"][0]["decision_index"], 2)
        self.assertNotIn("FORBIDDEN", json.dumps(context))
        rgb = json.dumps(decision_context(report, "rgb"))
        self.assertNotIn("eef_before", rgb)
        self.assertNotIn("gripper_after", rgb)

    def test_updated_prompt_contains_calibration_and_recovery_with_legacy_available(self):
        prompt = runner.system_prompt(5, "rgb-proprio", rig_facts={"tabletop_world_z_m": .9})
        self.assertIn('"tabletop_world_z_m":0.9', prompt)
        self.assertIn("0.05 m", prompt)
        self.assertIn("After two", prompt)
        self.assertIn("check visually", prompt)
        self.assertEqual(runner.system_prompt(5, "rgb", "legacy-v1"), runner.legacy_system_prompt(5, "rgb"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

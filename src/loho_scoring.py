"""Private LIBERO goal scoring; never include these results in model inputs."""
import copy

RUBRIC_ID = "libero_loho_goal_predicates_v1"
FINISHED_REASONS = {"success", "decision_budget", "cost_budget", "horizon", "step_budget", "model_done", "give_up", "tool_errors"}


def trial_status(reason):
    if reason == "success":
        return "task_completed"
    if reason in {"decision_budget", "cost_budget", "horizon", "step_budget"}:
        return "budget_exhausted"
    if reason == "model_done":
        return "model_declared_done"
    if reason in {"give_up", "tool_errors"}:
        return reason
    return reason if reason in {"interrupted", "error", "running", "cost_unresolved"} else "unknown"


class GoalScorer:
    """Equal weight for each actual final predicate, with transient peaks separate."""

    def __init__(self, env):
        self.env = env
        simulator = env.env
        self.predicates = copy.deepcopy(getattr(simulator, "parsed_problem", {}).get("goal_state", []))
        self.available = bool(self.predicates) and callable(getattr(simulator, "_eval_predicate", None))
        self.initial = None
        self.current = []
        self.ever = [False] * len(self.predicates)
        self.first_satisfied_step = [None] * len(self.predicates)
        self.peak = 0
        self.last_step = None

    def update(self, step):
        if not self.available:
            return
        current = [bool(self.env.env._eval_predicate(predicate)) for predicate in self.predicates]
        if self.initial is None:
            self.initial = current[:]
        self.current = current
        self.last_step = int(step)
        for i, satisfied in enumerate(current):
            if satisfied and not self.ever[i]:
                self.first_satisfied_step[i] = int(step)
            self.ever[i] |= satisfied
        self.peak = max(self.peak, sum(current))

    def snapshot(self, success):
        if not self.available or self.initial is None:
            return {"available": False, "rubric_id": RUBRIC_ID,
                    "task_complete": bool(success), "completion_percent": None}
        count = len(self.predicates)
        # A 100% final goal score must agree with the simulator's full-success check.
        if all(self.current) != bool(success):
            raise ValueError("Goal predicate score disagrees with the simulator success check")
        return {"available": True, "rubric_id": RUBRIC_ID,
                "method": "Equal-weight final BDDL goal predicates; no credit for arm motion alone.",
                "task_complete": bool(success), "goals_total": count,
                "goals_satisfied": sum(self.current), "completion_fraction": sum(self.current) / count,
                "completion_percent": 100 * sum(self.current) / count,
                "initial_completion_percent": 100 * sum(self.initial) / count,
                "peak_simultaneous_completion_percent": 100 * self.peak / count,
                "last_scored_simulator_step": self.last_step,
                "goals": [{"predicate": predicate, "label": " ".join(predicate),
                           "initially_satisfied": self.initial[i], "satisfied": self.current[i],
                           "ever_satisfied": self.ever[i], "first_satisfied_step": self.first_satisfied_step[i]}
                          for i, predicate in enumerate(self.predicates)]}

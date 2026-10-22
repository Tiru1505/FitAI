import pytest

from app.services.adaptive_coach import (
    CoachConfig, ExercisePerformance, compute_session_score, decide_adaptations, persistent_errors,
)  # fmt: skip
from app.services.recommender_service import Prescription

CFG = CoachConfig()


def rx(slug="squat", day=0, sets=3, reps=10, rest=60, practice=False):
    return Prescription(slug, day, 0, sets, reps, rest, "", practice)


def perf(slug="squat", completion=1.0, form=0.9, difficulty=3, errors=None):
    return ExercisePerformance(slug, completion, form, difficulty, errors or [])


def decide(prescriptions, performances, day=0, missed=0, shortened=False):
    return decide_adaptations(prescriptions, performances, day, missed, shortened, CFG)


def test_session_score_uses_configured_weights():
    s = compute_session_score(1.0, 0.5, 0.8, 3, CFG)
    assert s.session_score == pytest.approx(0.35 * 1.0 + 0.35 * 0.5 + 0.15 * 0.8 + 0.15 * 1.0)


def test_session_score_renormalises_without_form_score():
    s = compute_session_score(1.0, None, 1.0, 3, CFG)
    assert s.session_score == pytest.approx(1.0)
    assert "form_score" not in s.weights_used
    assert sum(s.weights_used.values()) == pytest.approx(1.0, abs=1e-3)


def test_high_completion_and_high_form_progresses_reps():
    out = decide([rx()], [perf(completion=0.95, form=0.9)])
    assert out.prescriptions[0].repetitions == 12
    assert out.decisions[0].action == "progress"
    assert out.changed


def test_high_completion_low_form_keeps_difficulty_and_gives_guidance():
    out = decide([rx()], [perf(completion=1.0, form=0.4)])
    assert out.prescriptions[0].repetitions == 10
    assert out.decisions[0].action == "hold_technique"
    assert not out.changed
    assert out.guidance


def test_low_completion_high_difficulty_regresses():
    out = decide([rx(reps=10, rest=60)], [perf(completion=0.4, form=0.7, difficulty=5)])
    p = out.prescriptions[0]
    assert (p.repetitions, p.rest_seconds) == (8, 75)
    assert out.decisions[0].action == "regress"


def test_regression_respects_minimum_reps():
    out = decide([rx(reps=5)], [perf(completion=0.2, difficulty=5)])
    assert out.prescriptions[0].repetitions == CFG.min_reps


def test_progression_respects_maximum_reps():
    out = decide([rx(reps=CFG.max_reps)], [perf()])
    assert out.prescriptions[0].repetitions == CFG.max_reps


def test_persistent_form_errors_enable_practice_mode():
    errors = [{"knees_caving"}, {"knees_caving", "forward_lean"}, {"knees_caving"}]
    out = decide([rx()], [perf(form=0.3, errors=errors)])
    assert out.prescriptions[0].practice_mode is True
    assert out.decisions[0].action == "practice_mode"


def test_non_persistent_errors_do_not_trigger_practice_mode():
    assert persistent_errors([{"a"}, {"b"}, {"a"}], 3) == set()
    assert persistent_errors([{"a"}, {"a"}], 3) == set()  # not enough history


def test_repeated_missed_sessions_shorten_plan_once():
    plan = [rx(day=0, sets=3), rx("push_up", day=1, sets=1)]
    out = decide(plan, [], missed=2)
    assert [p.sets for p in out.prescriptions] == [2, 1]
    assert any(d.action == "shorten" for d in out.decisions)
    again = decide(plan, [], missed=2, shortened=True)
    assert not any(d.action == "shorten" for d in again.decisions)


def test_only_exercises_from_the_session_day_are_adapted():
    plan = [rx("squat", day=0), rx("squat", day=1)]
    out = decide(plan, [perf("squat")], day=0)
    assert out.prescriptions[0].repetitions == 12
    assert out.prescriptions[1].repetitions == 10


def test_input_prescriptions_are_not_mutated():
    plan = [rx()]
    decide(plan, [perf()])
    assert plan[0].repetitions == 10

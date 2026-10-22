"""Transparent, score-based adaptive coaching (version one: no reinforcement learning).

session_score = w_c * completion_rate + w_f * form_score
              + w_s * consistency_score + w_d * difficulty_adjustment

The weights and every threshold come from ``Settings`` and are configurable
project parameters, not medically validated values.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.core.config import Settings
from app.services.recommender_service import Prescription

# Perceived difficulty (1 = very easy ... 5 = very hard) -> adjustment score.
DIFFICULTY_ADJUSTMENT = {1: 0.6, 2: 0.85, 3: 1.0, 4: 0.6, 5: 0.3}


@dataclass(frozen=True)
class CoachConfig:
    weight_completion: float = 0.35
    weight_form: float = 0.35
    weight_consistency: float = 0.15
    weight_difficulty: float = 0.15
    high_completion: float = 0.90
    low_completion: float = 0.60
    high_form: float = 0.80
    low_form: float = 0.60
    high_difficulty: int = 4
    easy_difficulty: int = 2
    missed_sessions_threshold: int = 2
    persistent_error_sessions: int = 3
    rep_increment: int = 2
    rep_decrement: int = 2
    rest_increment_seconds: int = 15
    min_reps: int = 4
    max_reps: int = 25
    max_rest_seconds: int = 180

    @classmethod
    def from_settings(cls, s: Settings) -> "CoachConfig":
        return cls(
            s.score_weight_completion, s.score_weight_form, s.score_weight_consistency, s.score_weight_difficulty,
            s.coach_high_completion, s.coach_low_completion, s.coach_high_form, s.coach_low_form,
            s.coach_high_difficulty, s.coach_easy_difficulty, s.coach_missed_sessions_threshold,
            s.coach_persistent_error_sessions, s.coach_rep_increment, s.coach_rep_decrement,
            s.coach_rest_increment_seconds, s.coach_min_reps, s.coach_max_reps, s.coach_max_rest_seconds,
        )  # fmt: skip


@dataclass
class ScoreBreakdown:
    completion_rate: float
    form_score: float | None
    consistency_score: float
    difficulty_adjustment: float
    session_score: float
    weights_used: dict[str, float]


def difficulty_adjustment(perceived_difficulty: int | None) -> float:
    return DIFFICULTY_ADJUSTMENT.get(perceived_difficulty or 3, 1.0)


def compute_session_score(
    completion_rate: float,
    form_score: float | None,
    consistency_score: float,
    perceived_difficulty: int | None,
    config: CoachConfig,
) -> ScoreBreakdown:
    """If no form score exists (e.g. manually logged session) the remaining weights are renormalised."""
    diff = difficulty_adjustment(perceived_difficulty)
    parts = {
        "completion_rate": (config.weight_completion, completion_rate),
        "consistency_score": (config.weight_consistency, consistency_score),
        "difficulty_adjustment": (config.weight_difficulty, diff),
    }
    if form_score is not None:
        parts["form_score"] = (config.weight_form, form_score)
    total_weight = sum(w for w, _ in parts.values())
    score = sum(w * v for w, v in parts.values()) / total_weight
    return ScoreBreakdown(
        completion_rate=round(completion_rate, 4),
        form_score=round(form_score, 4) if form_score is not None else None,
        consistency_score=round(consistency_score, 4),
        difficulty_adjustment=diff,
        session_score=round(score, 4),
        weights_used={k: round(w / total_weight, 4) for k, (w, _) in parts.items()},
    )


@dataclass
class ExercisePerformance:
    exercise_slug: str
    completion_rate: float
    form_score: float | None
    difficulty_rating: int | None
    # Error codes from the most recent results for this exercise, newest first (including this session).
    recent_error_sets: list[set[str]] = field(default_factory=list)


@dataclass
class AdaptationDecision:
    exercise_slug: str | None
    action: str
    reason: str
    changes: dict = field(default_factory=dict)


@dataclass
class AdaptationOutcome:
    prescriptions: list[Prescription]
    decisions: list[AdaptationDecision]
    guidance: list[str]

    @property
    def changed(self) -> bool:
        return any(d.changes for d in self.decisions)


def persistent_errors(recent_error_sets: list[set[str]], sessions: int) -> set[str]:
    if len(recent_error_sets) < sessions:
        return set()
    window = recent_error_sets[:sessions]
    common = set(window[0])
    for errors in window[1:]:
        common &= errors
    return {e for e in common if e != "insufficient_range"} or (common & {"insufficient_range"})


def decide_adaptations(
    prescriptions: list[Prescription],
    performances: list[ExercisePerformance],
    session_day_index: int | None,
    missed_sessions: int,
    recently_shortened: bool,
    config: CoachConfig,
) -> AdaptationOutcome:
    """Apply the rule table to the exercises performed on ``session_day_index``."""
    new = [replace(p) for p in prescriptions]
    decisions: list[AdaptationDecision] = []
    guidance: list[str] = []
    perf_by_slug = {p.exercise_slug: p for p in performances}

    for rx in new:
        if session_day_index is not None and rx.day_index != session_day_index:
            continue
        perf = perf_by_slug.get(rx.exercise_slug)
        if perf is None:
            continue
        name = rx.exercise_slug.replace("_", " ")
        before = {"sets": rx.sets, "repetitions": rx.repetitions, "rest_seconds": rx.rest_seconds, "practice_mode": rx.practice_mode}
        persistent = persistent_errors(perf.recent_error_sets, config.persistent_error_sessions)
        hi_c = perf.completion_rate >= config.high_completion
        lo_c = perf.completion_rate < config.low_completion
        form = perf.form_score
        hard = (perf.difficulty_rating or 0) >= config.high_difficulty

        if persistent:
            action = "practice_mode"
            if not rx.practice_mode:
                rx.practice_mode = True
                rx.notes = "Practice mode: slow tempo and focus on technique before adding load or reps."
            reason = (
                f"The same form issue ({', '.join(sorted(persistent))}) appeared in the last "
                f"{config.persistent_error_sessions} {name} results, so practice mode was added."
            )
            guidance.append(f"Review the technique cues for {name} before your next workout.")
        elif hi_c and form is not None and form >= config.high_form:
            action = "progress"
            rx.repetitions = min(config.max_reps, rx.repetitions + config.rep_increment)
            if rx.practice_mode:
                rx.practice_mode, rx.notes = False, ""
            reason = f"High completion ({perf.completion_rate:.0%}) and good form ({form:.0%}) on {name}: repetitions increased."
        elif hi_c and form is not None and form < config.low_form:
            action = "hold_technique"
            reason = f"You completed {name} but form score was {form:.0%}: difficulty kept stable to focus on technique."
            guidance.append(f"Technique focus for {name}: follow the form cues and slow the movement down.")
        elif hi_c and form is None and (perf.difficulty_rating or 3) <= config.easy_difficulty:
            action = "progress"
            rx.repetitions = min(config.max_reps, rx.repetitions + config.rep_increment)
            reason = f"High completion on {name} rated easy (no live form data): repetitions increased."
        elif lo_c and hard:
            action = "regress"
            rx.repetitions = max(config.min_reps, rx.repetitions - config.rep_decrement)
            rx.rest_seconds = min(config.max_rest_seconds, rx.rest_seconds + config.rest_increment_seconds)
            reason = (
                f"Low completion ({perf.completion_rate:.0%}) with high reported difficulty on {name}: "
                "repetitions reduced and rest increased."
            )
        else:
            action = "maintain"
            reason = f"No rule triggered for {name}: prescription kept the same."

        after = {"sets": rx.sets, "repetitions": rx.repetitions, "rest_seconds": rx.rest_seconds, "practice_mode": rx.practice_mode}
        changes = {k: {"from": before[k], "to": after[k]} for k in before if before[k] != after[k]}
        decisions.append(AdaptationDecision(rx.exercise_slug, action, reason, changes))

    if missed_sessions >= config.missed_sessions_threshold and not recently_shortened:
        shortened = {}
        for rx in new:
            if rx.sets > 1:
                shortened[f"{rx.exercise_slug}@day{rx.day_index}"] = {"from": rx.sets, "to": rx.sets - 1}
                rx.sets -= 1
        decisions.append(
            AdaptationDecision(
                None,
                "shorten",
                f"{missed_sessions} planned sessions were missed in the last 7 days: sessions shortened by one set per exercise.",
                shortened,
            )
        )
        guidance.append("Consistency reminder: shorter sessions you can complete regularly beat long sessions you skip.")

    return AdaptationOutcome(new, decisions, guidance)

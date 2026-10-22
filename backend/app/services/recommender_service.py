"""Stage 1 workout recommender: an explainable, rule-based baseline.

Every decision appends a human-readable reason so the generated plan can be
explained to the user (and defended in a project review). A machine-learning
recommender (``ml/scripts/train_recommender.py``) can be compared against this
baseline, but the baseline remains the default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SCHEDULES = {
    1: [2],
    2: [0, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 4],
    5: [0, 1, 2, 3, 4],
    6: [0, 1, 2, 3, 4, 5],
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Exercise priority when a session must be shortened (earlier = kept first).
PRIORITY = ["squat", "push_up", "lunge", "shoulder_press", "biceps_curl"]
UPPER = ["push_up", "shoulder_press", "biceps_curl"]
LOWER = ["squat", "lunge"]

GOAL_TEMPLATES = {
    "general_fitness": "beginner_full_body",
    "weight_management": "weight_management_circuit",
    "muscle_gain": "upper_lower_split",
    "mobility": "mobility_and_control",
    "endurance": "endurance_focused",
}

# (sets, reps, rest_seconds) by template and experience level.
PRESCRIPTIONS = {
    "beginner_full_body": {"beginner": (2, 10, 75), "intermediate": (3, 10, 60), "advanced": (3, 12, 60)},
    "weight_management_circuit": {"beginner": (2, 12, 45), "intermediate": (3, 12, 40), "advanced": (3, 15, 30)},
    "upper_lower_split": {"beginner": (2, 8, 90), "intermediate": (3, 10, 90), "advanced": (4, 10, 90)},
    "mobility_and_control": {"beginner": (2, 8, 60), "intermediate": (2, 10, 60), "advanced": (3, 10, 60)},
    "endurance_focused": {"beginner": (2, 12, 40), "intermediate": (3, 15, 30), "advanced": (3, 20, 30)},
}

HEALTH_FLAG_WARNING = (
    "You indicated a health condition, injury, pregnancy, or other special circumstance. "
    "FitAI is an educational prototype: please consult a qualified health professional before "
    "following this plan. The plan has been kept at beginner intensity."
)

SECONDS_PER_REP = 3


@dataclass
class ProfileInput:
    goal: str
    experience: str
    equipment: list[str]
    days_per_week: int
    session_minutes: int
    exclusions: list[str] = field(default_factory=list)
    preferred_days: list[int] = field(default_factory=list)
    health_flags: list[str] = field(default_factory=list)


@dataclass
class ExerciseInfo:
    slug: str
    name: str
    equipment: list[str]


@dataclass
class Prescription:
    exercise_slug: str
    day_index: int
    order_index: int
    sets: int
    repetitions: int
    rest_seconds: int
    notes: str = ""
    practice_mode: bool = False


@dataclass
class PlanDraft:
    template: str
    goal: str
    schedule: list[int]
    prescriptions: list[Prescription]
    reasons: list[str]
    warnings: list[str]


class PlanGenerationError(ValueError):
    pass


def estimate_minutes(sets: int, reps: int, rest: int) -> float:
    return sets * (reps * SECONDS_PER_REP + rest) / 60.0


def choose_schedule(days_per_week: int, preferred_days: list[int]) -> list[int]:
    preferred = sorted(set(d for d in preferred_days if 0 <= d <= 6))
    if len(preferred) >= days_per_week:
        return preferred[:days_per_week]
    schedule = list(preferred)
    for day in DEFAULT_SCHEDULES[days_per_week] + list(range(7)):
        if len(schedule) == days_per_week:
            break
        if day not in schedule:
            schedule.append(day)
    return sorted(schedule)


def generate_plan(profile: ProfileInput, catalog: list[ExerciseInfo]) -> PlanDraft:
    reasons: list[str] = []
    warnings: list[str] = []

    template = GOAL_TEMPLATES.get(profile.goal, "beginner_full_body")
    reasons.append(f"Goal '{profile.goal.replace('_', ' ')}' maps to the '{template.replace('_', ' ')}' template.")

    experience = profile.experience
    if profile.health_flags:
        warnings.append(HEALTH_FLAG_WARNING)
        if experience != "beginner":
            reasons.append("Intensity reduced to beginner level because health considerations were reported.")
        experience = "beginner"

    available: list[ExerciseInfo] = []
    by_slug = {e.slug: e for e in catalog}
    for slug in PRIORITY:
        ex = by_slug.get(slug)
        if ex is None:
            continue
        if slug in profile.exclusions:
            reasons.append(f"{ex.name} excluded at your request.")
            continue
        if ex.equipment and not set(ex.equipment) & set(profile.equipment):
            reasons.append(f"{ex.name} skipped: needs {' or '.join(e.replace('_', ' ') for e in ex.equipment)}.")
            continue
        available.append(ex)
    if not available:
        raise PlanGenerationError("No supported exercises remain after applying equipment and exclusion constraints.")

    sets, reps, rest = PRESCRIPTIONS[template][experience]
    reasons.append(f"{experience.capitalize()} prescription: {sets} sets x {reps} reps, {rest}s rest.")

    days = max(1, min(6, profile.days_per_week))
    schedule = choose_schedule(days, profile.preferred_days)
    reasons.append("Training days: " + ", ".join(WEEKDAYS[d] for d in schedule) + ".")

    slugs = [e.slug for e in available]
    if template == "upper_lower_split":
        upper = [s for s in slugs if s in UPPER]
        lower = [s for s in slugs if s in LOWER]
        if days >= 2 and upper and lower:
            day_lists = [upper if i % 2 == 0 else lower for i in range(days)]
            reasons.append("Alternating upper-body and lower-body days to spread training volume.")
        else:
            day_lists = [slugs] * days
            reasons.append("Using full-body days because a split needs at least 2 days and both upper and lower exercises.")
    else:
        day_lists = [slugs] * days

    if template == "mobility_and_control":
        warnings.append(
            "Version one supports only five strength exercises, so this plan emphasises slow, controlled "
            "movement rather than dedicated mobility drills."
        )

    prescriptions: list[Prescription] = []
    trimmed = False
    for day_index, day_slugs in enumerate(day_lists):
        chosen = list(day_slugs)
        day_sets = sets
        while sum(estimate_minutes(day_sets, reps, rest) for _ in chosen) > profile.session_minutes:
            if len(chosen) > 2:
                chosen.pop()
            elif day_sets > 1:
                day_sets -= 1
            elif len(chosen) > 1:
                chosen.pop()
            else:
                break
            trimmed = True
        for order, slug in enumerate(chosen):
            notes = "Move slowly: about 3 seconds down and 2 seconds up." if template == "mobility_and_control" else ""
            prescriptions.append(Prescription(slug, day_index, order, day_sets, reps, rest, notes))
    if trimmed:
        reasons.append(f"Volume trimmed to fit your preferred session length of {profile.session_minutes} minutes.")

    return PlanDraft(template, profile.goal, schedule, prescriptions, reasons, warnings)

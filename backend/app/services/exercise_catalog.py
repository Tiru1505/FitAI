"""The five exercises supported in version one, and the idempotent seeding helper."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise

SUPPORTED_EXERCISES = ("squat", "lunge", "push_up", "biceps_curl", "shoulder_press")

CATALOG: list[dict] = [
    {
        "slug": "squat",
        "name": "Squat",
        "difficulty": "beginner",
        "muscle_group": "Quadriceps, glutes, hamstrings",
        "equipment": [],
        "instructions": [
            "Stand with feet about shoulder-width apart, toes turned slightly out.",
            "Push your hips back and bend your knees as if sitting into a chair.",
            "Lower to a depth you can control while keeping your chest up.",
            "Drive through your whole foot to return to standing.",
        ],
        "form_cues": ["Knees track in line with toes", "Chest up", "Controlled depth"],
        "substitutions": ["Box squat (sit to a chair or bench)", "Wall-supported squat"],
        "safety_note": "Stop if you feel sharp knee, hip, or back pain.",
    },
    {
        "slug": "lunge",
        "name": "Lunge",
        "difficulty": "beginner",
        "muscle_group": "Quadriceps, glutes",
        "equipment": [],
        "instructions": [
            "Stand tall, then take a controlled step forward.",
            "Lower until both knees are bent while keeping your torso upright.",
            "Push through the front foot to return to the start.",
            "Alternate legs or complete all reps on one side.",
        ],
        "form_cues": ["Torso upright", "Front knee over the foot", "Controlled descent"],
        "substitutions": ["Static split squat", "Reverse lunge", "Hold a wall or chair for balance"],
        "safety_note": "Use a support for balance if needed. Stop if you feel knee pain.",
    },
    {
        "slug": "push_up",
        "name": "Push-up",
        "difficulty": "intermediate",
        "muscle_group": "Chest, shoulders, triceps, core",
        "equipment": [],
        "instructions": [
            "Place hands slightly wider than shoulder-width apart.",
            "Keep a straight line from shoulders through hips to ankles.",
            "Bend your elbows to lower your chest toward the floor.",
            "Press back up to straight arms.",
        ],
        "form_cues": ["Straight body line", "Elbows about 45 degrees from the body", "Full range you can control"],
        "substitutions": ["Incline push-up (hands on a bench or wall)", "Knee push-up"],
        "safety_note": "Choose an incline variation if you cannot keep your hips in line.",
    },
    {
        "slug": "biceps_curl",
        "name": "Biceps curl",
        "difficulty": "beginner",
        "muscle_group": "Biceps, forearms",
        "equipment": ["dumbbells", "resistance_band"],
        "instructions": [
            "Stand tall holding dumbbells or a band with arms extended.",
            "Keep your elbows close to your sides.",
            "Bend your elbows to curl the weight toward your shoulders.",
            "Lower slowly back to straight arms.",
        ],
        "form_cues": ["Elbows stay by your sides", "No body swing", "Slow lowering"],
        "substitutions": ["Resistance band curl", "Hammer curl"],
        "safety_note": "Use a light load you can control through the full range.",
    },
    {
        "slug": "shoulder_press",
        "name": "Shoulder press",
        "difficulty": "intermediate",
        "muscle_group": "Shoulders, triceps",
        "equipment": ["dumbbells", "resistance_band"],
        "instructions": [
            "Hold weights at shoulder height with elbows bent.",
            "Brace your core and keep your ribs down.",
            "Press both arms overhead until they are nearly straight.",
            "Lower with control back to shoulder height.",
        ],
        "form_cues": ["Press both arms evenly", "Avoid leaning back", "Controlled lowering"],
        "substitutions": ["Seated dumbbell press", "Resistance band press"],
        "safety_note": "Skip this exercise if overhead movement causes shoulder pain.",
    },
]


def seed_exercises(db: Session) -> None:
    existing = {e.slug: e for e in db.scalars(select(Exercise))}
    for data in CATALOG:
        exercise = existing.get(data["slug"])
        if exercise is None:
            db.add(Exercise(**data))
        else:
            for key, value in data.items():
                setattr(exercise, key, value)
    db.commit()

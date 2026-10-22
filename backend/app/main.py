import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, inference, nutrition, progress, sessions, users, workouts
from app.core.config import BACKEND_DIR, get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.exercise_catalog import SUPPORTED_EXERCISES, seed_exercises
from app.services.exercise_classifier import ModelRegistry
from app.services.nutrition_service import DISCLAIMER, seed_foods

logger = logging.getLogger("fitai")

SAFETY_NOTICE = (
    "FitAI is an educational fitness-support prototype. It does not diagnose medical conditions, prescribe "
    "treatment, guarantee injury prevention, or provide clinical nutrition prescriptions. Stop exercising if "
    "you feel pain, dizziness, or shortness of breath. If you have an injury, a chronic condition, are "
    "pregnant, have a history of eating disorders, or have special dietary requirements, consult a qualified "
    "professional before using FitAI."
)

PRIVACY_NOTICE = (
    "Camera frames are processed in your browser to extract 33 body landmark points. Only these numerical "
    "landmarks are sent to the FitAI server for analysis; raw video is never uploaded or stored. The server "
    "stores your profile, plans, and aggregate session results (repetitions, form scores, feedback). You can "
    "delete all stored data at any time from Settings."
)


def run_migrations(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging configuration
    cfg.set_main_option("script_location", str(Path(BACKEND_DIR / "app" / "db" / "migrations")))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.run_migrations_on_startup:
        run_migrations(settings.database_url)
    with SessionLocal() as db:
        seed_exercises(db)
        seed_foods(db)
    registry = ModelRegistry(settings.trained_models_dir, SUPPORTED_EXERCISES)
    registry.load_all()
    app.state.registry = registry
    logger.info("exercise classifier: %s", registry.exercise_classifier.status)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for module in (auth, users, workouts, sessions, inference, progress, nutrition):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/meta/notices", tags=["meta"])
    def notices() -> dict:
        return {"safety": SAFETY_NOTICE, "privacy": PRIVACY_NOTICE, "nutrition": DISCLAIMER}

    return app


app = create_app()

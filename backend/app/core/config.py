"""Application settings.

All tunable project parameters (score weights, adaptation thresholds, inference
thresholds) live here so they can be changed through environment variables and
validated experimentally instead of being hard-coded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_prefix="FITAI_", extra="ignore")

    app_name: str = "FitAI API"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'fitai.db').as_posix()}"
    run_migrations_on_startup: bool = True

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Inference -----------------------------------------------------------
    trained_models_dir: Path = BACKEND_DIR / "trained_models"
    classifier_confidence_threshold: float = 0.60
    min_landmark_visibility: float = 0.50
    sequence_length: int = 60
    classify_every_n_frames: int = 5
    invisible_frames_before_reset: int = 15
    max_frames_per_request: int = 900

    # --- Session score (weights are configurable project parameters) ---------
    score_weight_completion: float = 0.35
    score_weight_form: float = 0.35
    score_weight_consistency: float = 0.15
    score_weight_difficulty: float = 0.15
    consistency_window_days: int = 14

    # --- Adaptive coaching thresholds ----------------------------------------
    coach_high_completion: float = 0.90
    coach_low_completion: float = 0.60
    coach_high_form: float = 0.80
    coach_low_form: float = 0.60
    coach_high_difficulty: int = 4
    coach_easy_difficulty: int = 2
    coach_missed_sessions_threshold: int = 2
    coach_persistent_error_sessions: int = 3
    coach_rep_increment: int = 2
    coach_rep_decrement: int = 2
    coach_rest_increment_seconds: int = 15
    coach_min_reps: int = 4
    coach_max_reps: int = 25
    coach_max_rest_seconds: int = 180

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment != "development" and settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise RuntimeError("FITAI_JWT_SECRET must be set outside development.")
    return settings

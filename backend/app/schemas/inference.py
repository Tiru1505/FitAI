from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ExerciseSlug


class LandmarkFrame(BaseModel):
    """One frame of 33 MediaPipe pose landmarks as [x, y, z, visibility]; null when no person was detected."""

    landmarks: list[list[float]] | None = None
    timestamp_ms: float | None = None
    image_width: float | None = Field(default=None, gt=0, le=10000)
    image_height: float | None = Field(default=None, gt=0, le=10000)

    @field_validator("landmarks")
    @classmethod
    def check_shape(cls, v):
        if v is None:
            return v
        if len(v) != 33 or any(len(p) != 4 for p in v):
            raise ValueError("landmarks must be 33 points of [x, y, z, visibility]")
        for x, y, z, vis in v:
            if not (-2.0 <= x <= 3.0 and -2.0 <= y <= 3.0 and -10.0 <= z <= 10.0 and 0.0 <= vis <= 1.0):
                raise ValueError("landmark values out of expected range")
        return v


class AnalyzeRequest(BaseModel):
    expected_exercise: ExerciseSlug
    frames: list[LandmarkFrame] = Field(min_length=1)


class AnalyzeResponse(BaseModel):
    frames_processed: int
    last: dict
    summary: dict
    model_status: dict


class LiveConfigMessage(BaseModel):
    type: Literal["config"]
    expected_exercise: ExerciseSlug
    session_id: int | None = None


class LiveFrameMessage(LandmarkFrame):
    type: Literal["frame"]


class ClientStats(BaseModel):
    frames_captured: int = Field(default=0, ge=0)
    frames_sent: int = Field(default=0, ge=0)
    frames_dropped: int = Field(default=0, ge=0)


class LiveEndMessage(BaseModel):
    type: Literal["end"]
    save: bool = True
    client_stats: ClientStats = Field(default_factory=ClientStats)

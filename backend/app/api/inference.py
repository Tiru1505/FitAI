import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import AppSettings, CurrentUser, Registry, user_from_token
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import WorkoutSession
from app.schemas.inference import AnalyzeRequest, AnalyzeResponse, LiveConfigMessage, LiveEndMessage, LiveFrameMessage
from app.services import live_session_store
from app.services.live_analyzer import LiveAnalyzer

router = APIRouter(prefix="/api/inference", tags=["inference"])
logger = logging.getLogger("fitai.inference")

WS_POLICY_VIOLATION = 1008


@router.get("/status")
def model_status(registry: Registry, _user: CurrentUser) -> dict:
    return registry.status()


@router.post("/analyze-frame", response_model=AnalyzeResponse)
def analyze_frames(body: AnalyzeRequest, registry: Registry, settings: AppSettings, _user: CurrentUser) -> AnalyzeResponse:
    """Stateless analysis of one frame or a short sequence of landmark frames (no video)."""
    if len(body.frames) > settings.max_frames_per_request:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"At most {settings.max_frames_per_request} frames per request")
    analyzer = LiveAnalyzer(body.expected_exercise, registry, settings)
    last: dict = {}
    for frame in body.frames:
        last = analyzer.process(frame.landmarks, frame.image_width, frame.image_height)
    return AnalyzeResponse(frames_processed=len(body.frames), last=last, summary=analyzer.summary(), model_status=registry.status())


@router.websocket("/live")
async def live(websocket: WebSocket, token: str | None = None) -> None:
    """Live landmark channel.

    Client -> server: {"type": "config", ...} once, then {"type": "frame", ...} messages,
    {"type": "reset"} to start a new set, and {"type": "end", ...} to receive a summary.
    Only landmark coordinates are received; no images or video.
    """
    settings = get_settings()
    registry = websocket.app.state.registry
    with SessionLocal() as db:
        user = user_from_token(db, token)
        user_id = user.id if user else None
    if user_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION, reason="authentication required")
        return
    await websocket.accept()

    analyzer: LiveAnalyzer | None = None
    session_id: int | None = None
    try:
        while True:
            data = await websocket.receive_json()
            kind = data.get("type") if isinstance(data, dict) else None
            try:
                if kind == "config":
                    cfg = LiveConfigMessage.model_validate(data)
                    session_id = None
                    if cfg.session_id is not None:
                        with SessionLocal() as db:
                            ws = db.get(WorkoutSession, cfg.session_id)
                            if ws is None or ws.user_id != user_id or ws.status != "in_progress":
                                await websocket.send_json({"type": "error", "detail": "session not found or not in progress"})
                                continue
                        session_id = cfg.session_id
                    analyzer = LiveAnalyzer(cfg.expected_exercise, registry, settings)
                    await websocket.send_json(
                        {"type": "ready", "expected_exercise": cfg.expected_exercise, "session_id": session_id, "model_status": registry.status()}
                    )
                elif kind == "frame":
                    if analyzer is None:
                        await websocket.send_json({"type": "error", "detail": "send a config message first"})
                        continue
                    frame = LiveFrameMessage.model_validate(data)
                    # Model inference is CPU-bound: keep it off the event loop.
                    result = await run_in_threadpool(analyzer.process, frame.landmarks, frame.image_width, frame.image_height)
                    result["timestamp_ms"] = frame.timestamp_ms
                    await websocket.send_json(result)
                elif kind in ("reset", "end"):
                    if analyzer is None:
                        await websocket.send_json({"type": "error", "detail": "send a config message first"})
                        continue
                    end = LiveEndMessage.model_validate({**data, "type": "end"})
                    summary = analyzer.summary()
                    saved = None
                    if session_id is not None and end.save and summary["frames"] > 0:
                        saved = live_session_store.add_summary(session_id, summary, end.client_stats.model_dump())
                    await websocket.send_json({"type": "summary", "set_summary": summary, "session_exercise_totals": saved})
                    analyzer = LiveAnalyzer(analyzer.expected_exercise, registry, settings)
                else:
                    await websocket.send_json({"type": "error", "detail": "unknown message type"})
            except ValidationError as exc:
                await websocket.send_json({"type": "error", "detail": "invalid message", "errors": exc.errors(include_url=False, include_input=False)})
            except ValueError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
    except WebSocketDisconnect:
        logger.info("live inference client disconnected")

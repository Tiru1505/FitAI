from app.core.config import Settings
from app.services import pose_service as ps
from app.services.exercise_classifier import ModelRegistry
from app.services.form_feedback import FormAnalyzer
from app.services.live_analyzer import LiveAnalyzer
from app.services.rep_counter import make_rep_counter
from tests.landmark_factory import curl_front_view, rep_angles, squat_side_view


def run_curl(drift: float, reps: int = 3):
    counter, form = make_rep_counter("biceps_curl"), FormAnalyzer("biceps_curl")
    frames = []
    for a in rep_angles(170, 40, reps):
        arr = ps.to_array(curl_front_view(a, elbow_drift_deg=drift if a < 140 else 0))
        rep = counter.update(arr)
        frames.append(form.update(arr, rep))
    return counter, form, frames


def test_clean_curls_score_full_form():
    counter, form, _ = run_curl(drift=0)
    assert counter.count == 3
    s = form.summary()
    assert s["form_score"] == 1.0 and s["error_counts"] == {}


def test_elbow_drift_is_detected_and_lowers_score():
    counter, form, frames = run_curl(drift=50)
    assert counter.count == 3
    s = form.summary()
    assert s["error_counts"].get("elbow_drift") == 3
    assert s["form_score"] == 0.0
    assert any(f.feedback == "Keep your elbows close to your sides." for f in frames)


def test_partial_rep_counts_as_insufficient_range():
    counter, form = make_rep_counter("squat"), FormAnalyzer("squat")
    for a in rep_angles(172, 125, 1):
        arr = ps.to_array(squat_side_view(a))
        form.update(arr, counter.update(arr))
    s = form.summary()
    assert s["rep_attempts"] == 1 and s["error_counts"] == {"insufficient_range": 1}


def test_not_visible_reports_uncertain():
    counter, form = make_rep_counter("squat"), FormAnalyzer("squat")
    frame = form.update(None, counter.update_angle(None))
    assert frame.status == "uncertain"


def test_live_analyzer_without_models_is_explicit_about_source(tmp_path):
    settings = Settings(trained_models_dir=tmp_path)
    registry = ModelRegistry(tmp_path, ("squat",))
    registry.load_all()
    assert registry.exercise_classifier.available is False
    analyzer = LiveAnalyzer("squat", registry, settings)
    msg = {}
    for a in rep_angles(172, 85, 2):
        msg = analyzer.process(squat_side_view(a), 640, 480)
    assert msg["recognition_source"] == "user_selected"
    assert msg["confidence"] is None
    assert msg["repetition_count"] == 2
    msg = analyzer.process(None)
    assert msg["visible"] is False and msg["form_status"] == "uncertain"

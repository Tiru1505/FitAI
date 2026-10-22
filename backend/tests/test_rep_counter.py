import pytest

from app.services import pose_service as ps
from app.services.rep_counter import REP_CONFIGS, make_rep_counter
from tests.landmark_factory import rep_angles, squat_side_view


def run(counter, angles):
    updates = [counter.update_angle(a) for a in angles]
    return updates[-1], updates


@pytest.mark.parametrize("reps", [1, 3, 10])
def test_squat_counts_full_reps(reps):
    counter = make_rep_counter("squat")
    last, _ = run(counter, rep_angles(172, 85, reps))
    assert last.repetition_count == reps
    assert last.partial_count == 0


def test_phases_occur_in_order():
    counter = make_rep_counter("squat")
    _, updates = run(counter, rep_angles(172, 85, 1))
    phases = [u.phase for u in updates]
    order = [p for i, p in enumerate(phases) if i == 0 or p != phases[i - 1]]
    assert order == ["start", "descending", "bottom", "ascending", "complete", "start"]


def test_shallow_movement_is_partial_not_full_rep():
    counter = make_rep_counter("squat")
    last, updates = run(counter, rep_angles(172, 125, 2))
    assert last.repetition_count == 0
    assert last.partial_count == 2
    assert sum(u.partial_rep for u in updates) == 2


def test_jitter_near_threshold_does_not_double_count():
    counter = make_rep_counter("squat")
    angles = rep_angles(172, 85, 1)
    # Noise around the bottom threshold (100 deg) while at the bottom.
    bottom = angles.index(85)
    angles[bottom:bottom] = [99, 103, 98, 104, 97, 102] * 3
    last, _ = run(counter, angles)
    assert last.repetition_count == 1


def test_mirrored_shoulder_press_counts_upward_reps():
    counter = make_rep_counter("shoulder_press")
    assert REP_CONFIGS["shoulder_press"].start_is_high is False
    last, _ = run(counter, rep_angles(80, 170, 4))  # start bent, press to extended
    assert last.repetition_count == 4


def test_does_not_start_counting_outside_start_position():
    counter = make_rep_counter("shoulder_press")
    # Arms hanging straight (in the "target" region) should not produce reps.
    last, _ = run(counter, [170.0] * 50)
    assert last.repetition_count == 0
    assert last.phase == "not_started"


def test_missing_landmarks_reset_state_after_threshold():
    counter = make_rep_counter("squat", invisible_frames_before_reset=5)
    angles = rep_angles(172, 85, 1)
    half = len(angles) // 2
    run(counter, angles[:half])  # mid-rep
    assert counter.state in ("descending", "bottom", "ascending")
    for _ in range(5):
        u = counter.update_angle(None)
    assert not u.visible
    assert counter.state == "not_started"
    last, _ = run(counter, angles[half:])
    assert last.repetition_count == 0  # interrupted rep is not counted


def test_short_occlusion_does_not_reset():
    counter = make_rep_counter("squat", invisible_frames_before_reset=10)
    angles = rep_angles(172, 85, 1)
    half = len(angles) // 2
    run(counter, angles[:half])
    for _ in range(3):
        counter.update_angle(None)
    last, _ = run(counter, angles[half:])
    assert last.repetition_count == 1


def test_counts_from_landmark_frames_and_ignores_low_visibility():
    counter = make_rep_counter("squat")
    for a in rep_angles(172, 85, 2):
        counter.update(ps.to_array(squat_side_view(a)))
    assert counter.count == 2

    low = squat_side_view(90)
    for p in low:
        p[3] = 0.1
    assert counter.update(ps.to_array(low)).visible is False

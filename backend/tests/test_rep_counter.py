import pytest

from app.services import pose_service as ps
from app.services.rep_counter import REP_CONFIGS, CalibrationSettings, make_rep_counter
from tests.landmark_factory import rep_angles, squat_side_view


NO_CAL = CalibrationSettings(enabled=False)


def fixed_counter(exercise: str, **kwargs):
    """Counter with calibration disabled: pins the raw threshold logic."""
    return make_rep_counter(exercise, calibration=NO_CAL, **kwargs)


def run(counter, angles):
    updates = [counter.update_angle(a) for a in angles]
    return updates[-1], updates


@pytest.mark.parametrize("reps", [1, 3, 10])
def test_squat_counts_full_reps(reps):
    counter = fixed_counter("squat")
    last, _ = run(counter, rep_angles(172, 85, reps))
    assert last.repetition_count == reps
    assert last.partial_count == 0


def test_phases_occur_in_order():
    counter = fixed_counter("squat")
    _, updates = run(counter, rep_angles(172, 85, 1))
    phases = [u.phase for u in updates]
    order = [p for i, p in enumerate(phases) if i == 0 or p != phases[i - 1]]
    assert order == ["start", "descending", "bottom", "ascending", "complete", "start"]


def test_shallow_movement_is_partial_not_full_rep():
    counter = fixed_counter("squat")
    last, updates = run(counter, rep_angles(172, 125, 2))
    assert last.repetition_count == 0
    assert last.partial_count == 2
    assert sum(u.partial_rep for u in updates) == 2


def test_jitter_near_threshold_does_not_double_count():
    counter = fixed_counter("squat")
    angles = rep_angles(172, 85, 1)
    # Noise around the bottom threshold (100 deg) while at the bottom.
    bottom = angles.index(85)
    angles[bottom:bottom] = [99, 103, 98, 104, 97, 102] * 3
    last, _ = run(counter, angles)
    assert last.repetition_count == 1


def test_mirrored_shoulder_press_counts_upward_reps():
    counter = fixed_counter("shoulder_press")
    assert REP_CONFIGS["shoulder_press"].start_is_high is False
    last, _ = run(counter, rep_angles(80, 170, 4))  # start bent, press to extended
    assert last.repetition_count == 4


def test_does_not_start_counting_outside_start_position():
    counter = fixed_counter("shoulder_press")
    # Arms hanging straight (in the "target" region) should not produce reps.
    last, _ = run(counter, [170.0] * 50)
    assert last.repetition_count == 0
    assert last.phase == "not_started"


def test_missing_landmarks_reset_state_after_threshold():
    counter = fixed_counter("squat", invisible_frames_before_reset=5)
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
    counter = fixed_counter("squat", invisible_frames_before_reset=10)
    angles = rep_angles(172, 85, 1)
    half = len(angles) // 2
    run(counter, angles[:half])
    for _ in range(3):
        counter.update_angle(None)
    last, _ = run(counter, angles[half:])
    assert last.repetition_count == 1


def test_counts_from_landmark_frames_and_ignores_low_visibility():
    counter = fixed_counter("squat")
    for a in rep_angles(172, 85, 2):
        counter.update(ps.to_array(squat_side_view(a)))
    assert counter.count == 2

    low = squat_side_view(90)
    for p in low:
        p[3] = 0.1
    assert counter.update(ps.to_array(low)).visible is False


# --- per-session calibration ------------------------------------------------

def feed(counter, angles):
    for a in angles:
        counter.update_angle(a)
    return counter


def test_calibration_counts_reps_a_fixed_threshold_would_miss():
    """A foreshortened (head-on) or limited-mobility squat never reaches the fixed 100 degrees."""
    shallow = rep_angles(170, 125, 5)
    assert feed(fixed_counter("squat"), shallow).count == 0
    adaptive = feed(make_rep_counter("squat"), shallow)
    assert adaptive.count == 5, "calibration should recover every repetition, including warm-up ones"
    assert adaptive.calibrated is True


def test_calibration_leaves_a_normal_range_alone():
    normal = rep_angles(172, 85, 5)
    assert feed(make_rep_counter("squat"), normal).count == 5
    assert feed(fixed_counter("squat"), normal).count == 5


def test_partial_reps_are_judged_against_the_users_own_range():
    angles = rep_angles(172, 85, 3) + rep_angles(172, 150, 2)
    counter = feed(make_rep_counter("squat"), angles)
    assert (counter.count, counter.partial_count) == (3, 2)


def test_standing_still_never_calibrates():
    counter = feed(make_rep_counter("squat"), [170 + 0.4 * ((i % 7) - 3) / 3 for i in range(300)])
    assert counter.calibrated is False
    assert counter.count == 0


def test_calibration_replay_does_not_recover_an_interrupted_rep():
    counter = make_rep_counter("squat", invisible_frames_before_reset=5)
    angles = rep_angles(170, 125, 1)
    feed(counter, angles[: len(angles) // 2])     # part-way down
    for _ in range(5):
        counter.update_angle(None)                # person leaves frame: state resets
    feed(counter, angles[len(angles) // 2 :])     # returns mid-movement
    assert counter.count == 0


def test_calibration_tightens_thresholds_into_the_observed_range():
    counter = feed(make_rep_counter("squat"), rep_angles(170, 125, 4))
    assert counter.calibrated
    assert 125 < counter.config.target_threshold < 170
    assert counter.config.target_threshold < counter.config.start_threshold < 170

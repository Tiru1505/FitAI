import numpy as np
import pytest

from app.services import pose_service as ps
from tests.landmark_factory import squat_side_view


def test_joint_angle_right_angle():
    assert ps.joint_angle(np.array([1.0, 0.0]), np.array([0.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(90.0)


def test_joint_angle_degenerate_is_nan():
    p = np.array([0.0, 0.0])
    assert np.isnan(ps.joint_angle(p, p, np.array([1.0, 1.0])))


@pytest.mark.parametrize("angle", [60, 95, 130, 175])
def test_synthetic_squat_frame_has_requested_knee_angle(angle):
    arr = ps.to_array(squat_side_view(angle))
    measured, vis = ps.side_angle(arr, "left", ("hip", "knee", "ankle"))
    assert measured == pytest.approx(angle, abs=0.5)
    assert vis > 0.9


def test_normalization_is_translation_and_scale_invariant():
    arr = ps.to_array(squat_side_view(120))
    moved = arr.copy()
    moved[:, 0] = moved[:, 0] * 0.5 + 0.2
    moved[:, 1] = moved[:, 1] * 0.5 + 0.1
    np.testing.assert_allclose(ps.frame_features(arr), ps.frame_features(moved), atol=1e-5)
    assert ps.frame_features(arr).shape == (ps.FEATURES_PER_FRAME,)


def test_aspect_correction_scales_x_only():
    arr = ps.to_array(squat_side_view(120))
    out = ps.aspect_corrected(arr, 640, 480)
    np.testing.assert_allclose(out[:, 0], arr[:, 0] * 640 / 480)
    np.testing.assert_allclose(out[:, 1], arr[:, 1])


def test_to_array_rejects_bad_shape():
    with pytest.raises(ValueError):
        ps.to_array([[0, 0, 0, 1]] * 10)

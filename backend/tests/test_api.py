from tests.landmark_factory import rep_angles, squat_side_view


def setup_user(client, headers, profile_payload, **overrides):
    r = client.put("/api/users/me", json={**profile_payload, **overrides}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.post("/api/workouts/generate", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --- auth & validation ------------------------------------------------------

def test_register_login_and_me(client):
    r = client.post("/api/auth/register", json={"email": "Alice@Example.com", "password": "abcdef12"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"email": "alice@example.com", "password": "abcdef12"}).status_code == 409
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "abcdef12"})
    assert r.status_code == 200
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == "alice@example.com" and me.json()["profile"] is None
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-pass1"}).status_code == 401


def test_weak_password_and_bad_email_rejected(client):
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": "abcdef12"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "b@example.com", "password": "short1"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "b@example.com", "password": "lettersonly"}).status_code == 422


def test_private_endpoints_require_auth(client):
    for path in ("/api/users/me", "/api/workouts/today", "/api/progress/summary", "/api/nutrition/foods"):
        assert client.get(path).status_code == 401
    assert client.get("/api/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_profile_validation(client, auth_headers, profile_payload):
    bad = [
        {"age": 5},
        {"goal": "get_huge"},
        {"days_per_week": 9},
        {"preferred_days": [7]},
        {"exclusions": ["deadlift"]},
        {"equipment": ["barbell"]},
        {"weight_kg": -1},
    ]
    for override in bad:
        r = client.put("/api/users/me", json={**profile_payload, **override}, headers=auth_headers)
        assert r.status_code == 422, override


def test_plan_requires_profile(client, auth_headers):
    assert client.post("/api/workouts/generate", headers=auth_headers).status_code == 409


def test_generate_plan_and_today(client, auth_headers, profile_payload):
    plan = setup_user(client, auth_headers, profile_payload, preferred_days=[0, 1, 2, 3, 4, 5, 6][:3])
    assert plan["template"] == "beginner_full_body"
    assert len(plan["days"]) == 3 and plan["generated_reason"]
    today = client.get("/api/workouts/today", headers=auth_headers).json()
    assert today["plan_id"] == plan["id"]
    assert client.get(f"/api/workouts/{plan['id']}", headers=auth_headers).status_code == 200


def test_cannot_read_other_users_plan(client, auth_headers, profile_payload):
    plan = setup_user(client, auth_headers, profile_payload)
    other = client.post("/api/auth/register", json={"email": "intruder@example.com", "password": "abcdef12"}).json()
    r = client.get(f"/api/workouts/{plan['id']}", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert r.status_code == 404


# --- sessions, inference, adaptation ---------------------------------------

def test_session_requires_safety_acknowledgement(client, auth_headers, profile_payload):
    setup_user(client, auth_headers, profile_payload)
    assert client.post("/api/sessions/start", json={}, headers=auth_headers).status_code == 409
    assert client.post("/api/users/me/safety-acknowledgement", headers=auth_headers).status_code == 200
    assert client.post("/api/sessions/start", json={}, headers=auth_headers).status_code == 201


def test_analyze_frame_endpoint(client, auth_headers):
    frames = [{"landmarks": squat_side_view(a), "image_width": 480, "image_height": 480} for a in rep_angles(172, 85, 2)]
    r = client.post("/api/inference/analyze-frame", json={"expected_exercise": "squat", "frames": frames}, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["repetitions"] == 2
    assert body["last"]["recognition_source"] == "user_selected"
    assert body["model_status"]["exercise_classifier"]["available"] is False


def test_analyze_frame_rejects_malformed_landmarks(client, auth_headers):
    r = client.post(
        "/api/inference/analyze-frame",
        json={"expected_exercise": "squat", "frames": [{"landmarks": [[0.5, 0.5, 0, 1]] * 12}]},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_websocket_rejects_missing_token(client):
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect("/api/inference/live") as ws:
            ws.receive_json()
        raise AssertionError("expected the connection to be closed")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008


def test_full_live_session_flow_with_adaptation(client, auth_headers, profile_payload):
    # Train every day so today is always a training day.
    plan = setup_user(client, auth_headers, profile_payload, days_per_week=6, preferred_days=[0, 1, 2, 3, 4, 5],
                      equipment=[], exclusions=["push_up", "lunge"])  # fmt: skip
    client.post("/api/users/me/safety-acknowledgement", headers=auth_headers)
    today = client.get("/api/workouts/today", headers=auth_headers).json()
    if not today["is_training_day"]:  # Sunday: pick day 0 explicitly
        session = client.post("/api/sessions/start", json={"day_index": 0}, headers=auth_headers).json()
    else:
        session = client.post("/api/sessions/start", json={}, headers=auth_headers).json()
    day = plan["days"][session["day_index"]]
    squat = next(e for e in day["exercises"] if e["exercise"]["slug"] == "squat")
    target_reps = squat["sets"] * squat["repetitions"]

    token = auth_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/api/inference/live?token={token}") as ws:
        ws.send_json({"type": "config", "expected_exercise": "squat", "session_id": session["id"]})
        assert ws.receive_json()["type"] == "ready"
        msg = None
        for a in rep_angles(172, 85, target_reps):
            ws.send_json({"type": "frame", "landmarks": squat_side_view(a), "image_width": 480, "image_height": 480})
            msg = ws.receive_json()
        assert msg["repetition_count"] == target_reps
        ws.send_json({"type": "end", "client_stats": {"frames_captured": 10, "frames_sent": 10, "frames_dropped": 0}})
        summary = ws.receive_json()
        assert summary["type"] == "summary"
        assert summary["session_exercise_totals"]["repetitions"] == target_reps

    r = client.post(
        f"/api/sessions/{session['id']}/complete",
        json={"perceived_difficulty": 3, "exercises": [{"exercise_slug": "squat", "difficulty_rating": 3}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    squat_result = next(x for x in body["session"]["results"] if x["exercise_slug"] == "squat")
    assert squat_result["source"] == "live" and squat_result["completion_rate"] == 1.0
    assert squat_result["form_score"] == 1.0
    assert body["adaptation_applied"] is True
    assert any(d["action"] == "progress" and d["exercise_slug"] == "squat" for d in body["decisions"])

    new_plan = client.get("/api/workouts/active", headers=auth_headers).json()
    assert new_plan["id"] == body["new_plan_id"] and new_plan["version"] == 2
    new_squat = next(e for e in new_plan["days"][session["day_index"]]["exercises"] if e["exercise"]["slug"] == "squat")
    assert new_squat["repetitions"] == squat["repetitions"] + 2

    assert client.post(f"/api/sessions/{session['id']}/complete", json={"perceived_difficulty": 3}, headers=auth_headers).status_code == 409

    summary = client.get("/api/progress/summary", headers=auth_headers).json()
    assert summary["sessions_completed"] == 1 and summary["total_repetitions"] >= target_reps
    history = client.get("/api/progress/history", headers=auth_headers).json()
    assert len(history["adaptations"]) == 1


def test_manual_session_without_camera(client, auth_headers, profile_payload):
    setup_user(client, auth_headers, profile_payload, days_per_week=6, preferred_days=[0, 1, 2, 3, 4, 5])
    client.post("/api/users/me/safety-acknowledgement", headers=auth_headers)
    session = client.post("/api/sessions/start", json={"day_index": 0}, headers=auth_headers).json()
    r = client.post(
        f"/api/sessions/{session['id']}/complete",
        json={"perceived_difficulty": 5, "ended_early": True, "exercises": [{"exercise_slug": "squat", "manual_repetitions": 3}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    results = {x["exercise_slug"]: x for x in r.json()["session"]["results"]}
    assert results["squat"]["source"] == "manual" and results["squat"]["form_score"] is None
    assert r.json()["session"]["form_score"] is None


# --- nutrition & data deletion ---------------------------------------------

def test_food_filters(client, auth_headers):
    r = client.get("/api/nutrition/foods", params={"diet": "vegan", "exclude_allergens": ["soy", "peanuts"]}, headers=auth_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all("vegan" in i["tags"] and not {"soy", "peanuts"} & set(i["allergens"]) for i in items)
    assert client.get("/api/nutrition/foods", params={"diet": "keto"}, headers=auth_headers).status_code == 422


def test_meal_guidance_respects_profile(client, auth_headers, profile_payload):
    client.put("/api/users/me", json={**profile_payload, "dietary_preferences": ["vegetarian"], "allergies": ["milk"]}, headers=auth_headers)
    body = client.post("/api/nutrition/meal-guidance", json={}, headers=auth_headers).json()
    assert body["calorie_min"] and body["disclaimer"]
    for foods in body["suggested_foods"].values():
        assert all("vegetarian" in f["tags"] and "milk" not in f["allergens"] for f in foods)

    client.put("/api/users/me", json={**profile_payload, "health_flags": ["pregnancy"]}, headers=auth_headers)
    body = client.post("/api/nutrition/meal-guidance", json={}, headers=auth_headers).json()
    assert body["calorie_min"] is None and body["professional_referral"] is True


def test_delete_all_data(client, auth_headers, profile_payload):
    setup_user(client, auth_headers, profile_payload)
    client.post("/api/users/me/safety-acknowledgement", headers=auth_headers)
    session = client.post("/api/sessions/start", json={"day_index": 0}, headers=auth_headers).json()
    client.post(f"/api/sessions/{session['id']}/complete", json={"perceived_difficulty": 3}, headers=auth_headers)

    r = client.delete("/api/users/me/data", params={"keep_account": True}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["deleted"]["workout_sessions"] == 1
    me = client.get("/api/users/me", headers=auth_headers).json()
    assert me["profile"] is None

    r = client.delete("/api/users/me/data", headers=auth_headers)
    assert r.json()["account_deleted"] is True
    assert client.get("/api/users/me", headers=auth_headers).status_code == 401


# --- guest accounts ---------------------------------------------------------

def test_guest_login_creates_usable_account(client):
    r = client.post("/api/auth/guest")
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = client.get("/api/users/me", headers=headers).json()
    assert me["is_guest"] is True
    assert me["profile"] is not None, "guest should land on a usable account, not the profile form"
    # The safety notice is a health gate: it must NOT be pre-acknowledged.
    assert me["profile"]["safety_acknowledged_at"] is None
    assert client.post("/api/sessions/start", json={}, headers=headers).status_code == 409

    plan = client.get("/api/workouts/active", headers=headers).json()
    assert plan["days"], "guest should get a starter plan"
    # Bodyweight starter profile: nothing that needs equipment.
    slugs = {e["exercise"]["slug"] for d in plan["days"] for e in d["exercises"]}
    assert slugs == {"squat", "lunge", "push_up"}


def test_each_guest_gets_a_separate_account(client):
    a = client.post("/api/auth/guest").json()["access_token"]
    b = client.post("/api/auth/guest").json()["access_token"]
    id_a = client.get("/api/users/me", headers={"Authorization": f"Bearer {a}"}).json()["id"]
    id_b = client.get("/api/users/me", headers={"Authorization": f"Bearer {b}"}).json()["id"]
    assert id_a != id_b


def test_guest_account_cannot_be_logged_into(client):
    token = client.post("/api/auth/guest").json()["access_token"]
    email = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"}).json()["email"]
    # .invalid is the IANA-reserved domain for addresses that must never resolve, so the login
    # schema rejects it (422) before authentication is even attempted (401). Either is a refusal.
    assert email.endswith("@guest.invalid")
    assert client.post("/api/auth/login", json={"email": email, "password": "guest"}).status_code in (401, 422)


def test_registered_user_is_not_marked_guest(client, auth_headers):
    assert client.get("/api/users/me", headers=auth_headers).json()["is_guest"] is False

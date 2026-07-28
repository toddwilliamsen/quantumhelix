"""Auth, RBAC, tenant isolation, and alert escalation smoke tests."""
import uuid

from tests.conftest import auth_header


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_login_rejects_bad_password(client):
    res = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_login_and_me(client, admin_token):
    res = client.get("/api/me", headers=auth_header(admin_token))
    assert res.status_code == 200
    body = res.get_json()
    assert body["username"] == "admin"
    assert body["role"] == "SUPER_ADMIN"


def test_read_only_cannot_mutate_alerts(client, app, admin_token):
    from models import db, User, Alert, Tenant

    with app.app_context():
        tenant = Tenant.query.first()
        user = User(username="reader", role="READ_ONLY", tenant_id=tenant.id)
        user.set_password("reader-password-ok")
        db.session.add(user)
        alert = Alert(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            status="open",
            severity="HIGH",
            cloud="AWS",
            identity="reader-test@example.com",
            short_identity="reader-test",
            source_ip="1.2.3.4",
            score=0.9,
            ensemble=0.9,
            quantum_kernel=0.8,
            classical_svm=0.7,
            isolation_forest=0.6,
            plain_english="test",
            actions=[],
            siem={},
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    login = client.post("/api/login", json={"username": "reader", "password": "reader-password-ok"})
    assert login.status_code == 200
    token = login.get_json()["token"]

    res = client.post(
        f"/api/alert/{alert_id}/action?action=acknowledge",
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_escalate_creates_case(client, app, admin_token):
    from models import db, Alert, Tenant

    with app.app_context():
        tenant = Tenant.query.first()
        alert = Alert(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            status="open",
            severity="CRITICAL",
            cloud="Azure",
            identity="escalate-test@example.com",
            short_identity="escalate-test",
            source_ip="10.0.0.1",
            score=0.95,
            ensemble=0.95,
            quantum_kernel=0.9,
            classical_svm=0.9,
            isolation_forest=0.8,
            plain_english="escalate me",
            actions=[],
            siem={},
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    res = client.post(
        f"/api/alert/{alert_id}/action?action=escalate",
        headers=auth_header(admin_token),
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["case_id"]
    assert body["alert"]["status"] == "escalated"
    assert body["alert"]["case_id"] == body["case_id"]


def test_claim_and_my_queue(client, app, admin_token):
    from models import db, Alert, Tenant

    with app.app_context():
        tenant = Tenant.query.first()
        alert = Alert(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            status="open",
            severity="WATCH",
            cloud="GCP",
            identity="claim-test@example.com",
            short_identity="claim-test",
            source_ip="10.0.0.2",
            score=0.7,
            ensemble=0.7,
            quantum_kernel=0.6,
            classical_svm=0.6,
            isolation_forest=0.5,
            plain_english="claim me",
            actions=[],
            siem={},
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    res = client.post(
        f"/api/alert/{alert_id}/action?action=claim",
        headers=auth_header(admin_token),
    )
    assert res.status_code == 200
    assert res.get_json()["alert"]["status"] == "acknowledged"

    queue = client.get("/api/alerts?assignee=me&status=all", headers=auth_header(admin_token))
    assert queue.status_code == 200
    ids = [a["id"] for a in queue.get_json()["alerts"]]
    assert alert_id in ids


def test_password_change_revokes_old_session(client, admin_token):
    res = client.post("/api/me/password", headers=auth_header(admin_token), json={
        "current_password": "test-admin-password-ok",
        "new_password": "rotated-admin-password",
    })
    assert res.status_code == 200
    new_token = res.get_json()["token"]

    stale = client.get("/api/me", headers=auth_header(admin_token))
    assert stale.status_code == 401

    fresh = client.get("/api/me", headers=auth_header(new_token))
    assert fresh.status_code == 200

    # Restore for other tests that may run after in same process (session-scoped app).
    client.post("/api/me/password", headers=auth_header(new_token), json={
        "current_password": "rotated-admin-password",
        "new_password": "test-admin-password-ok",
    })


def test_ingest_requires_auth_without_api_key(client, monkeypatch):
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    res = client.post("/api/ingest/webhook", json={"user": "x", "src_ip": "1.1.1.1"})
    assert res.status_code == 401


def test_super_admin_create_user_defaults_to_own_tenant(client, admin_token):
    """SUPER_ADMIN may omit tenant_id; it defaults to their tenant instead of 400."""
    res = client.post("/api/users", headers=auth_header(admin_token), json={
        "username": "no-tenant-user",
        "password": "a-strong-password",
        "role": "TIER_1",
    })
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["user"]["tenant_id"]
    assert body["user"]["must_change_password"] is True


def test_must_change_password_blocks_api(client, admin_token, app):
    from models import db, User, Tenant

    with app.app_context():
        tenant = Tenant.query.first()
        user = User(username="must-change-user", role="TIER_1", tenant_id=tenant.id)
        user.set_password("temporary-pass1", require_change=True)
        db.session.add(user)
        db.session.commit()

    login = client.post("/api/login", json={"username": "must-change-user", "password": "temporary-pass1"})
    assert login.status_code == 200
    assert login.get_json()["must_change_password"] is True
    token = login.get_json()["token"]

    blocked = client.get("/api/alerts", headers=auth_header(token))
    assert blocked.status_code == 403

    allowed = client.get("/api/me", headers=auth_header(token))
    assert allowed.status_code == 200


def test_create_user_rejects_unknown_tenant(client, admin_token):
    res = client.post("/api/users", headers=auth_header(admin_token), json={
        "username": "bad-tenant-user",
        "password": "a-strong-password",
        "role": "TIER_1",
        "tenant_id": 99999,
    })
    assert res.status_code == 400

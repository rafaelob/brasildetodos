"""Tests for Milestone M4: Security, Moderation, Port 8008 Multi-Origin Matching & CSRF."""
import pytest
from fastapi.testclient import TestClient
from bdt.api import create_app, password_hash
from bdt.evidence import Document
from bdt.storage import Place, User

PASSWORD = "test-password-123456"
HEADERS_127 = {"X-BDT-Client": "web", "Origin": "http://127.0.0.1:8008"}
HEADERS_LOCAL = {"X-BDT-Client": "web", "Origin": "http://localhost:8008"}


@pytest.fixture
def app_8008(database, stored, monkeypatch):
    monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("BDT_PORT", "8008")
    monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")
    return create_app(str(database.engine.url), testing=True)


@pytest.fixture
def client_8008(app_8008):
    with TestClient(app_8008) as c:
        yield c


def test_origin_127_0_0_1_8008_succeeds_with_csrf_header(client_8008):
    """Origin http://127.0.0.1:8008 succeeds with X-BDT-Client: web."""
    reg = client_8008.post(
        "/api/auth/register",
        headers=HEADERS_127,
        json={"username": "user_127", "password": PASSWORD},
    )
    assert reg.status_code == 201, reg.text

    login = client_8008.post(
        "/api/auth/login",
        headers=HEADERS_127,
        json={"username": "user_127", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert client_8008.get("/api/auth/me").json()["username"] == "user_127"


def test_origin_localhost_8008_succeeds_with_csrf_header(client_8008):
    """Origin http://localhost:8008 succeeds with X-BDT-Client: web."""
    reg = client_8008.post(
        "/api/auth/register",
        headers=HEADERS_LOCAL,
        json={"username": "user_local", "password": PASSWORD},
    )
    assert reg.status_code == 201, reg.text

    login = client_8008.post(
        "/api/auth/login",
        headers=HEADERS_LOCAL,
        json={"username": "user_local", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert client_8008.get("/api/auth/me").json()["username"] == "user_local"


def test_dev_mode_normalizes_single_origin_to_both_localhost_and_127(database, stored, monkeypatch):
    """When only localhost:8008 is configured, 127.0.0.1:8008 is also accepted in dev mode."""
    monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://localhost:8008")
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/register",
            headers={"X-BDT-Client": "web", "Origin": "http://127.0.0.1:8008"},
            json={"username": "norm_user", "password": PASSWORD},
        )
        assert r.status_code == 201, r.text


def test_unauthorized_origin_receives_403_origin_not_allowed(client_8008):
    """Unauthorized origin (e.g. http://evil.com) receives HTTP 403 origin_not_allowed."""
    r = client_8008.post(
        "/api/auth/login",
        headers={"X-BDT-Client": "web", "Origin": "http://evil.com"},
        json={"username": "someuser", "password": PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "origin_not_allowed"

    r2 = client_8008.post(
        "/api/auth/login",
        headers={"X-BDT-Client": "web", "Origin": "http://attacker.example.org:8008"},
        json={"username": "someuser", "password": PASSWORD},
    )
    assert r2.status_code == 403
    assert r2.json()["detail"] == "origin_not_allowed"


def test_missing_csrf_header_receives_403_csrf_header_required(client_8008):
    """Missing X-BDT-Client: web receives HTTP 403 csrf_header_required."""
    r = client_8008.post(
        "/api/auth/login",
        headers={"Origin": "http://127.0.0.1:8008"},
        json={"username": "someuser", "password": PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_header_required"

    r2 = client_8008.post(
        "/api/auth/register",
        headers={},
        json={"username": "someuser", "password": PASSWORD},
    )
    assert r2.status_code == 403
    assert r2.json()["detail"] == "csrf_header_required"


def test_health_endpoint_returns_llm_required_false_and_status_ok(client_8008):
    """GET /api/health returns llm_required: False and status: ok."""
    r = client_8008.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("llm_required") is False
    assert "version" in data


def test_request_body_exceeding_32kb_receives_413_request_too_large(client_8008):
    """Request bodies exceeding 32KB receive HTTP 413 request_too_large."""
    large_payload = "x" * 32769
    r = client_8008.post(
        "/api/auth/login",
        headers=HEADERS_127,
        content=large_payload,
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "request_too_large"


def test_self_review_observation_strictly_blocked(database, stored, monkeypatch):
    """A reviewer cannot review/approve their own submitted observation."""
    monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("BDT_PORT", "8008")
    monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")

    with database.session() as session:
        session.add(User(username="reviewer_author", role="reviewer", password_hash=password_hash(PASSWORD)))
        session.add(User(username="independent_rev", role="reviewer", password_hash=password_hash(PASSWORD)))

    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        # Login as reviewer_author
        login_res = client.post("/api/auth/login", headers=HEADERS_127, json={"username": "reviewer_author", "password": PASSWORD})
        assert login_res.status_code == 200

        # Submit an observation
        obs_payload = {
            "place_id": "test:school",
            "mode": "field",
            "observed_on": "2025-01-01",
            "body": "Detailed observation of the physical school facility entrance.",
            "consent": True,
        }
        obs = client.post("/api/observations", headers=HEADERS_127, json=obs_payload)
        assert obs.status_code == 201
        obs_id = obs.json()["id"]

        # Attempt self-review
        self_rev = client.post(
            f"/api/review/{obs_id}",
            headers=HEADERS_127,
            json={"decision": "approved", "note": "Self-review approval note."},
        )
        assert self_rev.status_code == 403
        assert self_rev.json()["detail"] == "self_review_forbidden"

        # Logout and login as independent_rev
        client.post("/api/auth/logout", headers=HEADERS_127)
        login_indep = client.post("/api/auth/login", headers=HEADERS_127, json={"username": "independent_rev", "password": PASSWORD})
        assert login_indep.status_code == 200

        # Independent review succeeds
        indep_rev = client.post(
            f"/api/review/{obs_id}",
            headers=HEADERS_127,
            json={"decision": "approved", "note": "Valid independent verification performed."},
        )
        assert indep_rev.status_code == 200
        assert indep_rev.json()["status"] == "approved"


def test_self_review_link_strictly_blocked(database, stored, source, monkeypatch):
    """A reviewer cannot review/approve their own proposed relationship link."""
    monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("BDT_PORT", "8008")
    monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")

    with database.session() as session:
        session.add(User(username="link_author", role="reviewer", password_hash=password_hash(PASSWORD)))
        session.add(User(username="link_reviewer", role="reviewer", password_hash=password_hash(PASSWORD)))

    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        # Login as link_author
        client.post("/api/auth/login", headers=HEADERS_127, json={"username": "link_author", "password": PASSWORD})

        # Register resource and document
        res_data = {
            "id": "pncp:m4-test/2025",
            "kind": "contract",
            "title": "M4 Test Contract for School",
            "municipality_id": "1234567",
            "source": source.model_dump(),
            "attributes": {"phase": "contracted"},
        }
        assert client.post("/api/workbench/resources", headers=HEADERS_127, json=res_data).status_code == 201

        doc_data = {"title": "M4 Evidence Document", "source": source.model_dump()}
        doc_res = client.post("/api/workbench/documents", headers=HEADERS_127, json=doc_data)
        assert doc_res.status_code == 201
        doc_id = doc_res.json()["id"]

        with database.session() as session:
            doc_row = session.get(Document, doc_id)
            doc_row.state = "extracted"
            doc_row.extraction = {
                "pages": [
                    {
                        "page": 1,
                        "text": "Exact excerpt identifying test:school for relationship link verification.",
                        "words": [],
                        "candidates": [],
                    }
                ]
            }

        # Propose link
        link_body = {
            "place_id": "test:school",
            "resource_id": "pncp:m4-test/2025",
            "document_id": doc_id,
            "page": 1,
            "excerpt": "identifying test:school for relationship",
            "justification": "Verified contract reference to school facility.",
        }
        link_res = client.post("/api/workbench/links", headers=HEADERS_127, json=link_body)
        assert link_res.status_code == 201
        link_id = link_res.json()["id"]

        # Author attempts self-review -> forbidden
        self_link_rev = client.post(
            f"/api/workbench/links/{link_id}/review",
            headers=HEADERS_127,
            json={
                "decision": "reviewed",
                "expected_revision": 1,
                "note": "Author self-review note.",
                "public_excerpt_checked": True,
            },
        )
        assert self_link_rev.status_code == 403
        assert self_link_rev.json()["detail"] == "independent_review_required"

        # Logout and login as independent reviewer
        client.post("/api/auth/logout", headers=HEADERS_127)
        client.post("/api/auth/login", headers=HEADERS_127, json={"username": "link_reviewer", "password": PASSWORD})

        # Independent review succeeds
        indep_link_rev = client.post(
            f"/api/workbench/links/{link_id}/review",
            headers=HEADERS_127,
            json={
                "decision": "reviewed",
                "expected_revision": 1,
                "note": "Independent reviewer verified the excerpt.",
                "public_excerpt_checked": True,
            },
        )
        assert indep_link_rev.status_code == 200
        assert indep_link_rev.json()["status"] == "reviewed"

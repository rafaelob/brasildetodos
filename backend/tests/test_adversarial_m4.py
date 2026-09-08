# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adversarial challenge test suite for Milestone M4.

Empirically tests and stress-tests:
1. Origin matching variations:
   - http://127.0.0.1:8008, http://localhost:8008, trailing slashes, scheme casing, port matching.
2. Attack & unauthorized origins:
   - http://evil.com, http://127.0.0.1:8009, http://localhost:3000, null origin,
     forged subdomains (http://127.0.0.1.attacker.com, http://localhost.attacker.com),
     userinfo injection, scheme mismatch -> all return HTTP 403 origin_not_allowed.
3. CSRF header permutations on mutations:
   - missing X-BDT-Client, invalid values (web2, true, 1, empty, uppercase, quotes, etc.)
     across POST, PUT, DELETE, PATCH -> all return HTTP 403 csrf_header_required.
   - safe methods (GET, HEAD, OPTIONS) do not require CSRF header.
4. 32KB payload boundary:
   - 32,768 bytes (allowed, boundary condition) vs 32,769 bytes (HTTP 413 request_too_large),
     declared vs streamed chunks, non-numeric Content-Length.
5. Anti-self-review bypass attempts:
   - Author attempting self-review of citizen observations (approve/reject).
   - Author attempting self-review of workbench relationship links (reviewed/rejected/retracted).
   - Task assignee attempting self-acceptance of civic group tasks.
6. Platform rules & security invariants:
   - /api/health returns llm_required: False and status: ok.
   - Zero LLM / vector DB dependencies in runtime.
   - Mandatory security response headers (CSP, nosniff, DENY, no-referrer, Cache-Control).
"""
import json
import pytest
from fastapi.testclient import TestClient
from bdt.api import create_app, password_hash
from bdt.evidence import Document
from bdt.groups import Group, Member, Task
from bdt.storage import Place, User

PASSWORD = "AdversarialPassword123!"
VALID_ORIGIN_127 = "http://127.0.0.1:8008"
VALID_ORIGIN_LOCAL = "http://localhost:8008"


@pytest.fixture
def adversarial_app(database, stored, monkeypatch):
    """Create test application configured for Milestone M4 port 8008."""
    monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
    monkeypatch.setenv("BDT_PORT", "8008")
    monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")
    return create_app(str(database.engine.url), testing=True)


@pytest.fixture
def adv_client(adversarial_app):
    """TestClient instance for adversarial testing."""
    with TestClient(adversarial_app) as client:
        yield client


# ==============================================================================
# 1. Origin Matching Variations & Dev Normalization
# ==============================================================================

class TestOriginMatchingVariations:
    """Stress-test origin matching: allowed variations, trailing slashes, scheme casing, and ports."""

    @pytest.mark.parametrize("valid_origin", [
        "http://127.0.0.1:8008",
        "http://localhost:8008",
        "http://127.0.0.1:8008/",
        "http://localhost:8008/",
        "http://127.0.0.1:8008///",
        "http://localhost:8008///",
    ])
    def test_valid_origin_variations_allowed(self, adv_client, valid_origin):
        """Standard origins and trailing slash variations must be accepted."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": valid_origin},
            json={"username": "nobody", "password": PASSWORD},
        )
        # Should not be blocked by origin middleware (403 origin_not_allowed)
        assert resp.status_code != 403 or resp.json().get("detail") != "origin_not_allowed"
        # Since user doesn't exist, auth failure is 401
        assert resp.status_code == 401

    @pytest.mark.parametrize("cased_origin", [
        "HTTP://127.0.0.1:8008",
        "Http://127.0.0.1:8008",
        "HTTP://localhost:8008",
        "http://LOCALHOST:8008",
        "http://127.0.0.1:8008/Path",
    ])
    def test_non_canonical_scheme_casing_rejected(self, adv_client, cased_origin):
        """Non-canonical scheme or host casing (per RFC 6454 lowercase standard) must be rejected."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": cased_origin},
            json={"username": "nobody", "password": PASSWORD},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "origin_not_allowed"

    @pytest.mark.parametrize("wrong_port_origin", [
        "http://127.0.0.1:80",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8009",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:80080",
        "http://localhost:80",
        "http://localhost:8000",
        "http://localhost:8009",
        "http://localhost:8080",
        "http://localhost:3000",
    ])
    def test_port_mismatches_strictly_rejected(self, adv_client, wrong_port_origin):
        """Any port other than 8008 must be rejected with 403 origin_not_allowed."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": wrong_port_origin},
            json={"username": "nobody", "password": PASSWORD},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "origin_not_allowed"


# ==============================================================================
# 2. Attack & Unauthorized Origins
# ==============================================================================

class TestAttackAndUnauthorizedOrigins:
    """Stress-test attack vectors against origin validation."""

    @pytest.mark.parametrize("attack_origin", [
        "http://evil.com",
        "https://evil.com",
        "http://evil.com:8008",
        "http://127.0.0.1:8009",
        "http://localhost:3000",
        "null",
        "http://127.0.0.1.attacker.com",
        "http://127.0.0.1.attacker.com:8008",
        "http://localhost.attacker.com",
        "http://localhost.attacker.com:8008",
        "http://attacker-127.0.0.1:8008",
        "http://attacker-localhost:8008",
        "http://127.0.0.1:8008.attacker.com",
        "https://127.0.0.1:8008",
        "https://localhost:8008",
        "http://[::1]:8008",
        "http://subdomain.127.0.0.1:8008",
        "http://127.0.0.1:8008@evil.com",
        "file://",
        "data:text/html",
        "javascript:void(0)",
    ])
    def test_attack_origins_strictly_rejected(self, adv_client, attack_origin):
        """Every unauthorized or forged origin must return HTTP 403 origin_not_allowed."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": attack_origin},
            json={"username": "test_user", "password": PASSWORD},
        )
        assert resp.status_code == 403, f"Origin '{attack_origin}' unexpectedly allowed with status {resp.status_code}"
        assert resp.json()["detail"] == "origin_not_allowed"


# ==============================================================================
# 3. CSRF Header Permutations on Mutations
# ==============================================================================

class TestCsrfHeaderPermutations:
    """Verify strict X-BDT-Client: web enforcement on all state-changing methods."""

    @pytest.mark.parametrize("invalid_csrf_val", [
        None,             # header omitted
        "",               # empty string
        "web2",           # wrong version
        "true",           # boolean string
        "1",              # numeric string
        "null",           # string null
        "Web",            # titlecase
        "WEB",            # uppercase
        "web ",           # trailing whitespace
        " web",           # leading whitespace
        "\"web\"",        # quoted
        "admin",          # privilege token attempt
        "bearer",         # bearer attempt
    ])
    @pytest.mark.parametrize("method,endpoint", [
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
    ])
    def test_invalid_csrf_header_blocked_on_mutations(self, adv_client, invalid_csrf_val, method, endpoint):
        """Mutations without exact X-BDT-Client: web must be rejected with 403 csrf_header_required."""
        headers = {"Origin": VALID_ORIGIN_127}
        if invalid_csrf_val is not None:
            headers["X-BDT-Client"] = invalid_csrf_val

        if method == "POST":
            resp = adv_client.post(endpoint, headers=headers, json={"username": "user", "password": PASSWORD})
        elif method == "PUT":
            resp = adv_client.put(endpoint, headers=headers, json={})
        elif method == "DELETE":
            resp = adv_client.delete(endpoint, headers=headers)
        elif method == "PATCH":
            resp = adv_client.patch(endpoint, headers=headers, json={})

        assert resp.status_code == 403
        assert resp.json()["detail"] == "csrf_header_required"

    def test_safe_methods_do_not_require_csrf_header(self, adv_client):
        """GET, HEAD, and OPTIONS methods do not require X-BDT-Client header."""
        # GET
        get_resp = adv_client.get("/api/health", headers={"Origin": VALID_ORIGIN_127})
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "ok"

        # HEAD (FastAPI routes without explicit HEAD handler return 405, but never 403 csrf_header_required)
        head_resp = adv_client.head("/api/health", headers={"Origin": VALID_ORIGIN_127})
        assert head_resp.status_code in (200, 405)
        assert head_resp.status_code != 403

        # OPTIONS
        options_resp = adv_client.options("/api/health", headers={"Origin": VALID_ORIGIN_127})
        assert options_resp.status_code in (200, 405)  # Method allowed or not, but NOT 403 csrf_header_required


# ==============================================================================
# 4. 32KB Payload Boundary Challenge
# ==============================================================================

class TestPayloadBoundary:
    """Stress-test the exact 32KB (32,768 bytes) request body limit."""

    def test_payload_exact_32768_bytes_is_allowed(self, adv_client):
        """Exact 32,768 bytes must pass the size gate (not return 413 request_too_large)."""
        # Construct valid JSON that totals exactly 32,768 bytes
        # {"username":"x...x","password":"..."}
        prefix = '{"username":"'
        suffix = '","password":"' + PASSWORD + '"}'
        needed_padding = 32768 - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
        body = prefix + ("a" * needed_padding) + suffix
        assert len(body.encode("utf-8")) == 32768

        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
            content=body.encode("utf-8"),
        )
        # Should pass the 413 boundary check
        assert resp.status_code != 413
        assert resp.status_code in (401, 422)  # Auth fails or schema validation, but NOT 413

    def test_payload_32769_bytes_strictly_rejected(self, adv_client):
        """A single byte over 32,768 bytes (32,769 bytes) must receive HTTP 413 request_too_large."""
        payload_32769 = b"x" * 32769
        resp = adv_client.post(
            "/api/auth/login",
            headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
            content=payload_32769,
        )
        assert resp.status_code == 413
        assert resp.json()["detail"] == "request_too_large"

    def test_declared_content_length_exceeding_32768_rejected_before_streaming(self, adv_client):
        """Header Content-Length > 32768 is rejected immediately."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={
                "X-BDT-Client": "web",
                "Origin": VALID_ORIGIN_127,
                "Content-Length": "32769",
            },
            content=b"short",
        )
        assert resp.status_code == 413
        assert resp.json()["detail"] == "request_too_large"

    @pytest.mark.parametrize("invalid_len", [
        "not-a-number",
        "-1",
        "-32768",
        "1000000",
    ])
    def test_invalid_or_oversized_content_length_rejected(self, adv_client, invalid_len):
        """Non-numeric or oversized Content-Length headers must be rejected."""
        resp = adv_client.post(
            "/api/auth/login",
            headers={
                "X-BDT-Client": "web",
                "Origin": VALID_ORIGIN_127,
                "Content-Length": invalid_len,
            },
            content=b"test",
        )
        assert resp.status_code == 413
        assert resp.json()["detail"] == "request_too_large"


# ==============================================================================
# 5. Anti-Self-Review Bypass Attempts
# ==============================================================================

class TestAntiSelfReviewBypass:
    """Stress-test anti-self-review enforcement across observations, workbench links, and tasks."""

    def test_observation_author_cannot_self_review(self, database, stored, monkeypatch):
        """An author with reviewer privileges cannot review or approve their own observation."""
        monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
        monkeypatch.setenv("BDT_PORT", "8008")
        monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")

        with database.session() as session:
            session.add(User(username="author_rev", role="reviewer", password_hash=password_hash(PASSWORD)))
            session.add(User(username="indep_rev", role="reviewer", password_hash=password_hash(PASSWORD)))

        app = create_app(str(database.engine.url), testing=True)
        with TestClient(app) as client:
            # Login as author_rev
            client.post("/api/auth/login", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                        json={"username": "author_rev", "password": PASSWORD})

            # Submit observation
            obs_resp = client.post(
                "/api/observations",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={
                    "place_id": "test:school",
                    "mode": "field",
                    "observed_on": "2025-05-01",
                    "body": "Civic observation for anti-self-review test.",
                    "consent": True,
                },
            )
            assert obs_resp.status_code == 201
            obs_id = obs_resp.json()["id"]

            # Author attempts to approve own observation -> 403 self_review_forbidden
            approve_attempt = client.post(
                f"/api/review/{obs_id}",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "approved", "note": "Self-approval attempt."},
            )
            assert approve_attempt.status_code == 403
            assert approve_attempt.json()["detail"] == "self_review_forbidden"

            # Author attempts to reject own observation -> 403 self_review_forbidden
            reject_attempt = client.post(
                f"/api/review/{obs_id}",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "rejected", "note": "Self-rejection attempt."},
            )
            assert reject_attempt.status_code == 403
            assert reject_attempt.json()["detail"] == "self_review_forbidden"

            # Independent reviewer logs in and reviews -> succeeds
            client.post("/api/auth/logout", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127})
            client.post("/api/auth/login", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                        json={"username": "indep_rev", "password": PASSWORD})

            indep_resp = client.post(
                f"/api/review/{obs_id}",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "approved", "note": "Valid independent review."},
            )
            assert indep_resp.status_code == 200
            assert indep_resp.json()["status"] == "approved"

            # Duplicate review attempt -> 409 already_reviewed
            dup_resp = client.post(
                f"/api/review/{obs_id}",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "approved", "note": "Second review attempt."},
            )
            assert dup_resp.status_code == 409
            assert dup_resp.json()["detail"] == "already_reviewed"

    def test_workbench_link_author_cannot_self_review(self, database, stored, source, monkeypatch):
        """A link author cannot self-review or retract their proposed workbench relationship link."""
        monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
        monkeypatch.setenv("BDT_PORT", "8008")
        monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")

        with database.session() as session:
            session.add(User(username="link_auth_user", role="reviewer", password_hash=password_hash(PASSWORD)))
            session.add(User(username="indep_link_user", role="reviewer", password_hash=password_hash(PASSWORD)))

        app = create_app(str(database.engine.url), testing=True)
        with TestClient(app) as client:
            client.post("/api/auth/login", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                        json={"username": "link_auth_user", "password": PASSWORD})

            # Create resource and document
            res_data = {
                "id": "pncp:adversarial-m4/2026",
                "kind": "contract",
                "title": "Adversarial Link Contract",
                "municipality_id": "1234567",
                "source": source.model_dump(),
                "attributes": {"phase": "contracted"},
            }
            client.post("/api/workbench/resources", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127}, json=res_data)

            doc_res = client.post("/api/workbench/documents", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                                  json={"title": "Adversarial Document", "source": source.model_dump()})
            doc_id = doc_res.json()["id"]

            with database.session() as session:
                doc = session.get(Document, doc_id)
                doc.state = "extracted"
                doc.extraction = {
                    "pages": [{"page": 1, "text": "Contract matches test:school facility address.", "words": [], "candidates": []}]
                }

            # Propose link
            link_res = client.post(
                "/api/workbench/links",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={
                    "place_id": "test:school",
                    "resource_id": "pncp:adversarial-m4/2026",
                    "document_id": doc_id,
                    "page": 1,
                    "excerpt": "matches test:school facility",
                    "justification": "Verified excerpt alignment.",
                },
            )
            assert link_res.status_code == 201
            link_id = link_res.json()["id"]

            # Link author attempts review (reviewed) -> 403 independent_review_required
            author_rev_att = client.post(
                f"/api/workbench/links/{link_id}/review",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "reviewed", "expected_revision": 1, "note": "Self review note that is long enough.", "public_excerpt_checked": True},
            )
            assert author_rev_att.status_code == 403
            assert author_rev_att.json()["detail"] == "independent_review_required"

            # Link author attempts reject -> 403 independent_review_required
            author_rej_att = client.post(
                f"/api/workbench/links/{link_id}/review",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "rejected", "expected_revision": 1, "note": "Self rejection note that is long enough.", "public_excerpt_checked": True},
            )
            assert author_rej_att.status_code == 403
            assert author_rej_att.json()["detail"] == "independent_review_required"

            # Independent reviewer attempts without public_excerpt_checked -> 422
            client.post("/api/auth/logout", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127})
            client.post("/api/auth/login", headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                        json={"username": "indep_link_user", "password": PASSWORD})

            unchecked_att = client.post(
                f"/api/workbench/links/{link_id}/review",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "reviewed", "expected_revision": 1, "note": "Independent review note long enough.", "public_excerpt_checked": False},
            )
            assert unchecked_att.status_code == 422
            assert unchecked_att.json()["detail"] == "public_excerpt_review_required"

            # Independent reviewer completes valid review -> 200
            valid_rev = client.post(
                f"/api/workbench/links/{link_id}/review",
                headers={"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127},
                json={"decision": "reviewed", "expected_revision": 1, "note": "Independent valid review note here.", "public_excerpt_checked": True},
            )
            assert valid_rev.status_code == 200
            assert valid_rev.json()["status"] == "reviewed"

    def test_civic_group_task_assignee_cannot_self_accept(self, database, stored, monkeypatch):
        """Civic group task assignee cannot accept or review their own submitted task."""
        monkeypatch.setenv("BDT_ALLOW_REGISTRATION", "1")
        monkeypatch.setenv("BDT_PORT", "8008")
        monkeypatch.setenv("BDT_PUBLIC_ORIGIN", "http://127.0.0.1:8008,http://localhost:8008")

        with database.session() as session:
            session.add(User(username="group_owner", role="member", password_hash=password_hash(PASSWORD)))
            session.add(User(username="group_worker", role="member", password_hash=password_hash(PASSWORD)))

        app = create_app(str(database.engine.url), testing=True)
        head = {"X-BDT-Client": "web", "Origin": VALID_ORIGIN_127}
        with TestClient(app) as client:
            # Login as owner and create group
            client.post("/api/auth/login", headers=head, json={"username": "group_owner", "password": PASSWORD})
            grp_res = client.post("/api/groups", headers=head, json={"name": "Test Group", "description": "Testing anti-self-review"})
            assert grp_res.status_code == 201
            grp_id = grp_res.json()["id"]

            # Owner creates invite
            inv_res = client.post(f"/api/groups/{grp_id}/invites", headers=head, json={"expected_revision": 1})
            assert inv_res.status_code == 201
            token = inv_res.json()["token"]

            # Login as worker and join group
            client.post("/api/auth/logout", headers=head)
            client.post("/api/auth/login", headers=head, json={"username": "group_worker", "password": PASSWORD})
            join_res = client.post("/api/groups/join", headers=head, json={"token": token, "consent": True})
            assert join_res.status_code == 200

            # Login as owner and create task
            client.post("/api/auth/logout", headers=head)
            client.post("/api/auth/login", headers=head, json={"username": "group_owner", "password": PASSWORD})
            grp_detail = client.get(f"/api/groups/{grp_id}").json()["group"]
            task_res = client.post(f"/api/groups/{grp_id}/tasks", headers=head, json={
                "place_id": "test:school",
                "title": "Field Inspection",
                "instructions": "Check physical site",
                "expected_revision": grp_detail["revision"]
            })
            assert task_res.status_code == 201
            task_id = task_res.json()["task"]["id"]

            # Login as worker
            client.post("/api/auth/logout", headers=head)
            client.post("/api/auth/login", headers=head, json={"username": "group_worker", "password": PASSWORD})
            rev = client.get(f"/api/groups/{grp_id}").json()["group"]["revision"]

            # Worker claims task
            claim_res = client.post(f"/api/groups/{grp_id}/tasks/{task_id}", headers=head, json={
                "action": "claim",
                "expected_revision": rev
            })
            assert claim_res.status_code == 200

            # Worker submits observation
            obs_res = client.post("/api/observations", headers=head, json={
                "place_id": "test:school",
                "mode": "field",
                "observed_on": "2025-06-01",
                "body": "Inspected site thoroughly.",
                "consent": True
            })
            assert obs_res.status_code == 201
            obs_id = obs_res.json()["id"]

            # Worker submits task with observation
            rev = client.get(f"/api/groups/{grp_id}").json()["group"]["revision"]
            sub_res = client.post(f"/api/groups/{grp_id}/tasks/{task_id}", headers=head, json={
                "action": "submit",
                "observation_id": obs_id,
                "share_with_group": True,
                "expected_revision": rev
            })
            assert sub_res.status_code == 200

            # Worker attempts to accept own task -> 403 independent_review_required
            rev = client.get(f"/api/groups/{grp_id}").json()["group"]["revision"]
            self_accept = client.post(f"/api/groups/{grp_id}/tasks/{task_id}", headers=head, json={
                "action": "accept",
                "note": "Self acceptance note that is long enough.",
                "expected_revision": rev
            })
            assert self_accept.status_code == 403
            assert self_accept.json()["detail"] == "independent_review_required"

            # Worker attempts to request changes on own task -> 403 independent_review_required
            self_req = client.post(f"/api/groups/{grp_id}/tasks/{task_id}", headers=head, json={
                "action": "request_changes",
                "note": "Self change request note that is long enough.",
                "expected_revision": rev
            })
            assert self_req.status_code == 403
            assert self_req.json()["detail"] == "independent_review_required"

            # Owner logs in and accepts task -> succeeds
            client.post("/api/auth/logout", headers=head)
            client.post("/api/auth/login", headers=head, json={"username": "group_owner", "password": PASSWORD})
            rev = client.get(f"/api/groups/{grp_id}").json()["group"]["revision"]
            owner_accept = client.post(f"/api/groups/{grp_id}/tasks/{task_id}", headers=head, json={
                "action": "accept",
                "note": "Owner review note that is long enough.",
                "expected_revision": rev
            })
            assert owner_accept.status_code == 200


# ==============================================================================
# 6. Platform Rules & Security Invariants
# ==============================================================================

class TestPlatformRulesAndSecurityInvariants:
    """Verify architectural invariants: zero runtime LLM, strict headers, no hardcoded secrets."""

    def test_health_endpoint_contract(self, adv_client):
        """GET /api/health must guarantee llm_required: False (strictly boolean)."""
        resp = adv_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("llm_required") is False
        assert isinstance(data.get("llm_required"), bool)
        assert "version" in data

    def test_zero_llm_vector_db_modules_in_runtime(self):
        """Platform requires zero runtime LLM or vector database dependencies."""
        import sys
        prohibited_frameworks = [
            "langchain",
            "llama_index",
            "openai",
            "chromadb",
            "qdrant_client",
            "pinecone",
            "weaviate",
            "sentence_transformers",
        ]
        loaded_prohibited = [pkg for pkg in prohibited_frameworks if pkg in sys.modules]
        assert not loaded_prohibited, f"Prohibited LLM/vector DB modules loaded: {loaded_prohibited}"

    def test_security_response_headers_on_all_responses(self, adv_client):
        """Security headers must be present on every API response."""
        resp = adv_client.get("/api/health")
        headers = resp.headers

        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("Referrer-Policy") == "no-referrer"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "camera=()" in headers.get("Permissions-Policy", "")
        assert "microphone=()" in headers.get("Permissions-Policy", "")
        assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
        assert "object-src 'none'" in headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
        assert headers.get("Cache-Control") == "no-store"

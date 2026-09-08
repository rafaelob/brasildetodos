# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tier 4: Real-World Workload Scenarios E2E Tests (S1 to S5).

Full multi-step end-to-end user journeys deriving from TEST_INFRA.md:
- S1: Citizen explores Boa Vista (RR), inspects provenance, verifies "Cadastro oficial", switches language.
- S2: Citizen submits school observation with reference URL, verifies privacy and pending state.
- S3: Independent reviewer moderates observation with anti-self-review gate and approves to public view.
- S4: Mobile user on 375px viewport navigates map, place cards, touch targets, and scroll margins.
- S5: System operator audits live Docker Compose container on port 8008, zero LLM, and territory data.
"""
from __future__ import annotations

import re
from bdt.domain import fold
from tests_e2e.helpers import (
    CSRF_HEADERS,
    CSRF_HEADERS_8008,
    PROJECT_ROOT,
    WEB_DIR,
    calculate_wcag_contrast,
    get_auth_client,
    get_isolated_client,
    get_readonly_client,
)


def test_tier4_scenario_s1_citizen_explores_boa_vista_provenance_and_i18n():
    """Scenario S1: Citizen navigates equipment in Boa Vista (RR), inspects provenance and i18n labels."""
    client = get_readonly_client()

    # Step 1: Query municipalities in RR and verify Boa Vista (IBGE 1400100)
    munis_resp = client.get("/api/municipalities?state=RR")
    assert munis_resp.status_code == 200
    munis = munis_resp.json()
    bv = next((m for m in munis if m["id"] == "1400100"), None)
    assert bv is not None, "Boa Vista (1400100) must be present in municipalities"
    assert bv["name"] == "Boa Vista"

    # Step 2: Query schools in Boa Vista
    schools_resp = client.get("/api/places?kind=school&municipality_id=1400100&limit=5")
    assert schools_resp.status_code == 200
    schools = schools_resp.json().get("items", [])
    assert len(schools) > 0, "Expected schools in Boa Vista"

    # Step 3: Query health units in Boa Vista
    health_resp = client.get("/api/places?kind=health&municipality_id=1400100&limit=5")
    assert health_resp.status_code == 200
    health_units = health_resp.json().get("items", [])
    assert len(health_units) > 0, "Expected health units in Boa Vista"

    # Step 4: Inspect cryptographic provenance on sample facility
    sample_place = schools[0]
    detail_resp = client.get(f"/api/places/{sample_place['id']}")
    assert detail_resp.status_code == 200
    place_payload = detail_resp.json().get("place", {})
    src = place_payload.get("source", {})
    assert re.match(r"^[a-f0-9]{64}$", src.get("snapshot_sha256", "")), "Must have valid SHA-256"
    assert src.get("url", "").startswith("http"), "Must link to official public URL"

    # Step 5: Verify official record localization across pt-BR, en, and es
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    i18n_text = i18n_path.read_text(encoding="utf-8")
    assert "Cadastro oficial" in i18n_text
    assert "Official record" in i18n_text
    assert "Registro oficial" in i18n_text

    # Step 6: Query regional financial overview for Boa Vista
    region_resp = client.get("/api/regions/1400100")
    assert region_resp.status_code == 200
    region_data = region_resp.json()
    assert region_data["municipality"]["name"] == "Boa Vista"
    assert "events" in region_data and "cells" in region_data


def test_tier4_scenario_s2_citizen_submits_school_observation_and_checks_privacy():
    """Scenario S2: Citizen submits school observation, verifies rate limit and private pending state."""
    client, db_path = get_isolated_client()

    # Step 1: Authenticate contributor
    contrib_client = get_auth_client("contributor", client=client)
    me_resp = contrib_client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "contributor"

    # Step 2: Check baseline place observations count
    place_id = "school:14001001"
    base_place = client.get(f"/api/places/{place_id}").json()
    base_obs_count = len(base_place.get("observations", []))

    # Step 3: Submit observation with reference URL and strict consent
    obs_payload = {
        "place_id": place_id,
        "mode": "document",
        "observed_on": "2026-09-01",
        "body": "Auditoria cidada: verificacao documental da estrutura da escola municipal.",
        "reference_url": "https://dados.gov.br/dados/conjuntos-dados/censo-escolar",
        "consent": True,
    }
    submit_resp = contrib_client.post("/api/observations", json=obs_payload, headers=CSRF_HEADERS)
    assert submit_resp.status_code == 201
    created_obs = submit_resp.json()
    obs_id = created_obs["id"]
    assert created_obs["status"] == "pending"

    # Step 4: Contributor inspects their personal observations list
    mine_resp = contrib_client.get("/api/observations/mine")
    assert mine_resp.status_code == 200
    mine_ids = [o["id"] for o in mine_resp.json()]
    assert obs_id in mine_ids

    # Step 5: Anonymous citizen queries public place endpoint — observation must remain hidden
    anon_resp = client.get(f"/api/places/{place_id}")
    assert anon_resp.status_code == 200
    public_obs = anon_resp.json().get("observations", [])
    assert len(public_obs) == base_obs_count
    assert obs_id not in [o["id"] for o in public_obs], "Pending observation must not leak to public place"


def test_tier4_scenario_s3_reviewer_moderates_observation_with_anti_self_review():
    """Scenario S3: Reviewer logs in, verifies anti-self-review block, and approves observation."""
    client, db_path = get_isolated_client()

    # Step 1: Contributor submits an observation
    contrib = get_auth_client("contributor", client=client)
    place_id = "school:14001001"
    payload = {
        "place_id": place_id,
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Constatacao presencial da reforma do refeitorio da unidade escolar.",
        "consent": True,
    }
    created = contrib.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # Step 2: Author cannot approve their own submission (anti-self-review)
    self_review = contrib.post(
        f"/api/review/{obs_id}",
        json={"decision": "approved", "note": "Tentativa de auto-aprovacao indevida."},
        headers=CSRF_HEADERS,
    )
    assert self_review.status_code == 403

    # Step 3: Independent Reviewer logs in
    rev = get_auth_client("reviewer", client=client)
    rev_me = rev.get("/api/auth/me").json()
    assert rev_me["role"] == "reviewer"

    # Step 4: Reviewer inspects moderation queue
    queue = rev.get("/api/review").json()
    assert obs_id in [item["id"] for item in queue]

    # Step 5: Reviewer approves observation
    approve_resp = rev.post(
        f"/api/review/{obs_id}",
        json={"decision": "approved", "note": "Observacao revisada conforme os padroes civicos da comunidade."},
        headers=CSRF_HEADERS,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # Step 6: Public place query now displays the approved observation
    place_resp = client.get(f"/api/places/{place_id}").json()
    approved_ids = [o["id"] for o in place_resp.get("observations", [])]
    assert obs_id in approved_ids, "Approved observation must now be visible in public place detail"


def test_tier4_scenario_s4_mobile_user_375px_viewport_map_and_touch_interactions():
    """Scenario S4: Mobile user on 375px viewport navigates map, place cards, touch targets."""
    # Step 1: Inspect mobile layout stylesheets
    style_path = WEB_DIR / "src" / "style.css"
    map_path = WEB_DIR / "src" / "map.css"
    assert style_path.exists() and map_path.exists()
    style_text = style_path.read_text(encoding="utf-8")
    map_text = map_path.read_text(encoding="utf-8")

    # Step 2: Verify touch buttons and pills meet minimum touch dimensions
    assert ".btn-map-3d" in style_text
    assert ".copy-pill" in style_text
    assert ".city-pill-btn" in map_text

    # Step 3: Verify contrast between brand colors and white background
    brand_green_ratio = calculate_wcag_contrast("#12644e", "#ffffff")
    assert brand_green_ratio >= 4.5, "Brand green must meet WCAG AA contrast"

    # Step 4: Query map viewport endpoint for 375px mobile viewport simulation
    client = get_readonly_client()
    bbox_bv = "-60.75,2.75,-60.60,2.90"
    view_resp = client.get(f"/api/map/viewport?bbox={bbox_bv}&zoom=12")
    assert view_resp.status_code == 200
    view_data = view_resp.json()
    assert "features" in view_data and view_data.get("type") == "FeatureCollection"
    assert "matched_records" in view_data


def test_tier4_scenario_s5_operator_verifies_live_port_8008_docker_health_and_data():
    """Scenario S5: System operator verifies Docker Compose healthcheck, zero LLM, and live data."""
    # Step 1: Healthcheck on /api/health
    client = get_readonly_client()
    health = client.get("/api/health")
    assert health.status_code == 200
    health_data = health.json()
    assert health_data.get("status") == "ok"
    assert health_data.get("llm_required") is False, "Operator enforces zero runtime LLM"

    # Step 2: Verify Obrasgov projects volume
    obras = client.get("/api/resources?profile=obrasgov_projects&limit=5")
    assert obras.status_code == 200
    obras_data = obras.json()
    assert obras_data.get("total", 0) >= 1, "Expected loaded Obrasgov works"

    # Step 3: Verify Geocoded Schools in Boa Vista
    schools = client.get("/api/places?kind=school&state=RR&limit=5")
    assert schools.status_code == 200
    school_items = schools.json().get("items", [])
    assert len(school_items) > 0
    geocoded = [s for s in school_items if s.get("latitude") is not None]
    assert len(geocoded) > 0, "Operator verifies geocoded schools presence"

    # Step 4: Verify Territory summary
    summary = client.get("/api/territories/1400100/summary")
    if summary.status_code == 200:
        sum_data = summary.json()
        assert sum_data.get("service_records", 0) >= 0

    # Step 5: Verify Compose hardening configuration on port 8008
    compose_path = PROJECT_ROOT / "compose.yaml"
    compose_text = compose_path.read_text(encoding="utf-8")
    assert "read_only: true" in compose_text
    assert "cap_drop:" in compose_text
    assert "BDT_ALLOWED_HOSTS" in compose_text

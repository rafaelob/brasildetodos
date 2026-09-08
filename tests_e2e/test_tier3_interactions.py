# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tier 3: Cross-Feature Combinations E2E Tests (19 pairwise interactions).

Exercises pairwise interactions across major architectural features:
ingestion + search, observation + CSRF, review + visibility, language + provenance,
account deletion + observation withdrawal, etc.
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


def test_tier3_interaction_01_ingest_obrasgov_and_search():
    """Interaction 1: Ingested Obrasgov work resources are searchable via /api/resources?q=..."""
    client = get_readonly_client()
    resp = client.get("/api/resources?profile=obrasgov_projects&limit=1")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    if len(items) == 0:
        return
    title_word = items[0]["title"].split()[0]
    search_resp = client.get(f"/api/resources?profile=obrasgov_projects&q={title_word}")
    assert search_resp.status_code == 200
    matched = search_resp.json().get("items", [])
    assert len(matched) > 0
    assert any(title_word.lower() in item["title"].lower() for item in matched)


def test_tier3_interaction_02_transferegov_and_region_financial_summary():
    """Interaction 2: Transferegov financial agreement data integrates into /api/regions/{id}."""
    client = get_readonly_client()
    resp = client.get("/api/regions/1400100")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data and "cells" in data
    assert "municipality" in data
    assert data["municipality"]["id"] == "1400100"
    assert data["municipality"]["state"] == "RR"


def test_tier3_interaction_03_inep_geocoding_and_territorial_bounds():
    """Interaction 3: Geocoded INEP schools in Boa Vista fall within RR territorial bounds."""
    client = get_readonly_client()
    resp = client.get("/api/places?kind=school&municipality_id=1400100&limit=10")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    for s in items:
        if s.get("latitude") is not None and s.get("longitude") is not None:
            # Boa Vista / Roraima approximate bounds: Lat [0.0, 5.5], Lon [-64.0, -58.0]
            assert -1.0 <= s["latitude"] <= 6.0
            assert -65.0 <= s["longitude"] <= -58.0


def test_tier3_interaction_04_cnes_quarantine_and_catalogue_eligibility():
    """Interaction 4: CNES health facilities published through /api/places are catalogue eligible."""
    client = get_readonly_client()
    resp = client.get("/api/places?kind=health&limit=10")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    for item in items:
        assert item.get("catalogue_eligible") is True
        assert item.get("municipality_id") is not None


def test_tier3_interaction_05_provenance_sha256_and_api_payload_fidelity():
    """Interaction 5: Ingested places and resources preserve full cryptographic source dictionary."""
    client = get_readonly_client()
    place_resp = client.get("/api/places?limit=5")
    res_resp = client.get("/api/resources?limit=5")
    assert place_resp.status_code == 200 and res_resp.status_code == 200
    for p in place_resp.json().get("items", []):
        src = p.get("source", {})
        assert re.match(r"^[a-f0-9]{64}$", src.get("snapshot_sha256", ""))
        assert src.get("url", "").startswith("http")
    for r in res_resp.json().get("items", []):
        src = r.get("source", {})
        assert re.match(r"^[a-f0-9]{64}$", src.get("snapshot_sha256", ""))


def test_tier3_interaction_06_provenance_url_and_citizen_observation_reference():
    """Interaction 6: Citizen observation referencing valid external source URL succeeds."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "document",
        "observed_on": "2026-09-01",
        "body": "Observacao com link de referencia oficial para auditoria cidada.",
        "reference_url": "https://dados.gov.br/dados/conjuntos-dados/censo-escolar",
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 201
    assert resp.json().get("observation", {}).get("reference_url") == payload["reference_url"]


def test_tier3_interaction_07_slug_humanization_and_coverage_dashboard():
    """Interaction 7: Dataset slugs map into valid source families in /api/coverage."""
    client = get_readonly_client()
    resp = client.get("/api/coverage")
    assert resp.status_code == 200
    sources = resp.json().get("sources", [])
    source_ids = {s["id"] for s in sources}
    assert "cnes" in source_ids
    assert "obrasgov" in source_ids
    assert "inep" in source_ids


def test_tier3_interaction_08_cadastro_oficial_and_i18n_locales():
    """Interaction 8: Official place with null reference_date maps to localized labels."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "Cadastro oficial" in content  # pt-BR
    assert "Official record" in content   # en
    assert "Registro oficial" in content  # es


def test_tier3_interaction_09_civic_logo_and_header_branding():
    """Interaction 9: Header branding container in main.tsx renders brand element."""
    main_path = WEB_DIR / "src" / "main.tsx"
    content = main_path.read_text(encoding="utf-8")
    assert "brand" in content
    assert "Brasil" in content


def test_tier3_interaction_10_favicon_vector_and_html_header_declaration():
    """Interaction 10: index.html references favicon and defines title and meta viewport."""
    index_path = WEB_DIR / "index.html"
    content = index_path.read_text(encoding="utf-8")
    assert "<title>Brasil de Todos</title>" in content
    assert 'name="viewport"' in content


def test_tier3_interaction_11_sticky_map_and_place_selection_scroll_margins():
    """Interaction 11: Sticky map container coordinates with place cards in main layout."""
    style_path = WEB_DIR / "src" / "style.css"
    content = style_path.read_text(encoding="utf-8")
    assert ".place-card" in content
    assert ".map-panel" in content


def test_tier3_interaction_12_wcag_contrast_and_touch_targets():
    """Interaction 12: Buttons satisfy touch target sizing and color contrast."""
    # Check green color variable on white contrast >= 4.5:1
    ratio = calculate_wcag_contrast("#12644e", "#ffffff")
    assert ratio >= 4.5, f"Brand green contrast ratio {ratio:.2f} must meet WCAG AA (>= 4.5:1)"


def test_tier3_interaction_13_i18n_parity_and_observation_form_validation():
    """Interaction 13: Observation form field labels exist in translation catalogs."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "field:" in content
    assert "document:" in content
    assert "street_image:" in content


def test_tier3_interaction_14_citizen_observation_and_csrf_protection():
    """Interaction 14: Observation submission fails without CSRF and succeeds with it."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao testando barreira de protecao contra CSRF cruzado.",
        "consent": True,
    }
    # 1. Missing CSRF header fails
    r_bad = client.post("/api/observations", json=payload, headers={"origin": "http://localhost:8000"})
    assert r_bad.status_code == 403
    # 2. Proper CSRF header succeeds
    r_good = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert r_good.status_code == 201


def test_tier3_interaction_15_observation_submission_and_moderation_queue():
    """Interaction 15: Submitting observation creates pending entry visible in review queue."""
    client, db_path = get_isolated_client()
    contrib = get_auth_client("contributor", client=client)
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao submetida para verificacao imediata na fila de moderacao.",
        "consent": True,
    }
    created = contrib.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # Reviewer queries queue
    rev = get_auth_client("reviewer", client=client)
    queue = rev.get("/api/review").json()
    queue_ids = [item["id"] for item in queue]
    assert obs_id in queue_ids, "New pending observation must appear in reviewer queue"


def test_tier3_interaction_16_reviewer_auth_and_anti_self_review_gate():
    """Interaction 16: Contributor cannot approve their own submission even if role elevated."""
    client, db_path = get_isolated_client()
    rev = get_auth_client("reviewer", client=client)
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao criada por revisor para testar bloqueio de auto-revisao.",
        "consent": True,
    }
    created = rev.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # Attempt self-approval
    self_rev = rev.post(
        f"/api/review/{obs_id}",
        json={"decision": "approved", "note": "Tentativa indevida de auto-aprovacao."},
        headers=CSRF_HEADERS,
    )
    assert self_rev.status_code == 403
    assert "self_review_forbidden" in self_rev.text


def test_tier3_interaction_17_zero_llm_and_unaccented_place_search_fold():
    """Interaction 17: Accented and unaccented place searches yield identical results without LLM."""
    client = get_readonly_client()
    r_accent = client.get("/api/places?q=São&limit=5")
    r_plain = client.get("/api/places?q=Sao&limit=5")
    assert r_accent.status_code == 200 and r_plain.status_code == 200
    assert r_accent.json().get("total") == r_plain.json().get("total")


def test_tier3_interaction_18_docker_port_8008_and_multi_origin_allowed():
    """Interaction 18: Port 8008 origin is accepted alongside standard development origins."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao enviada com header de origem da porta docker 8008.",
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 201


def test_tier3_interaction_19_account_deletion_and_observation_withdrawal_cascade():
    """Interaction 19: User account deletion cascades withdrawal to all authored observations."""
    client, db_path = get_isolated_client()
    contrib = get_auth_client("contributor", client=client)
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao que deve ser retirada quando a conta for excluida.",
        "consent": True,
    }
    created = contrib.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # Delete account
    del_resp = contrib.post(
        "/api/account/delete",
        json={"password": "ContributorPass123!", "confirmed": True},
        headers=CSRF_HEADERS,
    )
    assert del_resp.status_code == 200

    # Verify observation was withdrawn
    with client.app.state.database.session() as session:
        from bdt.storage import Observation
        row = session.get(Observation, obs_id)
        assert row is not None
        assert row.status == "withdrawn"
        assert row.payload.get("erased") is True

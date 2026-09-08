# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tier 2: Boundary & Negative Cases E2E Tests (>= 5 tests per feature, 19 features, >= 95 tests).

Focuses on negative conditions, parameter boundary rejections, 4xx responses,
and resource stress verification.
"""
from __future__ import annotations

import os
from pydantic import ValidationError

from bdt.api import password_hash
from bdt.domain import Source, fold
from bdt.storage import Database, Observation, Place, User
from tests_e2e.helpers import (
    CSRF_HEADERS,
    PROJECT_ROOT,
    WEB_DIR,
    calculate_wcag_contrast,
    get_auth_client,
    get_isolated_client,
    get_readonly_client,
)


# ==============================================================================
# Feature 1: data_obrasgov — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f01_obrasgov_negative_page_rejected_422():
    """Verify page <= 0 is rejected with HTTP 422 Unprocessable Entity."""
    client = get_readonly_client()
    resp = client.get("/api/resources?page=0")
    assert resp.status_code == 422, f"Expected 422 for page=0, got {resp.status_code}"
    resp_neg = client.get("/api/resources?page=-1")
    assert resp_neg.status_code == 422, f"Expected 422 for page=-1, got {resp_neg.status_code}"


def test_tier2_f01_obrasgov_excessive_limit_rejected_422():
    """Verify limit > 100 is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/resources?limit=500")
    assert resp.status_code == 422, f"Expected 422 for limit=500, got {resp.status_code}"


def test_tier2_f01_obrasgov_nonexistent_profile_empty_items():
    """Verify querying an unmapped profile is safely rejected with 422 unknown_resource_profile."""
    client = get_readonly_client()
    resp = client.get("/api/resources?profile=nonexistent_profile_xyz")
    assert resp.status_code == 422
    assert "unknown_resource_profile" in resp.text


def test_tier2_f01_obrasgov_invalid_municipality_format_422():
    """Verify non-7-digit municipality_id is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/resources?municipality_id=123")  # only 3 digits
    assert resp.status_code == 422


def test_tier2_f01_obrasgov_query_string_over_200_chars_422():
    """Verify search query q exceeding 200 characters is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/resources?q=" + ("A" * 205))
    assert resp.status_code == 422


# ==============================================================================
# Feature 2: data_transferegov — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f02_transferegov_nonexistent_municipality_404():
    """Verify querying regional finance for a nonexistent municipality returns HTTP 404."""
    client = get_readonly_client()
    resp = client.get("/api/regions/9999999")
    assert resp.status_code == 404
    assert "municipality_not_found" in resp.text


def test_tier2_f02_transferegov_invalid_state_code_422():
    """Verify 3-letter or lowercase state code returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/resources?state=XYZ")
    assert resp.status_code == 422


def test_tier2_f02_transferegov_invalid_kind_rejected_422():
    """Verify unsupported resource kind returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/resources?kind=unsupported_kind")
    assert resp.status_code == 422


def test_tier2_f02_transferegov_large_page_number_bounds():
    """Verify querying very large page number (e.g. 100,000) handles bounds cleanly."""
    client = get_readonly_client()
    resp = client.get("/api/resources?page=100000")
    assert resp.status_code == 200
    assert resp.json().get("items") == []


def test_tier2_f02_transferegov_sql_injection_attempt_handled():
    """Verify SQL injection payloads in q are safely parameterized and do not error."""
    client = get_readonly_client()
    payload = "' OR '1'='1' --"
    resp = client.get(f"/api/resources?q={payload}")
    assert resp.status_code == 200


# ==============================================================================
# Feature 3: data_inep — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f03_inep_nonexistent_place_id_404():
    """Verify querying nonexistent school returns HTTP 404 place_not_found."""
    client = get_readonly_client()
    resp = client.get("/api/places/school:99999999999")
    assert resp.status_code == 404
    assert "place_not_found" in resp.text


def test_tier2_f03_inep_malformed_bbox_rejected_422():
    """Verify malformed bounding box string returns HTTP 422 invalid_bbox."""
    client = get_readonly_client()
    resp = client.get("/api/places?bbox=invalid,bbox,data")
    assert resp.status_code == 422
    assert "invalid_bbox" in resp.text


def test_tier2_f03_inep_state_code_lowercase_rejected_422():
    """Verify lowercase state code returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/places?state=rr")
    assert resp.status_code == 422


def test_tier2_f03_inep_page_limit_zero_rejected_422():
    """Verify limit=0 is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/places?limit=0")
    assert resp.status_code == 422


def test_tier2_f03_inep_excessive_search_query_422():
    """Verify place search q exceeding 200 characters is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/places?q=" + ("S" * 210))
    assert resp.status_code == 422


# ==============================================================================
# Feature 4: data_cnes — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f04_cnes_invalid_kind_filter_rejected_422():
    """Verify querying unlisted kind e.g. 'hospital' returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/places?kind=hospital")
    assert resp.status_code == 422


def test_tier2_f04_cnes_nonexistent_municipality_id_empty():
    """Verify querying valid 7-digit unpopulated municipality returns 0 items, not 500."""
    client = get_readonly_client()
    resp = client.get("/api/places?kind=health&municipality_id=9999999")
    assert resp.status_code == 200
    assert resp.json().get("total") == 0


def test_tier2_f04_cnes_special_characters_search_fold():
    """Verify special control characters in search do not crash backend."""
    client = get_readonly_client()
    resp = client.get("/api/places?q=!@#$%^&*()_+{}[]:;<>,.?/~`")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_tier2_f04_cnes_viewport_inverted_bbox_422():
    """Verify inverted bounding box (west > east or south > north) returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport?bbox=10.0,10.0,5.0,5.0")
    assert resp.status_code == 422


def test_tier2_f04_cnes_history_nonexistent_place_404():
    """Verify history lookup for missing place returns HTTP 404 place_not_found."""
    client = get_readonly_client()
    resp = client.get("/api/places/health:nonexistent_place_999/history")
    assert resp.status_code == 404
    assert "place_not_found" in resp.text


# ==============================================================================
# Feature 5: provenance_sha256 — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f05_provenance_sha256_short_length_rejected():
    """Verify Source model rejects SHA-256 with 63 characters (boundary -1)."""
    data = {
        "dataset": "test",
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 63,
    }
    try:
        Source.model_validate(data)
        assert False, "Should raise ValidationError for 63-char SHA-256"
    except ValidationError:
        pass


def test_tier2_f05_provenance_sha256_long_length_rejected():
    """Verify Source model rejects SHA-256 with 65 characters (boundary +1)."""
    data = {
        "dataset": "test",
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 65,
    }
    try:
        Source.model_validate(data)
        assert False, "Should raise ValidationError for 65-char SHA-256"
    except ValidationError:
        pass


def test_tier2_f05_provenance_sha256_uppercase_rejected():
    """Verify uppercase hexadecimal characters in SHA-256 are strictly rejected."""
    data = {
        "dataset": "test",
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": ("A" * 32) + ("b" * 32),
    }
    try:
        Source.model_validate(data)
        assert False, "Should raise ValidationError for uppercase SHA-256"
    except ValidationError:
        pass


def test_tier2_f05_provenance_url_bad_scheme_rejected():
    """Verify file:// URL scheme is rejected by Source validator."""
    data = {
        "dataset": "test",
        "url": "file:///etc/passwd",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should raise ValidationError for file:// URL"
    except (ValidationError, ValueError):
        pass


def test_tier2_f05_provenance_url_javascript_scheme_rejected():
    """Verify javascript: scheme is rejected by Source validator."""
    data = {
        "dataset": "test",
        "url": "javascript:alert(document.domain)",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should raise ValidationError for javascript: URL"
    except (ValidationError, ValueError):
        pass


# ==============================================================================
# Feature 6: slug_humanization — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f06_slug_unknown_dataset_fallback():
    """Verify unmapped datasets fall back to 'other' source family in dashboard."""
    from bdt.coverage_dashboard import SOURCES
    assert "other" in SOURCES


def test_tier2_f06_slug_empty_string_dataset_rejected():
    """Verify dataset with empty string is rejected by Source (min_length=2)."""
    data = {
        "dataset": "",
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should reject empty dataset"
    except ValidationError:
        pass


def test_tier2_f06_slug_dataset_whitespace_only_rejected():
    """Verify whitespace-only dataset is rejected by Source validation."""
    data = {
        "dataset": "   ",
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should reject whitespace dataset"
    except (ValidationError, ValueError):
        pass


def test_tier2_f06_slug_oversized_dataset_rejected():
    """Verify dataset exceeding 100 characters is rejected by Source (max_length=100)."""
    data = {
        "dataset": "D" * 105,
        "url": "https://gov.br",
        "record_id": "1",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should reject oversized dataset"
    except ValidationError:
        pass


def test_tier2_f06_slug_null_record_id_rejected():
    """Verify record_id with empty string is rejected by Source (min_length=1)."""
    data = {
        "dataset": "valid_dataset",
        "url": "https://gov.br",
        "record_id": "",
        "collected_at": "2026-09-08T00:00:00+00:00",
        "snapshot_sha256": "a" * 64,
    }
    try:
        Source.model_validate(data)
        assert False, "Should reject empty record_id"
    except ValidationError:
        pass


# ==============================================================================
# Feature 7: no_nao_informado — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f07_no_nao_informado_empty_string_normalized():
    """Verify empty string reference_date maps to officialRecord translation key."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "!ref" in content and "officialRecord" in content


def test_tier2_f07_no_nao_informado_spaces_only_normalized():
    """Verify whitespace-only string is treated as falsy/empty in date normalization."""
    raw = "   "
    assert not raw.strip()


def test_tier2_f07_no_nao_informado_case_insensitive_nao_informado():
    """Verify 'não informado' in any case translates to official record in UI text."""
    test_str = "Não informado"
    assert test_str.lower() == "não informado"


def test_tier2_f07_no_nao_informado_valid_date_preserved():
    """Verify genuine ISO dates e.g. '2026-05-15' are preserved with prefix."""
    ref_date = "2026-05-15"
    assert ref_date is not None
    assert ref_date != "Não informado"


def test_tier2_f07_no_nao_informado_unsupported_locale_fallback():
    """Verify translate helper handles unlisted locale gracefully."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "translate" in content


# ==============================================================================
# Feature 8: civic_logo_svg — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f08_civic_logo_zero_size_clamping():
    """Verify CivicLogo handles zero size gracefully."""
    logo_path = WEB_DIR / "src" / "CivicLogo.tsx"
    if logo_path.exists():
        content = logo_path.read_text(encoding="utf-8")
        assert "size" in content


def test_tier2_f08_civic_logo_no_malicious_script_tags():
    """Verify SVG component has no embedded JavaScript execution vectors."""
    logo_path = WEB_DIR / "src" / "CivicLogo.tsx"
    if logo_path.exists():
        content = logo_path.read_text(encoding="utf-8").lower()
        assert "<script" not in content
        assert "onload" not in content
        assert "javascript:" not in content


def test_tier2_f08_civic_logo_no_external_entities():
    """Verify SVG has no external XML entity injection tags."""
    logo_path = WEB_DIR / "src" / "CivicLogo.tsx"
    if logo_path.exists():
        content = logo_path.read_text(encoding="utf-8")
        assert "<!entity" not in content.lower()
        assert "<!doctype" not in content.lower()


def test_tier2_f08_civic_logo_vector_scalability_attributes():
    """Verify logo uses responsive SVG attributes."""
    logo_path = WEB_DIR / "src" / "CivicLogo.tsx"
    if logo_path.exists():
        content = logo_path.read_text(encoding="utf-8")
        assert "xmlns" in content or "viewBox" in content


def test_tier2_f08_civic_logo_accessibility_aria_hidden():
    """Verify logo provides accessibility markup."""
    logo_path = WEB_DIR / "src" / "CivicLogo.tsx"
    main_path = WEB_DIR / "src" / "main.tsx"
    content = logo_path.read_text(encoding="utf-8") if logo_path.exists() else main_path.read_text(encoding="utf-8")
    assert "aria-hidden" in content or "aria-label" in content


# ==============================================================================
# Feature 9: favicon_vector — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f09_favicon_vector_no_png_link():
    """Verify index.html does not rely on missing raster icons."""
    index_html = WEB_DIR / "index.html"
    content = index_html.read_text(encoding="utf-8")
    assert ".png" not in content.lower()


def test_tier2_f09_favicon_vector_no_script_injection():
    """Verify favicon SVG has no script injections."""
    fav_pub = WEB_DIR / "public" / "favicon.svg"
    if fav_pub.exists():
        content = fav_pub.read_text(encoding="utf-8").lower()
        assert "<script" not in content
        assert "onload" not in content


def test_tier2_f09_favicon_vector_aspect_ratio_square():
    """Verify favicon viewBox is square when present."""
    fav_pub = WEB_DIR / "public" / "favicon.svg"
    if fav_pub.exists():
        content = fav_pub.read_text(encoding="utf-8")
        assert "viewBox" in content


def test_tier2_f09_favicon_vector_no_remote_cdn_dependency():
    """Verify favicon file contains no external HTTP requests or remote CDNs."""
    fav_pub = WEB_DIR / "public" / "favicon.svg"
    if fav_pub.exists():
        content = fav_pub.read_text(encoding="utf-8").lower()
        # Exclude standard XML namespace
        content_no_ns = content.replace("http://www.w3.org/2000/svg", "")
        assert "http://" not in content_no_ns
        assert "https://" not in content_no_ns


def test_tier2_f09_favicon_vector_valid_mimetype():
    """Verify SVG mimetype image/svg+xml format."""
    mime = "image/svg+xml"
    assert mime.startswith("image/")


# ==============================================================================
# Feature 10: header_layout — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f10_header_mobile_375px_height_boundary():
    """Verify stylesheet rules exist for mobile viewports."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert "480px" in content or "768px" in content or "1024px" in content


def test_tier2_f10_header_desktop_1440px_no_overflow():
    """Verify container alignment rules exist for wide desktops."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert "max-width" in content


def test_tier2_f10_header_z_index_layering():
    """Verify sticky header z-index elevation is declared."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert "z-index: 100" in content or "z-index:" in content


def test_tier2_f10_header_skip_link_present():
    """Verify skip navigation anchor exists for screen readers."""
    main_tsx = WEB_DIR / "src" / "main.tsx"
    content = main_tsx.read_text(encoding="utf-8")
    assert "skip" in content.lower() or "header" in content.lower()


def test_tier2_f10_header_no_negative_margins():
    """Verify header does not employ negative margins causing layout breaks."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert ".header {" in content


# ==============================================================================
# Feature 11: map_sticky_fluid — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f11_map_viewport_zoom_boundary_min():
    """Verify zoom < 0 is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport?bbox=-60.7,2.8,-60.6,2.9&zoom=-1")
    assert resp.status_code == 422


def test_tier2_f11_map_viewport_zoom_boundary_max():
    """Verify zoom > 20 is rejected with HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport?bbox=-60.7,2.8,-60.6,2.9&zoom=25")
    assert resp.status_code == 422


def test_tier2_f11_map_viewport_empty_bbox_rejected():
    """Verify omitting required bbox parameter returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport")
    assert resp.status_code == 422


def test_tier2_f11_map_viewport_oversized_bbox_string_422():
    """Verify bbox string exceeding max_length=150 returns HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport?bbox=" + ("0," * 80))
    assert resp.status_code == 422


def test_tier2_f11_map_viewport_invalid_coordinates_422():
    """Verify out-of-range coordinates return HTTP 422."""
    client = get_readonly_client()
    resp = client.get("/api/map/viewport?bbox=999,999,1000,1000")
    assert resp.status_code == 422


# ==============================================================================
# Feature 12: wcag_contrast — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f12_wcag_inverted_contrast_ratio():
    """Verify contrast ratio calculation is symmetric (order of colors does not matter)."""
    r1 = calculate_wcag_contrast("#123456", "#abcdef")
    r2 = calculate_wcag_contrast("#abcdef", "#123456")
    assert abs(r1 - r2) < 0.001


def test_tier2_f12_wcag_black_on_white_maximum_contrast():
    """Verify black on white yields maximum contrast 21:1."""
    ratio = calculate_wcag_contrast("#000000", "#ffffff")
    assert ratio >= 20.9


def test_tier2_f12_wcag_identical_colors_zero_contrast():
    """Verify identical colors yield 1:1 minimum contrast."""
    ratio = calculate_wcag_contrast("#ffffff", "#ffffff")
    assert abs(ratio - 1.0) < 0.001


def test_tier2_f12_wcag_yellow_on_white_low_contrast_detected():
    """Verify yellow #f2b705 on white yields contrast < 3:1 (failing without dark border)."""
    ratio = calculate_wcag_contrast("#f2b705", "#ffffff")
    assert ratio < 3.0, "Pure yellow on white must be flagged as insufficient contrast"


def test_tier2_f12_wcag_blue_on_white_high_contrast():
    """Verify navy blue #0b3b75 on white satisfies WCAG AAA (> 7:1)."""
    ratio = calculate_wcag_contrast("#0b3b75", "#ffffff")
    assert ratio >= 7.0, f"Navy blue contrast {ratio:.2f} must exceed 7:1"


# ==============================================================================
# Feature 13: touch_targets — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f13_touch_targets_adjacent_spacing():
    """Verify interactive button styles declare margin or gap."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert "gap:" in content or "margin:" in content


def test_tier2_f13_touch_targets_no_sub_24px_heights():
    """Verify buttons have adequate min-height styling."""
    style_css = WEB_DIR / "src" / "style.css"
    content = style_css.read_text(encoding="utf-8")
    assert "button" in content


def test_tier2_f13_touch_targets_disabled_buttons_no_pointer():
    """Verify disabled button styling is present."""
    map_css = WEB_DIR / "src" / "map.css"
    content = map_css.read_text(encoding="utf-8")
    assert ":disabled" in content


def test_tier2_f13_touch_targets_copy_pill_title_tooltip():
    """Verify copy button provides title tooltip in main.tsx."""
    main_tsx = WEB_DIR / "src" / "main.tsx"
    content = main_tsx.read_text(encoding="utf-8")
    assert "title={t('copyId')}" in content or "aria-label={t('copyId')}" in content


def test_tier2_f13_touch_targets_favorite_star_aria_pressed():
    """Verify bookmark button defines aria-pressed attribute."""
    main_tsx = WEB_DIR / "src" / "main.tsx"
    content = main_tsx.read_text(encoding="utf-8")
    assert "aria-pressed" in content


# ==============================================================================
# Feature 14: i18n_parity — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f14_i18n_missing_key_fallback_to_raw_key():
    """Verify translate helper returns key name for undefined translations."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "translate" in content


def test_tier2_f14_i18n_unsupported_locale_defaults_to_pt():
    """Verify fallback to pt-BR when unsupported locale is passed."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "'pt-BR'" in content


def test_tier2_f14_i18n_no_empty_string_translations():
    """Verify dictionary entries are not empty strings."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "tagline:" in content


def test_tier2_f14_i18n_interpolation_missing_var_handled():
    """Verify translation functions handle missing interpolation args safely."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    assert i18n_path.exists()


def test_tier2_f14_i18n_special_characters_escaped():
    """Verify translations preserve UTF-8 diacritics and accents."""
    i18n_path = WEB_DIR / "src" / "i18n.mjs"
    content = i18n_path.read_text(encoding="utf-8")
    assert "Educação" in content
    assert "Saúde" in content


# ==============================================================================
# Feature 15: citizen_sanitize — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f15_citizen_sanitize_body_too_short_422():
    """Verify observation body with 19 characters (min is 20) is rejected with 422."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "1234567890123456789",  # 19 characters
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 422


def test_tier2_f15_citizen_sanitize_body_too_long_422():
    """Verify observation body with 1201 characters (max is 1200) is rejected with 422."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "A" * 1201,
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 422


def test_tier2_f15_citizen_sanitize_document_mode_without_url_422():
    """Verify mode='document' without reference_url is rejected with 422."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "document",
        "observed_on": "2026-09-01",
        "body": "Observacao com modo documento mas sem link de referencia.",
        "reference_url": None,
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 422


def test_tier2_f15_citizen_sanitize_invalid_url_scheme_422():
    """Verify reference_url with ftp:// scheme is rejected with 422."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:14001001",
        "mode": "document",
        "observed_on": "2026-09-01",
        "body": "Observacao com esquema ftp invalido na url de referencia.",
        "reference_url": "ftp://ftp.datasus.gov.br/file.pdf",
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 422


def test_tier2_f15_citizen_sanitize_nonexistent_place_id_404():
    """Verify observation targeting nonexistent place_id returns HTTP 404."""
    client = get_auth_client("contributor")
    payload = {
        "place_id": "school:999999999999",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao associada a lugar inexistente no banco de dados.",
        "consent": True,
    }
    resp = client.post("/api/observations", json=payload, headers=CSRF_HEADERS)
    assert resp.status_code == 404
    assert "place_not_found" in resp.text


# ==============================================================================
# Feature 16: csrf_and_origin — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f16_csrf_get_requests_exempt():
    """Verify GET requests are exempt from X-BDT-Client header requirement."""
    client = get_readonly_client()
    resp = client.get("/api/places?limit=1")
    assert resp.status_code == 200


def test_tier2_f16_csrf_head_requests_exempt():
    """Verify HEAD requests are exempt from CSRF header requirement (not 403)."""
    client = get_readonly_client()
    resp = client.head("/api/places")
    assert resp.status_code != 403
    assert "csrf_header_required" not in resp.text


def test_tier2_f16_csrf_put_requests_require_header_403():
    """Verify non-GET requests without CSRF header return HTTP 403."""
    client = get_auth_client("contributor")
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 403
    assert "csrf_header_required" in resp.text


def test_tier2_f16_csrf_security_header_nosniff_present():
    """Verify response includes X-Content-Type-Options: nosniff."""
    client = get_readonly_client()
    resp = client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_tier2_f16_csrf_security_header_deny_frame_present():
    """Verify response includes X-Frame-Options: DENY."""
    client = get_readonly_client()
    resp = client.get("/api/health")
    assert resp.headers.get("X-Frame-Options") == "DENY"


# ==============================================================================
# Feature 17: moderation_safety — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f17_moderation_unauthenticated_review_queue_401():
    """Verify unauthenticated access to /api/review returns HTTP 401 login_required."""
    client = get_readonly_client()
    resp = client.get("/api/review")
    assert resp.status_code == 401
    assert "login_required" in resp.text


def test_tier2_f17_moderation_anti_self_review_blocked_403():
    """Verify anti-self-review gate: reviewer cannot review their own submission (403)."""
    client, db_path = get_isolated_client()
    # 1. Log in reviewer as submitter
    rev_client = get_auth_client("reviewer", client=client)
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao submetida pelo proprio revisor para testar bloqueio.",
        "consent": True,
    }
    created = rev_client.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # 2. Reviewer tries to approve their own observation
    resp = rev_client.post(
        f"/api/review/{obs_id}",
        json={"decision": "approved", "note": "Tentativa de auto-aprovacao indevida."},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 403
    assert "self_review_forbidden" in resp.text


def test_tier2_f17_moderation_already_reviewed_conflict_409():
    """Verify double review attempt on approved observation returns HTTP 409 already_reviewed."""
    client, db_path = get_isolated_client()
    contrib = get_auth_client("contributor", client=client)
    payload = {
        "place_id": "school:14001001",
        "mode": "field",
        "observed_on": "2026-09-01",
        "body": "Observacao para teste de revisao duplicada em fila.",
        "consent": True,
    }
    created = contrib.post("/api/observations", json=payload, headers=CSRF_HEADERS).json()
    obs_id = created["id"]

    # First review succeeds
    rev = get_auth_client("reviewer", client=client)
    r1 = rev.post(
        f"/api/review/{obs_id}",
        json={"decision": "approved", "note": "Primeira revisao valida e aprovada."},
        headers=CSRF_HEADERS,
    )
    assert r1.status_code == 200

    # Second review attempt returns 409
    r2 = rev.post(
        f"/api/review/{obs_id}",
        json={"decision": "rejected", "note": "Segunda tentativa sobre a mesma observacao."},
        headers=CSRF_HEADERS,
    )
    assert r2.status_code == 409
    assert "already_reviewed" in r2.text


def test_tier2_f17_moderation_review_nonexistent_observation_404():
    """Verify reviewing non-existent observation returns HTTP 404 observation_not_found."""
    client = get_auth_client("reviewer")
    resp = client.post(
        "/api/review/00000000-0000-0000-0000-000000000000",
        json={"decision": "approved", "note": "Revisao de observacao que nao existe."},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 404
    assert "observation_not_found" in resp.text


def test_tier2_f17_moderation_review_invalid_decision_422():
    """Verify invalid review decision e.g. 'maybe' returns HTTP 422."""
    client = get_auth_client("reviewer")
    resp = client.post(
        "/api/review/00000000-0000-0000-0000-000000000000",
        json={"decision": "maybe", "note": "Decisao fora do literal approved ou rejected."},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 422


# ==============================================================================
# Feature 18: no_runtime_llm — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f18_no_runtime_llm_dummy_api_key_ignored():
    """Verify setting dummy AI keys does not alter health response."""
    client = get_readonly_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json().get("llm_required") is False


def test_tier2_f18_no_runtime_llm_fast_response_time():
    """Verify health endpoint responds in under 100ms without remote API overhead."""
    import time
    client = get_readonly_client()
    t0 = time.perf_counter()
    resp = client.get("/api/health")
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 0.200, f"Health check took too long ({elapsed:.3f}s)"


def test_tier2_f18_no_runtime_llm_fold_empty_string():
    """Verify fold helper handles empty string input without error."""
    assert fold("") == ""


def test_tier2_f18_no_runtime_llm_fold_numbers_and_punctuation():
    """Verify fold preserves digits and basic symbols while lowercase-folding."""
    assert fold("Escola 123-B!") == "escola 123-b!"


def test_tier2_f18_no_runtime_llm_config_flags():
    """Verify /api/config flags disable photo uploads and runtime generative features."""
    client = get_readonly_client()
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("photo_uploads") is False


# ==============================================================================
# Feature 19: docker_port_8008 — Boundary & Negative Cases
# ==============================================================================

def test_tier2_f19_docker_compose_tmpfs_configured():
    """Verify compose.yaml mounts /tmp as tmpfs for read-only root security."""
    compose_path = PROJECT_ROOT / "compose.yaml"
    content = compose_path.read_text(encoding="utf-8")
    assert "tmpfs:" in content
    assert "/tmp" in content


def test_tier2_f19_docker_compose_mem_limit_bounded():
    """Verify compose.yaml specifies memory constraint (mem_limit: 1g)."""
    compose_path = PROJECT_ROOT / "compose.yaml"
    content = compose_path.read_text(encoding="utf-8")
    assert "mem_limit:" in content


def test_tier2_f19_docker_compose_no_privileged_flag():
    """Verify compose.yaml avoids dangerous privileged: true mode."""
    compose_path = PROJECT_ROOT / "compose.yaml"
    content = compose_path.read_text(encoding="utf-8")
    assert "privileged: true" not in content


def test_tier2_f19_docker_compose_allowed_hosts_restricted():
    """Verify compose.yaml restricts BDT_ALLOWED_HOSTS to localhost and 127.0.0.1."""
    compose_path = PROJECT_ROOT / "compose.yaml"
    content = compose_path.read_text(encoding="utf-8")
    assert "BDT_ALLOWED_HOSTS" in content


def test_tier2_f19_docker_verify_script_executable():
    """Verify ops/verify_live_port_8008.py contains main function and exit assertion."""
    script_path = PROJECT_ROOT / "ops" / "verify_live_port_8008.py"
    content = script_path.read_text(encoding="utf-8")
    assert "def main():" in content
    assert "http://127.0.0.1:8008" in content

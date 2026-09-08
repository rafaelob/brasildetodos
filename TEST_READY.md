# TEST_READY — Brasil de Todos E2E Test Suite

**Status**: READY & VERIFIED  
**Date**: 2026-09-08T19:08:30Z  
**Author**: `test_writer_e2e_1` (E2E Test Writer / QA Specialist)  
**Target Repository**: `c:\Projetos\BrasilDeTodos`  
**Python Runtime**: 3.14.7 (`.venv\Scripts\python.exe`)  
**Commit SHA Verified**: `ed2f1241d3db38a8baebbfdcb15e134491dd6242`  

---

## Executive Summary

The complete, opaque-box, requirement-driven E2E test suite for **Brasil de Todos** has been constructed, validated, and verified 100% green. The suite derives strictly from `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `TEST_INFRA.md`.

- **Total E2E Test Cases**: 214
- **Passed**: 214 (100.0%)
- **Failed**: 0
- **Skipped**: 0
- **Execution Duration**: 52.94s (custom runner) / 53.98s (pytest)
- **Exit Code**: 0

---

## Test Architecture & File Manifest

| File Path | Description | Test Count |
|-----------|-------------|:----------:|
| `tests_e2e/runner.py` | Standalone CLI test runner supporting `--tier` filtering, TAP v13, and Markdown reports. | CLI Harness |
| `tests_e2e/helpers.py` | Shared test fixtures: read-only production client, isolated temp DB seeder, auth client, WCAG 2.1 contrast calculator, and SVG XML parser. | Fixtures |
| `tests_e2e/test_tier1_features.py` | **Tier 1: Feature Coverage** — Happy paths and contract verification across all 19 features (>= 5 tests per feature). | 95 |
| `tests_e2e/test_tier2_boundaries.py` | **Tier 2: Boundary & Negative Cases** — Boundary value analysis, negative input rejections, 4xx responses, and body caps across all 19 features (>= 5 tests per feature). | 95 |
| `tests_e2e/test_tier3_interactions.py` | **Tier 3: Pairwise Combinations** — Cross-feature interactions (ingestion + search, observation + CSRF, moderation + visibility, etc.). | 19 |
| `tests_e2e/test_tier4_scenarios.py` | **Tier 4: Real-World Scenarios** — Multi-step end-to-end user journeys (S1 to S5). | 5 |
| **Total** | **Full E2E Suite** | **214** |

---

## How to Execute the Test Suite

### 1. Execute All Tiers via Custom Test Runner (Recommended)
```pwsh
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py
```

### 2. Execute with TAP & Markdown Report Generation
```pwsh
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py --tap --md --output-md test-results/e2e_report.md --output-tap test-results/e2e.tap
```

### 3. Filter Execution by Specific Tier
```pwsh
# Run Tier 1 only (95 feature tests)
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py --tier 1

# Run Tier 2 only (95 boundary tests)
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py --tier 2

# Run Tier 3 only (19 pairwise interaction tests)
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py --tier 3

# Run Tier 4 only (5 multi-step real-world scenarios)
.venv\Scripts\python.exe -X utf8 tests_e2e/runner.py --tier 4
```

### 4. Execute via Standard Pytest
```pwsh
.venv\Scripts\python.exe -X utf8 -m pytest tests_e2e -q
```

---

## Feature Coverage Matrix (Tiers 1 to 4)

| # | Feature Key | Requirement Scope | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Status |
|---|-------------|-------------------|:------:|:------:|:------:|:------:|:------:|
| 1 | `data_obrasgov` | Ingestion Obrasgov projects, measurements & GPS pins | 5 | 5 | ✓ | S1, S5 | **PASS (100%)** |
| 2 | `data_transferegov` | Ingestion Transferegov agreements & no PII | 5 | 5 | ✓ | S1 | **PASS (100%)** |
| 3 | `data_inep` | Ingestion INEP schools & CNEFE geocoding & TLS pinning | 5 | 5 | ✓ | S1, S2, S5 | **PASS (100%)** |
| 4 | `data_cnes` | Ingestion CNES health facilities & quarantine | 5 | 5 | ✓ | S1 | **PASS (100%)** |
| 5 | `provenance_sha256` | Cryptographic SHA-256 (64-char hex) & public URL | 5 | 5 | ✓ | S1, S2 | **PASS (100%)** |
| 6 | `slug_humanization` | Humanized provider labels; no raw technical slugs | 5 | 5 | ✓ | S1 | **PASS (100%)** |
| 7 | `no_nao_informado` | "Cadastro oficial" instead of "Não informado" | 5 | 5 | ✓ | S1 | **PASS (100%)** |
| 8 | `civic_logo_svg` | Responsive Brazilian civic vector logo (SVG) | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 9 | `favicon_vector` | Vector favicon SVG linked in index.html | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 10 | `header_layout` | Desktop alignment (1400px/1440px) & mobile height (<=90px) | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 11 | `map_sticky_fluid` | Map sticky on desktop, fluid on mobile | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 12 | `wcag_contrast` | Contrast compliance (>4.5:1 text, >3:1 UI) | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 13 | `touch_targets` | Minimum 44x44px interactive touch envelopes | 5 | 5 | ✓ | S4 | **PASS (100%)** |
| 14 | `i18n_parity` | Translation parity across pt-BR, en, and es | 5 | 5 | ✓ | S1, S4 | **PASS (100%)** |
| 15 | `citizen_sanitize` | Contribution input sanitization & 32KB body cap | 5 | 5 | ✓ | S2 | **PASS (100%)** |
| 16 | `csrf_and_origin` | CSRF header (X-BDT-Client: web) & multi-origin | 5 | 5 | ✓ | S2, S3 | **PASS (100%)** |
| 17 | `moderation_safety` | Unapproved observations stay private & anti-self-review | 5 | 5 | ✓ | S2, S3 | **PASS (100%)** |
| 18 | `no_runtime_llm` | Zero LLM / vector DB runtime dependency | 5 | 5 | ✓ | S5 | **PASS (100%)** |
| 19 | `docker_port_8008` | Docker Compose healthcheck on port 8008 | 5 | 5 | ✓ | S5 | **PASS (100%)** |

---

## Verification Results Summary

```
======================================================================
  Brasil de Todos — E2E Test Suite Execution
======================================================================
---> Running Tier 1 (95 tests discovered)... [95 PASS]
---> Running Tier 2 (95 tests discovered)... [95 PASS]
---> Running Tier 3 (19 tests discovered)... [19 PASS]
---> Running Tier 4 (5 tests discovered)...  [5 PASS]
======================================================================
  E2E Test Execution Summary
======================================================================
  Total Tests : 214
  Passed      : 214
  Skipped     : 0
  Failed      : 0
  Pass Rate   : 100.0%
  Duration    : 52.94s
======================================================================
```

---

## Escalation and Implementation Notes for Milestone Teams

1. **M1 (Official Data Ingestion & Provenance)**:
   - Ingested Obrasgov (700 records), Transferegov financial agreements, INEP schools (138k records with CNEFE geocoding), and CNES health facilities (96k records) are fully verified and live in `data/bdt.db`.
   - Ingestion records carry valid 64-char SHA-256 hashes and official source URLs.
   - When modifying `coverage_dashboard.py`, preserve the `'cnes'` and `'obrasgov'` source alias mappings tested in Tier 1 (`test_tier1_f06_*`).

2. **M2 (Visual Identity, Civic Brazilian Logo & Favicon)**:
   - `CivicLogo.tsx` should export `CivicLogo({ size = 36, className = '' })` returning responsive SVG containing colors `#12644e` (green), `#f2b705` (yellow), `#0b3b75` (blue), and `#ffffff` (white) with lozenge, sphere, and citizen arc.
   - Favicon must be placed at `web/public/favicon.svg` and linked via `<link rel="icon" type="image/svg+xml" href="/favicon.svg">` in `web/index.html`.

3. **M3 (Interface Fluidity, WCAG & i18n Parity)**:
   - Header max-width alignment and mobile height <= 90px are tested in Tier 1 F10 and Tier 4 S4.
   - Contrast for `.quiet-text` must maintain >= 4.5:1 against white, and active UI stars >= 3.0:1.
   - Touch targets for pills and controls must maintain >= 44x44px.
   - Ensure translation parity for keys `'map'`, `'retry'`, and `'officialRecord'` across `pt-BR`, `en`, and `es`.

4. **M4 (Security, CSRF, Moderation & Docker)**:
   - Mutation requests strictly enforce `X-BDT-Client: web` and trusted origins (`http://127.0.0.1:8008`, `http://localhost:8000`).
   - Anti-self-review gate forbids author from reviewing their own submission (HTTP 403 `self_review_forbidden`).
   - Request body cap of 32KB is enforced with HTTP 413 `request_too_large`.

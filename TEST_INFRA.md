# E2E Test Infra: Brasil de Todos

## Test Philosophy
- **Opaque-box, requirement-driven**: Tests derive strictly from `ORIGINAL_REQUEST.md` and user-facing requirements, not implementation internals.
- **Independence**: Exercises public entry points (HTTP API endpoints, frontend bundle, CLI tools) exactly as an end user or client would.
- **Progressive Testability**: Verification mechanisms do not require features more complex than what they test. Simple assertions (HTTP status, schema validation) over complex UI drivers for baseline features.
- **Robustness**: Includes negative tests verifying graceful rejection of invalid inputs (HTTP 4xx, error details, no 500 crashes).
- **Methodology**: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.

---

## Feature Coverage Matrix (Tiers 1 to 3)

| # | Feature Key | Requirement | Tier 1 (Min 5) | Tier 2 (Min 5) | Tier 3 (Pairwise) |
|---|-------------|-------------|:--------------:|:--------------:|:-----------------:|
| 1 | `data_obrasgov` | Ingestion Obrasgov projects & measurements | 5 | 5 | ✓ |
| 2 | `data_transferegov` | Ingestion Transferegov financial agreements | 5 | 5 | ✓ |
| 3 | `data_inep` | Ingestion INEP schools & TLS cert pinning | 5 | 5 | ✓ |
| 4 | `data_cnes` | Ingestion CNES health & quarantine | 5 | 5 | ✓ |
| 5 | `provenance_sha256` | Cryptographic SHA-256 & URL provenance | 5 | 5 | ✓ |
| 6 | `slug_humanization` | No raw slugs (cnes-national-bulk, etc.) | 5 | 5 | ✓ |
| 7 | `no_nao_informado` | "Cadastro oficial" instead of "Não informado" | 5 | 5 | ✓ |
| 8 | `civic_logo_svg` | Responsive Brazilian civic vector logo | 5 | 5 | ✓ |
| 9 | `favicon_vector` | Favicon SVG in index.html | 5 | 5 | ✓ |
| 10 | `header_layout` | Desktop alignment & mobile compactness (<=90px) | 5 | 5 | ✓ |
| 11 | `map_sticky_fluid` | Map sticky on desktop, fluid on mobile | 5 | 5 | ✓ |
| 12 | `wcag_contrast` | Contrast compliance (>4.5:1 text, >3:1 UI) | 5 | 5 | ✓ |
| 13 | `touch_targets` | Minimum 44x44px interactive touch envelopes | 5 | 5 | ✓ |
| 14 | `i18n_parity` | Complete translation parity (pt-BR, en, es) | 5 | 5 | ✓ |
| 15 | `citizen_sanitize` | Contribution input sanitization & body cap | 5 | 5 | ✓ |
| 16 | `csrf_and_origin` | CSRF header & multi-origin (127.0.0.1:8008) | 5 | 5 | ✓ |
| 17 | `moderation_safety`| Unapproved observations/links stay private | 5 | 5 | ✓ |
| 18 | `no_runtime_llm` | Zero LLM/vector DB runtime dependency | 5 | 5 | ✓ |
| 19 | `docker_port_8008` | Docker Compose healthcheck at :8008 | 5 | 5 | ✓ |

---

## Real-World Application Scenarios (Tier 4)

| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| S1 | Citizen navigates municipal health & education equipment in Boa Vista (RR), inspects provenance (SHA-256 + source URL), confirms "Cadastro oficial" label, and switches language between pt-BR, en, and es. | F01, F03, F04, F05, F06, F07, F14, F19, F20 | High |
| S2 | Citizen submits observation on public school with reference URL, verifies rate limit, checks that observation status is pending, and confirms it is not visible on public place endpoint. | F05, F22, F23, F24 | High |
| S3 | Reviewer logs in with credentials, reviews pending observation, verifies anti-self-review block, and approves observation; confirms observation is now public. | F23, F24 | Medium |
| S4 | Mobile user on 375px viewport navigates explore map and place cards, verifies header does not exceed 90px height, verifies touch buttons >=44px, and verifies skip links jump with proper scroll margins. | F10, F12, F14, F15, F16, F17, F18 | High |
| S5 | System operator queries live Docker Compose instance on `http://127.0.0.1:8008`, verifies `/api/health` returns `llm_required: False`, verifies Obrasgov resources, and verifies territory summaries. | F25, F26, F27, F29 | High |

---

## Test Architecture & Directory Layout
- Runner: `tests_e2e/runner.py`
  - Automated python executable executing end-to-end HTTP and frontend asset checks.
  - Generates TAP/JUnit XML and structured Markdown reports.
- Structure:
  - `tests_e2e/test_tier1_features.py`: Tier 1 Feature Coverage
  - `tests_e2e/test_tier2_boundaries.py`: Tier 2 Boundary & Negative Cases
  - `tests_e2e/test_tier3_interactions.py`: Tier 3 Cross-Feature Combinations
  - `tests_e2e/test_tier4_scenarios.py`: Tier 4 Real-World Workload Scenarios
  - `tests_e2e/test_tier5_adversarial.py`: Tier 5 Adversarial Hardening (Phase 2)

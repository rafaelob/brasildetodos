# Project: Brasil de Todos

## Architecture
Brasil de Todos is a full-stack civic transparency and public service platform designed for high performance, accessibility, and cryptographic provenance without mandatory runtime LLMs, vector databases, or paid mapping keys.

- **Backend**: Python 3.14.7, FastAPI 0.128.2, SQLAlchemy 2.0.50, Pydantic v2 (2.13.4). Dual SQLite (WAL mode, foreign keys) and PostgreSQL support.
- **Frontend**: React 19.2.0, TypeScript 5.9.3, Vite 8.2.2, MapLibre GL 6.7.0 (OpenFreeMap liberty tiles).
- **Security & Provenance**: Strict Pydantic models (`StrictModel`), SHA-256 cryptographic hashes on all ingested records, Scrypt password hashing, session tokens hashed with SHA-256 at rest, `X-BDT-Client: web` CSRF protection, `SameSite=Strict` cookies, anti-self-review moderation gates.
- **Operations**: Docker Compose containerized deployment exposing service on `http://127.0.0.1:8008`.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Official Ingestion: Obrasgov.br | Pipelines for investment projects, geometry pins, and physical execution measurements | M1 | ORIGINAL_REQUEST §R1 |
| F02 | Official Ingestion: Transferegov.br | Pipelines for federal agreements, amendments, and disbursements excluding PII/banking data | M1 | ORIGINAL_REQUEST §R1 |
| F03 | Official Ingestion: INEP Censo Escolar | Pipelines for educational microdata with intermediate TLS cert pinning and IBGE CNEFE school geolocation | M1 | ORIGINAL_REQUEST §R1 |
| F04 | Official Ingestion: CNES Health Establishments | Ingestion of SUS ambulatory facilities with quarantine defect isolation | M1 | ORIGINAL_REQUEST §R1 |
| F05 | Cryptographic Provenance Integrity | Strict validation of URL, SHA-256 snapshot digest, reference date, and timezone-aware collection date | M1 | ORIGINAL_REQUEST §R1 |
| F06 | Elimination of Technical Slugs & Slugs Humanization | Replace raw slugs (`cnes-national-bulk`) with humanized provider labels | M1 | ORIGINAL_REQUEST §R1 |
| F07 | Elimination of "Não informado" in Official Data | Replace unassigned or missing official dates with "Cadastro oficial" across all data presentations | M1 | ORIGINAL_REQUEST §R1 |
| F08 | Coverage Dashboard Alias Alignment | Align Transferegov and Obrasgov dataset aliases so records do not fall into 'other' | M1 | Survey Report (explorer-1) |
| F09 | Backend Test Suite Stability | Maintain 100% passing tests in pytest suite (1,130+ tests) | M1 | ORIGINAL_REQUEST Acceptance |
| F10 | Native Responsive SVG Civic Logo | Scalable SVG logo integrating Brazilian colors (green, yellow, blue), rhombus, sphere, and citizen arc | M2 | ORIGINAL_REQUEST §R2 |
| F11 | Vector Favicon Integration | Vector SVG favicon linked in index.html for browser tabs and bookmarks | M2 | ORIGINAL_REQUEST §R2 |
| F12 | Header Branding Integration | Integration of civic logo in desktop (1440px+) and mobile (375px-430px) headers | M2 | ORIGINAL_REQUEST §R2 |
| F13 | Desktop Header Alignment & Sizing | Alignment of sticky header with page max-width (1440px) eliminating horizontal stretching | M3 | Survey Report (explorer-2) |
| F14 | Mobile Header Compactness & Layout | Eliminate 3-row stacked header on mobile (<=480px) to keep sticky height <= 90px | M3 | ORIGINAL_REQUEST §R3 |
| F15 | Map Panel Sticky vs Relative Harmonization | Reconcile conflicting CSS rules so desktop map is sticky and mobile map is ordered properly | M3 | ORIGINAL_REQUEST §R3 |
| F16 | Target Anchor Scroll Margins | Add scroll-margin-top to skip links, place cards, and map so content is never obscured by sticky header | M3 | ORIGINAL_REQUEST §R3 |
| F17 | WCAG AA Contrast Compliance | Declare --bg and --text in :root, darken quiet-text (#486357, >5:1) and active stars (#b56a00, >3.5:1) | M3 | ORIGINAL_REQUEST §R3 |
| F18 | Mobile Touch Target Sizing | Ensure all interactive buttons (map tilt, city pills, copy pills, save icons) meet 44x44px minimum | M3 | ORIGINAL_REQUEST §R3 |
| F19 | Missing i18n Translation Keys Fix | Add missing keys ('map' in i18n.mjs, 'retry' in region-text.mjs) across pt-BR, en, and es | M3 | Survey Report (explorer-2) |
| F20 | Reference Date Sanitization Helper | Sanitize formatReferenceDate to translate "Não informado" to "Cadastro oficial" across all locales | M3 | ORIGINAL_REQUEST §R1, §R3 |
| F21 | Frontend Test Suite & Build Verification | Ensure npm test (192+ tests) and npm run build succeed with 100% pass | M3 | ORIGINAL_REQUEST Acceptance |
| F22 | Citizen Contribution Validation & Sanitization | Strict Pydantic models, 32KB request limit, past/present date validation, 20 req/15min rate limiting | M4 | ORIGINAL_REQUEST §R4 |
| F23 | CSRF & Authentication Protection | Custom X-BDT-Client header, SameSite=Strict cookies, Scrypt password hashing, token hashing | M4 | ORIGINAL_REQUEST §R4 |
| F24 | Moderation & Extraction Safety Gates | Document extractions private to reviewers, anti-self-review gates, dual approval for photos | M4 | ORIGINAL_REQUEST §R4 |
| F25 | Zero Runtime LLM & Vector DB Enforcement | Enforce platform rule of zero LLM/vector DB dependencies, llm_required: False | M4 | ORIGINAL_REQUEST §R4 |
| F26 | Multi-Origin Support for Port 8008 | Normalize localhost and 127.0.0.1 on configured port to prevent 403 origin_not_allowed | M4 | Survey Report (explorer-3) |
| F27 | Docker Compose Port 8008 & Healthcheck | Configure compose.yaml default to 8008, add explicit healthcheck, provide docker-compose.yml | M4 | ORIGINAL_REQUEST Acceptance |
| F28 | Integrated E2E Test Suite (Tiers 1-4) | Comprehensive opaque-box E2E test suite covering features, boundaries, interactions, and scenarios | M5 | Project Pattern Track |
| F29 | Live Docker Compose Verification at Port 8008 | Verification of running container on http://127.0.0.1:8008 via ops/verify_live_port_8008.py | M5 | ORIGINAL_REQUEST Acceptance |
| F30 | Adversarial Coverage Hardening (Tier 5) | White-box adversarial testing by Challenger agent to harden edge cases | M5 | Project Pattern Final |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Official Data Ingestion & Provenance Hardening | Features F01, F02, F03, F04, F05, F06, F07, F08, F09 | none | DONE |
| M2 | Visual Identity, Civic Brazilian Logo & Favicon | Features F10, F11, F12 | none | DONE |
| M3 | Interface Fluidity, Usability, WCAG & i18n Parity | Features F13, F14, F15, F16, F17, F18, F19, F20, F21 | M2 | DONE |
| M4 | Security, Moderation, Origin Matching & Docker Config | Features F22, F23, F24, F25, F26, F27 | M1 | DONE |
| M5 | Integrated Verification, E2E Tests & Adversarial Hardening | Features F28, F29, F30 | M1, M2, M3, M4 | PLANNED |

---

## Interface Contracts

### Ingestion & Provenance ↔ Storage (`bdt.domain.Source` ↔ `bdt.storage.Place/Resource`)
- `Source`:
  ```python
  class Source(StrictModel):
      dataset: str = Field(min_length=2, max_length=100)
      url: str = Field(max_length=2000)
      record_id: str = Field(min_length=1, max_length=180)
      reference_date: str | None = Field(default=None, max_length=80)
      collected_at: str  # ISO with timezone
      snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
  ```
- Validation rule: When `reference_date` is omitted or empty, backend stores `None`, and frontend renders localized `officialRecord` ("Cadastro oficial").

### Backend API ↔ Frontend Client (`/api` ↔ `web/src/api.ts`)
- All mutation requests (`POST`, `PUT`, `DELETE`, `PATCH`) must transmit:
  - Header: `X-BDT-Client: web`
  - Header: `Origin: <origin>` where origin is normalized to `http://127.0.0.1:<port>` or `http://localhost:<port>`.
  - Cookie: `bdt_session=<token>` (`SameSite=Strict`, `HttpOnly=True`).

### Frontend Component Contracts
- `CivicLogo`:
  - Signature: `({ size = 36, className = '' }: { size?: number; className?: string }) => JSX.Element`
  - Colors: `#12644e` (Brazilian civic green), `#f2b705` (warm yellow lozenge), `#0b3b75` (navy celestial sphere), `#ffffff` (citizen arc).
- `formatReferenceDate`:
  - Signature: `(ref: string | null | undefined, locale?: string) => string`
  - Invariant: If `!ref` or `ref === 'Não informado'` or `ref.trim() === ''`, returns `translate(locale, 'officialRecord')`. Otherwise returns `${translate(locale, 'refPrefix')} ${ref}`.

---

## Code Layout
- `backend/bdt/`:
  - `api.py`: FastAPI routes, origin validation, CSRF checks, security headers.
  - `storage.py`: SQLAlchemy models (`Place`, `Source`, `Change`, `User`, `Observation`).
  - `domain.py`: Pydantic contracts (`Source`, `ObservationInput`, `MoneyEvent`).
  - `coverage_dashboard.py`: Ingestion dashboard and publisher family mapping.
  - `obrasgov_batch.py`: Obrasgov.br data fetcher & parser.
  - `transferegov_finance.py`: Transferegov.br financial parser.
  - `education_bulk.py`, `education_tls.py`, `school_geocoder.py`: INEP parser, TLS cert pinning, and CNEFE geocoding.
  - `cnes_bulk.py`, `cnes_quality.py`: CNES health establishment ingestion & quarantine.
- `web/src/`:
  - `CivicLogo.tsx`: Responsive vector SVG logo component.
  - `main.tsx`: App root, header navigation, brand logo integration.
  - `Map.tsx`: MapLibre 2D/3D map panel.
  - `style.css`: Core layout, CSS variables, typography, header styling, WCAG contrast colors.
  - `map.css`: Map layout, controls, sticky behavior.
  - `workbench.css`: Document workbench styles (scoped mobile rules).
  - `i18n.mjs`, `ui-text.mjs`, `region-text.mjs`, etc.: Localization dictionaries.
- `web/public/`:
  - `favicon.svg`: Vector SVG favicon.
- `ops/`:
  - `verify_live_port_8008.py`: Live integration test script for Docker container.
- `compose.yaml` / `docker-compose.yml`:
  - Docker Compose service configuration.

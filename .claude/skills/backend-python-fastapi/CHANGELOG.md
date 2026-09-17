# Changelog: backend-python-fastapi

All notable changes to this skill are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.12] - 2026-09-05
### Fixed
- Corrected Python JIT activation and free-threaded build requirements against official documentation; clarified that template strings require safe context-specific processing and that FastAPI support does not certify the whole runtime stack.
- Replaced generic routing with Django and PostgreSQL migration boundaries, and scoped uv examples to the target project's declared manager.

## [1.0.11] - 2026-09-05
### Changed
- Added conditional root routing and removed redundant first-level pairing prompts from the activation description; detailed material remains available through workflow-selected references.

## [1.0.10] - 2026-08-10
### Fixed
- Updated the live FastAPI version fact from `0.140.9` to `0.141.1`, verified against the official FastAPI release-notes page (which dates `0.141.1` to 2026-07-29). No framework guidance or API contract changed.

## [1.0.9] - 2026-08-06
### Changed
- Removed two residual bare-date fragments the prior pass's `## Freshness` -> `## Dependency
  Currency` rename left behind (bare-date sweep, per `AGENTS.md` §"O que vai dentro de um
  SKILL.md"): the `<!-- FRESHNESS: ... Last structured: 2026-04-21 -->` HTML comment under
  `## Official documentation` lost only the trailing date (the "Always verify against official
  docs. Links may change." instruction stays -- it changes agent behavior, the date did not); and
  the standalone `Last verified 2026-07-28.` paragraph that opened `## Dependency Currency` was
  removed outright (every fact below it already carries its own inline verification date, e.g.
  "latest 3.14.6 as of 2026-06-10").

## [1.0.8] - 2026-08-06
### Changed
- Moved provenance out of `SKILL.md`'s body (provenance-out-of-body pass, per `AGENTS.md`
  §"O que vai dentro de um SKILL.md"). Renamed `## Freshness` to `## Dependency Currency` and
  kept only the current version pins there (dates attached to live facts, not a diary). The
  correction narrative and the re-sweep audit trail are archived below:
  - **Corrected 2026-07-28** (second pass, after the re-sweep below): the Python 3.13 bugfix
    window was overstated. Per the official devguide, a release gets ~2 years of full bugfix
    support after its `X.Y.0` date, then moves to security-only until EOL. Python 3.13.0
    released 2024-10-07, so bugfix support runs out around 2026-10, not through the 2029-10
    EOL as previously stated -- 2026-2029 is security-only. Did not change the "use 3.13 as
    repo default" recommendation; 3.13 stays fully supported either way.
  - Audited 2026-04-21; re-swept 2026-07-28.
  - **Re-swept 2026-07-28**, checked against the official FastAPI release-notes page and PyPI
    JSON (`fastapi`, `pydantic`, `uv`), the pydantic.dev changelog, the SQLAlchemy blog/
    changelog, python.org's downloads page, and the FastAPI GitHub release for tag `0.136.0`:
    FastAPI moved from 0.139.0 (2026-07-09) to 0.140.9 (2026-07-28), confirmed via PyPI JSON.
    Verified true, previously unconfirmed: "FastAPI 0.136+ adds official support for
    free-threaded Python 3.14t" -- GitHub's `0.136.0` release notes (2026-04-16) read exactly
    that (PR #15149 by @svlandeg). Verified true: PEP 779 accepted for Python 3.14, matching
    the existing body claim. Added exact current versions where the file only said "the
    current major line" (Pydantic 2.13.4, SQLAlchemy 2.0.51, uv 0.11.33) -- informational, not
    a guidance change. Left unchanged: re-read `references/FASTAPI_PROJECT_PATTERNS.md` end to
    end, no version-specific claims to rot, framework-comparison table still accurate.
    UNVERIFIED that pass: exact current Alembic, httpx, pytest-asyncio, testcontainers-python
    versions (none are version-pinned in this skill).

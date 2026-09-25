# Changelog: document-parsing-resilience

All notable changes to this skill are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.3] - 2026-09-25
### Changed
- Description rewritten trigger-first: it opens with "Use when" and the phrases a user or agent actually types, in Portuguese and English, before what the skill does and its sibling routes. Evidence: docia-platform traces showed 0 loads of this skill despite parsing work (14-day window). Previous description, kept for comparison: "Recover text from malformed PDF, DOCX or HTML: parser/OCR route and expected-vs-extracted coverage. Use when a parser returns empty or partial text, a corpus mixes scanned pages or broken encodings, or a truncated/encrypted upload needs an honest per-part ledger instead of a silent empty string. PDF editing -> pdf. Upload security -> file-ingestion-security-gates."

## [1.0.2] - 2026-08-06
### Changed
- Moved provenance out of the `## Freshness` body section (per `AGENTS.md` §"O que vai dentro de um SKILL.md"), renaming it `## Sources and re-verification` since it also carried the primary-source URL list backing the dated "(verified 2026-07-29)" claims spread through Steps 1, 3, 5 and 6 — that list stayed, since removing it would leave "re-verify before quoting" with nothing to re-verify against. Backfilled here:
  - **2026-07-29** — skill created.
  - **2026-07-29 — sourcing-contract cuts**: left out a `repair=` parameter for pdfplumber (its README documents none); any claim about which exception pypdf raises when an encrypted file is read without decrypting (its encryption docs state only the `is_encrypted` / `decrypt()` pattern and the supported algorithm list); and every universal numeric threshold for scanned-page detection, text density or OCR confidence — no primary source establishes one, so the skill teaches calibration instead (Step 5 already carries the "do not hardcode a threshold" instruction).

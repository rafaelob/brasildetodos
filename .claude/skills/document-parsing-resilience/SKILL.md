---
name: document-parsing-resilience
description: >-
  Recover text from malformed PDF, DOCX or HTML: parser/OCR route and
  expected-vs-extracted coverage. Use when a parser returns empty or partial
  text, a corpus mixes scanned pages or broken encodings, or a
  truncated/encrypted upload needs an honest per-part ledger instead of a
  silent empty string. PDF editing -> pdf. Upload security ->
  file-ingestion-security-gates.
license: Apache-2.0
compatibility: Language-agnostic design. Measured examples use Python 3.13 stdlib (codecs, unicodedata,
  zipfile); parser notes cite pypdf, pdfplumber, PyMuPDF and python-docx official docs.
metadata:
  author: coding-agent
  version: 1.0.2
  category: data-analysis
  subcategory: dataset-analysis
  vendor: universal
  lifecycle: active
  coding_agent: true
  user_level: false
  project_level: true
  audience: developer
  output_format: markdown
  modality: text
  freshness: 2026-07
  short-description: Parser fallback chains with per-page provenance, honest partial extraction, and encoding
    repair for messy document pipelines
  tags:
  - document-parsing
  - text-extraction
  - pdf
  - docx
  - ocr-routing
  - provenance
  - partial-extraction
  - page-ledger
  - encoding
  - mojibake
  - cp1252
  - unicode-normalization
  - quarantine
  - reparse
  - malformed-input
  - ingestion-pipeline
  - last_verified:2026-07-29
---

# Document Parsing Resilience

> An extractor that returns `""` for a page is making one of six different claims: the page is
> blank, the page is a photograph, the parser crashed, the file is truncated, the file is
> encrypted, or the bytes were never a document of that type. A pipeline that stores all six as
> the same empty string has destroyed the only information anyone needed to fix it.

## Scope

Parsing **legitimate but ugly** documents inside a pipeline: mixed PDF/DOCX/HTML corpora, scanned
pages, broken encodings, truncated uploads. The unit of work is a *document with parts*, and the
deliverable is a per-part ledger, not a string.

| Request | Owner |
|---|---|
| The general rule that "found nothing" and "could not look" are different facts | `zero-vs-unknown-semantics` |
| Screening hostile or untrusted uploads before they reach a parser | `file-ingestion-security-gates` |
| Editing, assembling, splitting or stamping a PDF as an artifact | `pdf` |
| Accuracy/completeness gates over an assembled dataset | `data-quality` |
| Format conversion of structured tabular data (CSV, Parquet, XML) | `data-file-transformation` |
| Retry, backoff and dead-letter topology of the worker itself | `background-jobs-queues` |
| Downstream chunking and retrieval of the extracted text | `rag-systems` |

## Workflow

Eight steps, in order. Steps 1–2 are design decisions that constrain everything after them, so do
not skip ahead to writing extraction code: **sniff the container → name the outcome states → build
the chain with provenance → account for expected versus extracted parts → route scanned pages →
repair encoding once → quarantine and reparse → publish quality signals.**

## Step 1 — Identify the container before choosing a parser

The extension is a label a human typed; the bytes are the fact. Sniff the container, then dispatch.

Three genuinely different states collapse into one message when you let the parser answer for you.
Measured with the Python 3.13.12 stdlib `zipfile` [observed]: a **truncated** OOXML file, a legacy
OLE2 `.doc` renamed `.docx`, and a PDF renamed `.docx` all raise the identical
`BadZipFile: File is not a zip file`. The exception cannot distinguish them — only a magic-byte
check before the parse can. Two further measurements from the same run:

- A valid ZIP with no `word/document.xml` opens cleanly and `namelist()` succeeds. It is not
  corrupt; it is *not a Word document*. Distinct state, distinct handling.
- Flipping one byte inside member data still opens, and `namelist()` still succeeds. Only the CRC
  check (`ZipFile.testzip()`) reports the damage. **Opened is not intact**, and the integrity check
  is a separate step most pipelines skip.

Completion criterion: every document leaves Step 1 with a `detected_container` recorded from the
bytes, plus a mismatch flag when it disagrees with the extension. Never overwrite the claimed
extension — the disagreement is evidence about the source system.

## Step 2 — Name the outcome states before writing any parser code

Fix the vocabulary first. Each state is terminal, mutually exclusive, and drives a different action.

| State | Means | Pipeline action |
|---|---|---|
| `extracted` | All expected parts produced text | Continue |
| `extracted_partial` | Some parts produced text, some failed | Continue **and** alert; keep the ledger |
| `empty_by_content` | Parsed fine, genuinely has no text | Continue; never retry |
| `needs_ocr` | Parsed fine, text layer absent by design | Route to OCR (Step 5) |
| `encrypted` | Password or permissions block extraction | Quarantine; needs a credential, not a retry |
| `malformed` | Truncated, CRC-bad, or structurally invalid | Quarantine; needs a new upload |
| `wrong_type` | Valid file of a type this route does not parse | Re-dispatch, do not fail |
| `parser_error` | Engine crashed or timed out on a valid file | Retry, then escalate |

`empty_by_content` and `needs_ocr` are the pair everything hinges on: both look like an empty
string and they demand opposite responses. Read
`references/outcome-states-and-page-ledger.md` before designing the schema — it carries the full
state table with transitions, the provenance fields, and the append-only attempt-ledger SQL.

## Step 3 — Fallback chains that record who produced what

A chain without provenance is unauditable: when a page comes out wrong you cannot tell which engine
to blame, and after upgrading an engine you cannot tell which documents deserve a reparse.

Ordering rule: **cheapest deterministic engine first, OCR last, and never let a later engine
silently overwrite an earlier result.** Promotion between engines happens only under a rule you
wrote down (for example "prefer the candidate with more extracted characters, tie broken by chain
order"), and the losing candidate's score stays in the ledger.

Record per part, not per document: `part_index`, `parser`, `parser_version`, `method`
(`text_layer` | `ocr`), `chars`, `status`, and the promotion rule that selected it. `parser_version`
is what makes a future reparse decidable instead of a guess.

Two constraints that belong in the chain design, not discovered later:

- **PyMuPDF's licence is a chain decision.** Its own docs state: "PyMuPDF and MuPDF are now
  available under both, open-source AGPL and commercial license agreements" (verified 2026-07-29).
  Putting an AGPL engine in a served pipeline is a legal decision, so make it deliberately.
- **pypdf's forgiving mode reports damage only through a log line.** Its docs: `strict=False`
  "means that pypdf will try to be forgiving and do something reasonable, but it will log a warning
  message" (verified 2026-07-29). If the pipeline suppresses parser logs, non-strict mode makes
  malformed documents indistinguishable from clean ones. Capture the warnings into the ledger.

Consult `references/parser-chains-and-scanned-routing.md` when composing the chain: per-engine
verified capability notes, chain recipes per container, and the promotion-rule patterns.

## Step 4 — Expected versus extracted: partial extraction that tells the truth

**A page failure is not a document failure, and a document failure is not a page failure.** Both
directions of that confusion lose data.

1. Read the expected part count from the container *before* extracting (PDF page count, DOCX body
   parts, HTML sections). This number is the denominator; without it, "we extracted 40 pages" is
   unfalsifiable.
2. Extract part by part, writing one ledger row per part — including the failures, with their state
   from Step 2.
3. Derive the document status from the ledger — plus a **disposition** (`done` | `retry` | `route` |
   `blocked` | `incomplete`) saying what the pipeline may still do. Never assert either. `extracted`
   requires `extracted_count == expected_count`; a mixture is `extracted_partial` with the missing
   indices listed. **A uniform failure keeps its own name:** twelve crashed pages derive
   `parser_error`/`retry` and a mis-routed file derives `wrong_type`/`route` — never
   `extracted_partial`, which claims text exists and hides the failure behind a coverage number.
   Parts with no ledger row at all are `incomplete`, not a result.
4. Compute `coverage = extracted_count / expected_count` and carry it forward as data, not as a log
   line, so downstream consumers can filter on it.

The forbidden pattern is `try: ... except Exception: continue`. It converts a lost page into a
shorter document, and nothing downstream can ever detect the loss. If a part fails, the row is
written with the failure state; the loop continues, the *evidence* does not vanish.

Completion criterion: for every ingested document, `expected_count`, `extracted_count` and the list
of failed part indices are all queryable. If any of the three is missing, this step is not done.

## Step 5 — Scanned and image-only PDFs: an explicit route, never a silent fallback

Text-layer extractors do not fail on a scanned page — they succeed and return almost nothing. Two
primary sources, verified 2026-07-29:

- pypdf: "pypdf is **not** OCR software"; it "will also never be able to extract text from images",
  and for image-based pages "the extracted text may be minimal or visually empty".
- pdfplumber: "Works best on machine-generated, rather than scanned, PDFs", and lists "Optical
  character recognition (OCR)" among the things it does not provide.

So the pipeline must *decide*. OCR costs money and latency and produces lower-fidelity text with
different failure modes — it is a routing decision that must be recorded (`method=ocr`, engine,
engine version), never an invisible retry inside a fallback chain.

Detection signals, combined rather than used alone: extracted characters per page, the share of
pages at or near zero characters, and whether the page carries a full-page image object. **Do not
hardcode a character threshold.** Any number here is corpus-specific; the calibration procedure
(label a sample, sweep the threshold, pick the operating point, re-check per corpus) is in
`references/parser-chains-and-scanned-routing.md` — read it before choosing a cutoff, and record
the chosen value with its calibration date.

## Step 6 — Encoding: repair once, at one boundary

Store the raw bytes plus their hash. Text is a *derived* view, so a decoding mistake is repairable
instead of permanent. Measured with Python 3.13.12 [observed]:

| Measurement | Result | Consequence |
|---|---|---|
| `latin-1` decoding all 256 byte values | Succeeds, 256 chars | A chain ending in `latin-1` **can never report an encoding failure** — it always "works" |
| `cp1252` decoding all 256 byte values | Raises on `0x81 0x8D 0x8F 0x90 0x9D` | cp1252 failures are *detectable*; prefer it over latin-1 as the legacy attempt |
| `utf-8` with `errors="ignore"` on those bytes | 128 of 256 silently dropped | Never use `ignore` on ingest — it is silent data loss |
| `utf-8` with `errors="replace"` | 128 × U+FFFD | Damage becomes countable; U+FFFD rate is a usable quality signal |

Python's own docs confirm the semantics: `replace` on decoding uses "U+FFFD, the official
REPLACEMENT CHARACTER", `ignore` means "malformed data is ignored ... without further notice", and
`surrogateescape` maps a byte to `U+DC80`–`U+DCFF` and turns it "back into the same byte" on
encoding — the one lossless way to carry undecodable bytes through (verified 2026-07-29).

Two facts from the WHATWG Encoding Standard (verified 2026-07-29) that decide the HTML/XML path:
the labels `iso-8859-1`, `latin1`, `ascii` and `us-ascii` all map to **windows-1252**, so a document
declaring `iso-8859-1` should be decoded as cp1252; and "the byte order mark is more authoritative
than anything else", so a BOM overrides any declared charset.

Normalize to **NFC once**, at the ingest boundary, and record that you did. Three UAX #15 facts
(verified 2026-07-29): normalization is idempotent (`toNFC(toNFC(x)) = toNFC(x)`), "none of the
Normalization Forms are closed under string concatenation" — so stitching per-page text from
different engines requires normalizing the *joined* result, not only each page — and NFKC/NFKD
"must not be blindly applied to arbitrary text" because they do not maintain compatibility
composites (measured: NFKC turns `ﬁ` into `fi` and `m²` into `m2`, silently changing meaning).

Read `references/encoding-repair-and-normalization.md` before writing the decode path: the ordered
decode ladder, the mojibake detection and repair procedure with its safety guard, and the
declared-versus-actual charset rules for HTML, XML and CSV.

## Step 7 — Quarantine, retry, and reparse

Quarantine is a state with a record, not a folder where files go to die. Each entry keeps the
content hash, the detected container, the outcome state, the failing engine and version, and the
first/last seen timestamps. This is the *parse-outcome* quarantine; the admission-time gate that
holds files for scanning belongs to `file-ingestion-security-gates`, and a document can pass through
both for different reasons.

- **Classify before retrying.** `parser_error` and timeouts are transient — retry. `malformed`,
  `encrypted` and `wrong_type` are not: retrying is pure cost, and a retry counter climbing on a
  truncated file is a monitoring lie.
- **Idempotency is by content hash, not filename.** The same bytes resubmitted must update the
  existing record, not create a second document. Different bytes under the same name are a new
  document.
- **Reparse is triggered by a parser upgrade.** Because `parser_version` is in the ledger, "reparse
  every document whose text came from engine X below version N" is a query. Without provenance it
  is a full-corpus rerun, which is why pipelines never do it.
- **Requeue keeps the prior attempt, and the schema has to allow that.** One row per *attempt*
  (`attempt_id`, `attempt_no`, `attempt_reason`) in an append-only ledger, plus a separate pointer
  table naming the current attempt per part. A part table keyed `(document_id, part_index)` leaves a
  retry nowhere to go but `UPSERT`, so the pipeline overwrites the very evidence that proves the
  upgrade helped — and a crashing second attempt silently replaces a good first one.

## Step 8 — Quality signals, labelled as heuristics

Publish four numbers per batch, and say in the metric name that they are heuristics: `coverage`
(Step 4), `ocr_share`, `replacement_char_rate` (U+FFFD per 1000 chars), and `chars_per_page`.

Text density is the useful and the most abused one: low density suggests a scanned page, a
CJK-heavy page, a form, or a cover sheet — it is a *sanity heuristic*, never a verdict. Wire these
to alerts and quarantine, never to a silent discard: a pipeline that drops low-density pages will
happily delete every legitimately sparse document in the corpus.

## Gotchas

| Gotcha | Reality |
|---|---|
| `except Exception: continue` inside the page loop | The document silently shortens; the loss is undetectable forever |
| latin-1 as the last-resort decoder | Never raises on any byte [observed] — guarantees a successful-looking wrong answer |
| `errors="ignore"` to "clean" bad bytes | Dropped 128 of 256 bytes with no signal [observed] |
| Trusting the parser's exception to name the failure | Truncated file, legacy `.doc`, and a mislabelled PDF give the *same* `BadZipFile` message [observed] |
| Treating `ZipFile` opening successfully as "file is fine" | A flipped byte still opens; only `testzip()` catches it [observed] |
| OCR wired in as an automatic fallback | Cost and latency spike invisibly, and provenance no longer says which text is OCR |
| Suppressing parser logs with pypdf `strict=False` | The warning is the only malformed-file signal in forgiving mode |
| Normalizing each page then concatenating | Not closed under concatenation (UAX #15) — the joined string may be un-normalized |
| NFKC "to clean up" extracted text | Destroys ligatures and superscripts (`ﬁ`→`fi`, `m²`→`m2`) |
| A hardcoded chars-per-page threshold for "scanned" | Corpus-specific; calibrate and date it, or it silently misroutes |
| Retry counters on `malformed`/`encrypted` | Burns budget and hides the real state behind transient-looking noise |
| Quarantine keyed by filename | Resubmission duplicates the document; the same bytes must converge |
| One part row keyed `(document_id, part_index)` | The retry can only `UPSERT`, so the failed attempt and its engine version are erased |
| Every-part-failed derived as `extracted_partial` | A document with no text at all reads as a partial success and never gets retried |

## Validation

- [ ] Every document has a recorded `detected_container` from the bytes, plus an extension-mismatch flag.
- [ ] Every outcome maps to exactly one Step 2 state; no code path returns a bare empty string.
- [ ] `empty_by_content` and `needs_ocr` are distinguishable in storage.
- [ ] `expected_count`, `extracted_count`, failed part indices and `coverage` are all queryable.
- [ ] A retry appends an attempt row and never overwrites one; a test asserts both attempts survive.
- [ ] A uniform `parser_error` or `wrong_type` derives that state with its own disposition, not
      `extracted_partial`; a part with no attempt row derives `incomplete`.
- [ ] No `except: continue` in any part loop — grep the extraction module and confirm.
- [ ] Every extracted part records `parser`, `parser_version` and `method`.
- [ ] OCR is entered by an explicit decision that lands in provenance, with the routing threshold and its calibration date stored.
- [ ] The decode path never uses `errors="ignore"`; latin-1 is absent or is explicitly the last rung with a recorded warning.
- [ ] NFC applied once at the boundary, to the joined text; raw bytes and hash retained.
- [ ] Quarantine records are keyed by content hash and classified transient vs permanent.
- [ ] A parser-version bump can be turned into a reparse query without a full-corpus rerun.

## Reference files

- Read `references/outcome-states-and-page-ledger.md` when designing storage: the full state table
  with transitions, the provenance fields, the append-only attempt-ledger SQL, the status-plus-
  disposition derivation, and the no-overwrite tests.
- Consult `references/parser-chains-and-scanned-routing.md` before composing a chain or choosing an
  OCR cutoff: per-engine verified capability notes, chain recipes, promotion rules, scanned-page
  detection signals, and the threshold calibration procedure.
- Read `references/encoding-repair-and-normalization.md` before writing the decode path: the decode
  ladder, mojibake repair with its guard, the declared-versus-actual charset rules for HTML/XML/CSV,
  and the normalization policy.

## Cross-references

`zero-vs-unknown-semantics` (the general absence-vs-unreadable rule this specialises),
`file-ingestion-security-gates` (screening before the parser), `pdf` (PDF as an artifact),
`data-quality` (gates over the assembled dataset), `data-file-transformation` (structured tabular
formats), `background-jobs-queues` (worker retry topology), `rag-systems` (chunking the output),
`corpus-lineage-provenance` (lineage across the whole corpus).

## Sources and re-verification

Library behaviour throughout this skill is given as *documented capability statements* rather than
pinned version numbers, because the capability boundaries (no OCR, forgiving-mode warnings, licence
terms) are what the design depends on and they are stable across minor releases. Re-verify the
capability claims above before quoting them.

Verified against primary sources 2026-07-29: `pypdf.readthedocs.io/en/stable/user/extract-text.html`
(not OCR software; never extracts text from images; may return visually empty text) and
`.../user/robustness.html` (`strict` trade-off and the warning-only signal);
`github.com/jsvine/pdfplumber` README (built on `pdfminer.six`; machine-generated over scanned; no
OCR); `pymupdf.readthedocs.io/en/latest/about.html` (dual AGPL/commercial licensing);
`python-docx.readthedocs.io` API docs (`paragraphs`/`tables` in document order; top-level tables
only, nested ones absent; revision-marked content excluded);
`encoding.spec.whatwg.org` (iso-8859-1/latin1/ascii labels map to windows-1252; BOM more
authoritative than any label); `docs.python.org/3/library/codecs.html` (error-handler semantics,
U+FFFD, surrogateescape); `unicode.org/reports/tr15/` (NFC idempotence, concatenation not closed,
NFKC compatibility loss). Measurements marked [observed] were run locally on Python 3.13.12 the
same day.

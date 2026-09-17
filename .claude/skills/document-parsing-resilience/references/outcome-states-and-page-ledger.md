# Outcome States and the Page Ledger

The storage design that makes partial extraction honest. Read this before creating tables or
defining the extraction return type.

## 1. The state machine

Eight terminal states. They are mutually exclusive at the *part* level and derived at the *document*
level. Nothing in the pipeline may return a bare empty string, a bare `null`, or a bare boolean.

At the document level the same eight names are joined by the non-terminal `parsing` (the run has not
finished) and by a second derived field, the **disposition** — see section 4. The status alone cannot
say whether a retry is allowed to move, which is why deriving only a status is what puts
`parser_error` and `wrong_type` in the same lane as a partial success.

| State | Detected by | Retryable | Downstream may use text? |
|---|---|---|---|
| `extracted` | Text produced for every expected part | n/a | Yes |
| `extracted_partial` | Some parts have text, some carry a failure state | Per failed part | Yes, with `coverage` attached |
| `empty_by_content` | Parse succeeded, container reports zero text objects | No | Yes (the emptiness is the answer) |
| `needs_ocr` | Parse succeeded, text layer absent or negligible | Not a retry — a route | Only after OCR |
| `encrypted` | Container reports encryption before extraction | No (needs a credential) | No |
| `malformed` | Structural check fails: truncated, CRC mismatch, unparseable | No (needs a new upload) | No |
| `wrong_type` | Container magic disagrees with the route's expected type | No (needs re-dispatch) | No |
| `parser_error` | Engine raised or timed out on a structurally valid file | Yes, bounded | No |

### Transitions

```text
sniffed ──> encrypted        (terminal until a credential arrives)
        ├─> malformed        (terminal until new bytes arrive)
        ├─> wrong_type ────> re-dispatch to the correct route (NOT a failure)
        └─> parsing
              ├─> extracted
              ├─> extracted_partial   (per-part states retained)
              ├─> empty_by_content
              ├─> needs_ocr ────> ocr_attempted ──> extracted | extracted_partial | parser_error
              └─> parser_error ──> retry (bounded) ──> quarantine
```

Two rules that keep the machine honest:

1. **`wrong_type` is not a failure.** A DOCX arriving on the PDF route is a dispatch bug, and
   recording it as `malformed` teaches the operator the wrong lesson and pollutes the malformed rate.
2. **`needs_ocr` never auto-resolves.** It is an input to a routing decision with a cost. The
   decision, its threshold, and the engine chosen all land in provenance.

## 2. Provenance record (one per extracted part)

```json
{
  "document_id": "…",
  "part_index": 7,
  "part_kind": "page",
  "parser": "pdfplumber",
  "parser_version": "0.11.x",
  "method": "text_layer",
  "status": "extracted",
  "chars": 2841,
  "replacement_chars": 0,
  "source_encoding": null,
  "selected_by": "chain_order",
  "candidates": [
    {"parser": "pypdf", "chars": 12, "status": "extracted", "rejected_by": "chars_below_candidate"}
  ],
  "warnings": ["pypdf: Object 12 0 not defined"],
  "extracted_at": "2026-07-29T00:00:00Z"
}
```

Field notes:

- `part_kind` — `page` for PDF, `body_part` for DOCX, `section` for HTML. Keeping the kind explicit
  stops a later reader from assuming every corpus is paginated.
- `parser_version` — the single field that turns a future engine upgrade into a reparse *query*.
  Omitting it converts every upgrade into a full-corpus rerun, which is why upgrades never happen.
- `method` — `text_layer` | `ocr`. Mixed-method documents are normal; make the mixture visible so a
  consumer can weight OCR text differently.
- `candidates` — the losing engines and why they lost. This is what makes a bad page diagnosable
  without re-running the whole chain.
- `warnings` — parser log lines captured, not swallowed. In forgiving parse modes this is often the
  *only* evidence the file was malformed.
- `source_encoding` — populated for text-ish containers (HTML, TXT, CSV); `null` for binary
  containers where the parser owns decoding.

## 3. Ledger schema

```sql
CREATE TABLE document_ingest (
  document_id      TEXT PRIMARY KEY,
  content_sha256   TEXT NOT NULL,
  declared_name    TEXT NOT NULL,          -- what the uploader called it
  declared_ext     TEXT,                   -- never overwritten
  detected_container TEXT NOT NULL,        -- from magic bytes
  container_mismatch BOOLEAN NOT NULL,     -- declared_ext vs detected_container
  expected_parts   INTEGER,                -- NULL only when the container cannot say
  extracted_parts  INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL,          -- derived, never asserted
  disposition      TEXT NOT NULL,          -- derived: done|retry|route|blocked|incomplete
  first_seen_at    TIMESTAMPTZ NOT NULL,
  last_attempt_at  TIMESTAMPTZ NOT NULL,
  UNIQUE (content_sha256)
);

-- The append-only evidence. One row per ATTEMPT, never one row per part: a retry or a
-- reparse adds a row, and nothing in the pipeline is allowed to UPDATE or DELETE here.
CREATE TABLE document_part_attempt (
  attempt_id       BIGSERIAL PRIMARY KEY,
  document_id      TEXT NOT NULL REFERENCES document_ingest(document_id),
  part_index       INTEGER NOT NULL,
  attempt_no       INTEGER NOT NULL,       -- 1, 2, 3 … per (document_id, part_index)
  attempt_reason   TEXT NOT NULL,          -- 'initial'|'retry'|'ocr_route'|'reparse_upgrade'
  part_kind        TEXT NOT NULL,
  status           TEXT NOT NULL,
  parser           TEXT,
  parser_version   TEXT,
  method           TEXT,
  chars            INTEGER,
  provenance       JSONB NOT NULL,
  attempted_at     TIMESTAMPTZ NOT NULL,
  UNIQUE (document_id, part_index, attempt_no)
);

-- The current view: a pointer, one row per part. Overwriting THIS loses nothing, because
-- the attempt it used to point at is still in the ledger above.
CREATE TABLE document_part_current (
  document_id      TEXT NOT NULL REFERENCES document_ingest(document_id),
  part_index       INTEGER NOT NULL,
  attempt_id       BIGINT NOT NULL REFERENCES document_part_attempt(attempt_id),
  selected_by      TEXT NOT NULL,          -- the promotion rule that chose this attempt
  selected_at      TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (document_id, part_index)
);

CREATE INDEX document_part_reparse
  ON document_part_attempt (parser, parser_version);
```

Design points:

- `UNIQUE (content_sha256)` is the idempotency mechanism. Resubmitting identical bytes updates one
  row; it never creates a second document.
- `expected_parts` is nullable **only** because some containers genuinely cannot report a count
  before parsing. When it is `NULL`, `coverage` is unknown — and unknown must not render as `1.0`.
- The attempt table holds rows for *failures too*. A missing row means "never attempted", which is a
  third thing again — and the derivation below reports it as an unfinished run, not as a result.

### Why the part table cannot be keyed `(document_id, part_index)`

That key is the natural one, and it is exactly what destroys the retry history. With one row per
part, a retry has nowhere to go but `UPDATE`/`UPSERT` on the row that recorded the failure, so the
pipeline overwrites its own evidence:

- **The upgrade becomes unprovable.** "Reparse every document whose text came from engine X below
  version N" runs, the rows are overwritten, and the `parser_version` that failed is gone. You can
  no longer show that the upgrade helped, which is the only reason anyone authorised it.
- **A worse retry silently wins.** Attempt 1 extracts 2,800 characters with pdfplumber; attempt 2
  crashes. Under a per-part key the crash overwrites the text, and the promotion rule ("never let a
  later engine silently overwrite an earlier result") has no data left to apply.
- **The retry counter becomes the only history**, and a counter cannot say *what* changed between
  attempt 1 and attempt 4.

The split above keeps both properties: the ledger is append-only evidence, and the pointer table is
the fast current view. Note that `PRIMARY KEY (document_id, part_index)` is *correct* on the pointer
table — the defect was never the key shape, it was putting that key on the table that holds the
evidence.

Writing an attempt is therefore two statements in one transaction: `INSERT` the attempt, then
`INSERT … ON CONFLICT (document_id, part_index) DO UPDATE` the pointer **only if the promotion rule
selects the new attempt**. A losing attempt still gets its ledger row; it just does not become
current, and `selected_by` records which rule decided.

## 4. Deriving document state (never assert it)

The document needs **two** derived fields, not one. The status says what happened; the *disposition*
says what the pipeline may still do about it, and that is the field that decides whether a retry
counter is allowed to move. Deriving only a status is how `parser_error` and `wrong_type` end up in
the same lane as a partial success.

| Disposition | Meaning | Who acts |
|---|---|---|
| `done` | Terminal. No further work changes the outcome | nobody |
| `retry` | Transient failure, bounded retry of the failed parts | the worker |
| `route` | Needs a decision with a cost: OCR, or re-dispatch to another parser route | the router |
| `blocked` | Terminal **until something outside the pipeline changes** — new bytes, a credential | a human |
| `incomplete` | Some part has no attempt row: the run did not finish | the watchdog |

```python
DISPOSITION = {                       # per-PART status -> what can still be done about it
    "extracted":        "done",
    "empty_by_content": "done",
    "needs_ocr":        "route",
    "wrong_type":       "route",      # re-dispatch; never a failure, never a retry
    "parser_error":     "retry",      # the only genuinely transient one
    "encrypted":        "blocked",    # needs a credential
    "malformed":        "blocked",    # needs new bytes
}
# When no part yielded text, the document takes the FIRST match here. Ordered by what the
# pipeline can still do, cheapest first, so the document names an actionable failure
# instead of averaging several into one that means nothing.
FAILURE_PRECEDENCE = ("parser_error", "needs_ocr", "wrong_type", "encrypted", "malformed")
USABLE = ("extracted", "empty_by_content")


def derive_document_state(expected: int | None, parts: list[dict]) -> dict:
    """`parts` = the CURRENT attempt of each part, failures included. Nothing else may
    write document_ingest.status."""
    attempted = len(parts)
    missing = max(0, expected - attempted) if expected is not None else 0
    kinds = {p["status"] for p in parts}
    usable = [p for p in parts if p["status"] in USABLE]
    coverage = len(usable) / expected if expected else None

    if not parts:
        # Zero rows is NOT a parser error: nothing was attempted. Only the container's own
        # count separates "genuinely no parts" from "the run died before writing a row".
        status, disposition = (("empty_by_content", "done") if expected == 0
                               else ("parsing", "incomplete"))
        coverage = 1.0 if expected == 0 else None
    elif not usable:
        # No text anywhere. `extracted_partial` here would claim text exists AND push a
        # re-dispatch or a credential problem into the retry lane.
        status = next(k for k in FAILURE_PRECEDENCE if k in kinds)
        disposition = DISPOSITION[status]
    elif kinds == {"empty_by_content"}:
        status, disposition = "empty_by_content", "done"
    elif kinds <= {"needs_ocr", "empty_by_content"}:
        status, disposition = "needs_ocr", "route"
    else:
        pending = {DISPOSITION[p["status"]] for p in parts if p["status"] not in USABLE}
        disposition = next((d for d in ("retry", "route", "blocked") if d in pending), "done")
        status = ("extracted" if not missing and len(usable) == attempted
                  else "extracted_partial")

    if missing and parts:
        disposition = "incomplete"    # no terminal claim is honest over an unfinished ledger
    return {"status": status, "disposition": disposition, "coverage": coverage,
            "attempted": attempted, "missing_rows": missing}
```

Worked outcomes, including the three the naive version gets wrong:

| Input (expected, current attempts) | status | disposition |
|---|---|---|
| 12, all `parser_error` | `parser_error` | `retry` |
| 3, all `wrong_type` | `wrong_type` | `route` |
| 2, `parser_error` + `malformed` | `parser_error` | `retry` |
| 3, all `empty_by_content` | `empty_by_content` | `done` |
| 3, `needs_ocr` ×2 + `empty_by_content` | `needs_ocr` | `route` |
| 12, `extracted` ×11 + `parser_error` | `extracted_partial` | `retry` |
| 12, `extracted` ×8 + `malformed` ×4 | `extracted_partial` | `blocked` |
| 12, `extracted` ×11 (one part never attempted) | `extracted_partial` | `incomplete` |
| `None`, `extracted` + `parser_error` | `extracted_partial` | `retry` |
| 0, no rows | `empty_by_content` | `done` |

Three rules the table encodes:

1. **A uniform failure keeps its own name.** Twelve crashed pages is `parser_error`, not
   `extracted_partial`. The wrong label costs you the fix: `extracted_partial` means "continue and
   alert" with a coverage number attached, so a document that produced nothing at all flows
   downstream as a partial success and the transient failure is never retried.
2. **`wrong_type` never becomes a failure state.** A DOCX on the PDF route needs re-dispatch. Derived
   as `extracted_partial` it is invisible; derived as `malformed` it pollutes the malformed rate and
   teaches the operator to distrust it.
3. **`coverage` is `len(usable) / expected` when `expected` is known, and explicitly `None`
   otherwise.** A pipeline that defaults unknown coverage to `1.0` reports a perfect score for the
   documents it understands least.

## 5. Worked example — a 12-page scan-hybrid PDF

Input: 12 pages. Pages 1–8 born with a text layer, 9–11 scanned inserts, page 12 damaged.

| part | attempts in the ledger | current | parser | method | chars |
|---|---|---|---|---|---|
| 1–8 | 1 (`extracted`) | #1 | pdfplumber | text_layer | 1.4k–3.1k |
| 9–11 | 2 (`needs_ocr`, then `extracted`) | #2 | ocr-engine | ocr | 600–900 |
| 12 | 2 (`parser_error` ×2) | #2 | pypdf, pdfplumber | text_layer | — |

Derived: `expected_parts = 12`, `attempted = 12`, `missing_rows = 0`,
`status = extracted_partial`, `disposition = retry`, `coverage = 0.917`, `ocr_share = 3/11`, failed
indices `[12]`.

The `needs_ocr` rows for pages 9–11 are still there. That is the point of the ledger: the OCR share
is not a guess reconstructed from `method`, it is the count of parts whose first attempt said
`needs_ocr` and whose second said `extracted`. Under a per-part key those first attempts are gone and
the routing decision is unauditable.

What the *wrong* pipeline stores for the same input: one row, one concatenated string of roughly
16k characters, status `ok`. The scanned pages are missing (they returned nothing), page 12 is
missing (the exception was swallowed), and nobody will ever learn either fact — the document looks
complete, just shorter than reality.

## 5b. Tests that hold the two properties

Both bugs this section exists to prevent pass a happy-path suite, because with one attempt and no
failures the broken schema and the broken derivation behave identically to the correct ones.

**Retry does not overwrite.**

```text
a1 = record_attempt(doc, part=12, status="parser_error", parser="pypdf",
                    parser_version="5.x", attempt_reason="initial")
a2 = record_attempt(doc, part=12, status="extracted", parser="pdfplumber",
                    parser_version="0.11.x", chars=1800, attempt_reason="retry")

assert [a.attempt_no for a in attempts(doc, 12)] == [1, 2]   # BOTH rows survive
assert attempts(doc, 12)[0].status == "parser_error"         # the failure is still on record
assert attempts(doc, 12)[0].parser_version == "5.x"          # and so is the engine that failed
assert current(doc, 12).attempt_id == a2                     # only the pointer moved
```

The first two assertions are the ones that fail under `PRIMARY KEY (document_id, part_index)`: the
retry upserts, `attempts(doc, 12)` returns one row, and the evidence that pypdf 5.x crashed is gone.

**A worse retry does not win.** Same part, attempt 1 `extracted` with 2,800 chars, attempt 2
`parser_error`. Assert `current` still points at attempt 1 and that `selected_by` names the promotion
rule — not the newest row.

**Reparse after an upgrade is a query, and it keeps its history.** Insert an attempt with
`attempt_reason='reparse_upgrade'`, then assert the pre-upgrade attempt is still readable and that
`chars` can be compared across the two. That comparison *is* the proof the upgrade helped; the
per-part key deletes the baseline it needs.

**Every uniform failure keeps its name.** Table-drive the derivation over the section 4 matrix. The
two rows that matter are all-`parser_error` and all-`wrong_type`: assert `status` is not
`extracted_partial`, and assert `disposition` is `retry` and `route` respectively. Asserting only the
status lets a future refactor keep the name and still route the document into the wrong lane.

**An unattempted part is not a result.** Write 11 attempt rows for a 12-part document and assert
`disposition == "incomplete"` and `missing_rows == 1`. A pipeline that reports `done` here silently
publishes an 11-page version of a 12-page document.

## 6. Anti-patterns in storage

| Anti-pattern | Why it destroys information |
|---|---|
| A single `text` column and nothing else | Every distinction in section 1 collapses to string length |
| `success BOOLEAN` | Cannot express partial, cannot express "needs a credential" |
| Storing only failures | "Never attempted" and "attempted and fine" become indistinguishable |
| One row per part, keyed `(document_id, part_index)` | A retry has nowhere to go but `UPSERT`, so the pipeline overwrites its own evidence and the engine upgrade becomes unprovable |
| A retry counter instead of attempt rows | A number cannot say *what* changed between attempt 1 and attempt 4 |
| Deriving a status without a disposition | `parser_error` and `wrong_type` land in the same lane as a partial success |
| Uniform failure derived as `extracted_partial` | A document that produced no text at all flows downstream as a partial success, and the transient failure is never retried |
| Keying quarantine by filename | Resubmission duplicates; identical bytes must converge |
| Deriving nothing, asserting everything | Document status drifts out of sync with its own parts |
| `coverage` defaulting to 1.0 when `expected` is unknown | Highest score goes to the least understood documents |

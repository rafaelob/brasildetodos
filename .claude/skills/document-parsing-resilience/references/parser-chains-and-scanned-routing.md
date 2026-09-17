# Parser Chains and Scanned-Page Routing

Engine capability notes, chain composition, and how to decide that a page needs OCR. Read before
composing a fallback chain or choosing a detection cutoff.

## 1. Engine capability notes (verified 2026-07-29)

Only documented capability statements appear here — the boundaries a design can rely on. Version
numbers are deliberately absent: re-verify against the installed release before quoting anything.

### pypdf — `pypdf.readthedocs.io`

- Extraction is text-layer only, stated flatly: "pypdf is **not** OCR software" and "pypdf will also
  never be able to extract text from images". For image-based pages, "the extracted text may be
  minimal or visually empty" — it *succeeds* and returns nothing useful.
- `extract_text()` takes an orientation argument (e.g. `extract_text(0)` for "extract only text
  oriented up"), horizontal-spacing control, and an `extraction_mode` with a `"layout"` option that
  yields text "in a fixed width format that closely adheres to the rendered" page.
- Layout warnings from its own docs: "in complicated PDF documents the coordinates given to the
  visitor functions may be wrong", and "This representation used within the PDF file makes it very
  hard to guarantee correct whitespaces". Do not build a downstream parser that depends on exact
  whitespace from any PDF engine.
- Robustness: `strict=True` "means that pypdf will raise an exception if a PDF does not follow the
  specification"; `strict=False` "means that pypdf will try to be forgiving and do something
  reasonable, but it will log a warning message". **In forgiving mode the log line is the only
  malformed-file signal** — capture it into provenance.
- Encryption: the documented pattern is `if reader.is_encrypted: reader.decrypt(password)`. Supported
  algorithms are listed as `RC4-40`, `RC4-128`, `AES-128`, `AES-256-R5`, `AES-256`, with support "until
  `PDF-2.0`". Detect encryption *before* extraction so the state is `encrypted`, not "empty".
- Layout mode also costs memory: "This can require quite a lot of memory".

### pdfplumber — `github.com/jsvine/pdfplumber`

- "Built on `pdfminer.six`." Failure modes are inherited from that layer.
- Default `extract_text()` reconstructs spacing geometrically: it "Adds spaces where the difference
  between the `x1` of one character and the `x0` of the next is greater than `x_tolerance`", and
  newlines by the analogous `doctop`/`y_tolerance` rule. Tolerances are tunable — and a corpus with
  unusual typography may need them tuned rather than a different engine.
- `extract_text(layout=True)` "Attempts to mimic the structural layout of the text on the page(s)"
  and is labelled experimental. Do not make a contract depend on it.
- Layout-analysis parameters pass through: `pdfplumber.open("file.pdf", laparams={...})`.
- Scanned documents: "Works best on machine-generated, rather than scanned, PDFs", and it explicitly
  does not provide "Optical character recognition (OCR)" nor "Strong support for extracting tables
  from OCR'ed documents".
- Its README documents **no** repair parameter. If your corpus needs structural repair, that is a
  separate pre-step with its own tool and its own recorded provenance — not a parser flag.

### PyMuPDF — `pymupdf.readthedocs.io`

- Licensing is a design constraint, not a footnote: "PyMuPDF and MuPDF are now available under both,
  open-source AGPL and commercial license agreements", with Artifex named as "the exclusive
  commercial licensing agent for MuPDF". Decide this before it ships.
- Extraction has structured output modes — `page.get_text("blocks")` for text blocks with position
  information, `get_text("words")` for single words (with customisable `delimiters`), and
  `get_text("dict", …)` for font/colour detail. Structured modes are what let you compute layout
  signals instead of guessing from a flat string.
- Reading order is not guaranteed: text "may not appear in any particular reading order" (the docs
  attribute this to page headers having been "inserted in a separate step"). A `sort` parameter
  "will sort the output from top-left to bottom-right (ignored for XHTML, HTML and XML output)".
- Verify OCR-related capabilities on its own OCR page before assuming any are available in your build.

### python-docx — `python-docx.readthedocs.io`

The API docs are precise about what the convenience collections *exclude*, and each exclusion is a
silent-data-loss trap:

- `Document.paragraphs` — "The Paragraph instances in the document, in document order." But:
  "paragraphs within revision marks such as `<w:ins>` or `<w:del>` do not appear in this list."
- `Document.tables` — "All Table instances in the document, in document order", with the caveat that
  "only tables appearing at the top level of the document appear in this list; a table nested inside
  a table cell does not appear", and revision-marked tables "will also not appear in the list".
- `Document.iter_inner_content()` — "Generate each Paragraph or Table in this document in document
  order." This is the collection to use when *order between* paragraphs and tables matters, which it
  does for anything reconstructing a document's reading flow.
- The docs make no statement about headers, footers or textboxes in relation to these collections.
  Treat their coverage as **unverified** and test against your own corpus before claiming a DOCX
  extraction is complete — a contract review whose obligations live in a header is the exact case
  that fails silently.

## 2. Composing the chain

Ordering principle: **cheapest deterministic first, OCR last, provenance always.**

| Container | Chain | Notes |
|---|---|---|
| PDF, born-digital corpus | text-layer engine A → text-layer engine B → OCR | Two text engines earn their place only if they disagree measurably on your corpus; verify before adding cost |
| PDF, mixed scan corpus | text-layer engine → scanned detection → OCR per page | Route **per page**, never per document; hybrid documents are the norm |
| DOCX | XML-level ordered traversal | Use the ordered content iterator; account for tables, revision marks, headers/footers explicitly |
| Legacy `.doc` (OLE2) | Dedicated route or convert-then-parse | Never send OLE2 bytes to a ZIP-based parser; it reports "not a zip file" and tells you nothing |
| HTML | Tolerant parser → text extraction | Encoding comes first; a wrong decode makes every selector unreliable |

### Promotion rules

Whenever two engines both produce output for the same part, the winner is chosen by a **written**
rule, and the loser stays in `candidates`:

| Rule | Use when | Failure mode to watch |
|---|---|---|
| `chain_order` — first success wins | Engines are ranked by known corpus fidelity | A degraded first engine silently caps quality; monitor per-engine char distributions |
| `max_chars` — most characters wins | Engines differ mainly in how much they drop | Rewards an engine that emits ligature noise or repeated headers |
| `min_replacement_chars` — fewest U+FFFD wins | Encoding damage is the dominant defect | Ignores structural loss; combine with a char floor |
| `hybrid` — char floor, then chain order | Default recommendation | Requires a floor, which must be calibrated, not invented |

Never implement "last engine wins": the last rung is normally the most degraded (or the most
expensive), and a silent overwrite makes the whole chain pointless.

### Timeouts and budget

Each rung gets its own timeout, and the timeout is a `parser_error` on that rung — not a document
failure. Cap total per-document engine attempts so one pathological file cannot consume a worker
indefinitely; record the cap being hit as a distinct reason, because "hit the attempt cap" and
"every engine genuinely failed" call for different investigations.

## 3. Scanned / image-only detection

Text-layer engines do not raise on a scanned page; they return almost nothing (pypdf's own docs:
"minimal or visually empty"). Detection therefore reads *signals*, and combining signals beats any
single one:

| Signal | Reads | Weakness alone |
|---|---|---|
| Characters extracted per page | Cheapest, works everywhere | A sparse legitimate page (cover, form, chapter divider) looks identical |
| Share of pages at or near zero characters | Catches whole-document scans | Misses hybrid documents, which are the common hard case |
| Full-page image object present | Strong structural evidence | Requires an engine exposing image objects; a decorative background can mimic it |
| Ratio of image area to page area | Distinguishes decoration from a scan | Costs a structured parse per page |
| Font resources declared on the page | A page with no fonts has no text layer | Some generators declare unused fonts |

### Threshold calibration procedure

There is no universal character cutoff, and any number quoted as one is corpus-specific. Calibrate:

1. **Sample** 150–300 pages spanning every document source in the corpus (not one representative
   file — sources differ more than pages do).
2. **Label** each page by hand: `has_text_layer` yes/no. This is the ground truth; nothing downstream
   is better than it.
3. **Sweep** the candidate signal across its range and record, at each value, how many text-layer
   pages get sent to OCR (wasted cost) and how many scanned pages get accepted as text (silent data
   loss).
4. **Choose the operating point deliberately.** These two errors are not symmetric: OCRing a
   text-layer page costs money; accepting a scanned page as "empty" loses the document's content
   invisibly. Bias toward OCR unless the cost is genuinely binding.
5. **Store** the chosen value with its calibration date and the sample size, next to the pipeline
   config. An undated threshold becomes folklore within a quarter.
6. **Re-calibrate** when a new document source is onboarded. New source, new distribution.

### The OCR routing contract

Entering OCR is a decision that must be recorded — `method=ocr`, engine name, engine version, the
signal value that triggered it, and the threshold in force. Three consequences to design for:

- **Cost and latency** are orders of magnitude above text-layer extraction. Route per page, and cap
  the OCR share per batch so a misconfigured threshold produces an alert rather than an invoice.
- **OCR text has different failure modes**: character confusions, lost table structure, invented
  words. Downstream consumers that weight text by confidence need to know the method.
- **OCR failure is its own state**, not a fallback to "empty". A page that failed OCR is
  `parser_error` on the OCR rung, retryable, and still visible as a gap in coverage.

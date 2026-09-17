# Encoding Repair and Normalization

The decode path for text-ish containers (HTML, XML, TXT, CSV) and the normalization policy for
everything the pipeline stores. Read before writing any `.decode()` call.

All measurements marked [observed] were run locally on Python 3.13.12 on 2026-07-29. Standard-library
and specification quotes were verified the same day against `docs.python.org/3/library/codecs.html`,
`encoding.spec.whatwg.org` and `unicode.org/reports/tr15/`.

## 1. Store bytes, derive text

Persist the raw bytes and their SHA-256. Text is a derived artifact of a *decode decision*, and the
decision is frequently wrong on the first attempt. If you keep only the decoded string, a wrong
decode is permanent; if you keep the bytes, it is a reparse.

Record alongside the text: `source_encoding`, how it was determined (`bom` | `declared` | `detected`
| `fallback`), the detector's confidence when one was used, and the `replacement_chars` count.

## 2. The decode ladder

Ordered, and each rung records *why* it was chosen.

| Rung | Action | Record |
|---|---|---|
| 1 | **BOM.** If a byte order mark is present, it decides. | `source_encoding_from=bom` |
| 2 | **Declared.** HTTP `Content-Type` charset, HTML `<meta charset>`, XML declaration. | `declared_encoding`, and whether it later proved wrong |
| 3 | **UTF-8 strict.** Try it even when something else was declared — most modern content is UTF-8 regardless of what the header says. | `source_encoding_from=probe` |
| 4 | **Detector.** A statistical detector, keeping its confidence score. | `detected_encoding`, `detector_confidence` |
| 5 | **cp1252 strict.** The legacy Western fallback that can still *fail*. | `source_encoding_from=fallback` |
| 6 | **UTF-8 with `errors="replace"`,** count the U+FFFD, flag the document. | `replacement_chars`, quality flag |

The WHATWG Encoding Standard settles rungs 1 and 2 (verified 2026-07-29):

- "the byte order mark is more authoritative than anything else" and "A byte order mark has priority
  over a label as it has been found to be more accurate" — so the BOM beats any declaration.
- The labels `ansi_x3.4-1968`, `ascii`, `cp1252`, `cp819`, `csisolatin1`, `ibm819`, `iso-8859-1`,
  `iso-ir-100`, `iso8859-1`, `iso88591`, `iso_8859-1`, `l1`, `latin1`, `us-ascii` and `windows-1252`
  **all map to windows-1252**. A document declaring `iso-8859-1` should be decoded as cp1252, which
  is what browsers do; decoding it as true ISO-8859-1 turns smart quotes and the euro sign into C1
  control characters.
- "New protocols and formats...must use the UTF-8 encoding exclusively" — worth quoting to whoever
  produces the upstream files, because fixing the source beats repairing forever.

### Why latin-1 must not be the last rung

Measured [observed]: `bytes(range(256)).decode("latin-1")` succeeds and returns 256 characters —
latin-1 decodes **every possible byte sequence** without raising. A ladder that ends in latin-1
therefore *can never report an encoding failure*: it always produces a confident, wrong answer.

By contrast, `cp1252` raises `UnicodeDecodeError` on `0x81`, `0x8D`, `0x8F`, `0x90` and `0x9D`
[observed] — five undefined bytes that make cp1252 a *detectable* legacy attempt. That is the whole
reason it belongs on rung 5 and latin-1 does not.

If you genuinely must accept arbitrary bytes, use `errors="surrogateescape"` rather than latin-1. The
Python docs describe it as: "On decoding, replace byte with individual surrogate code ranging from
`U+DC80` to `U+DCFF`. This code will then be turned back into the same byte when the
`'surrogateescape'` error handler is used when encoding the data." It is the one lossless carrier for
undecodable bytes — but the resulting string is not valid for most downstream consumers, so it is a
transport mechanism, not a storage format.

### Error handlers, in the docs' own words (verified 2026-07-29)

| Handler | Documented behaviour | Use in ingest |
|---|---|---|
| `strict` | "Raise `UnicodeError` (or a subclass), this is the default." | Rungs 3 and 5 — you want the failure |
| `ignore` | "Ignore the malformed data and continue without further notice." | **Never.** Measured [observed]: 128 of 256 bytes silently dropped |
| `replace` | "On decoding, use `�` (U+FFFD, the official REPLACEMENT CHARACTER)." | Last rung only, with the count recorded |
| `backslashreplace` | "On decoding, use hexadecimal form of byte value with format `\xhh`." | Debugging a specific document |
| `surrogateescape` | Byte ↔ `U+DC80`–`U+DCFF`, round-trips back to the same byte | Lossless transport of unknown bytes |

`replace` is the only lossy handler acceptable on ingest, because the damage is *countable*: the same
256-byte input produced exactly 128 U+FFFD characters [observed], which is a metric. `ignore`
produced a 128-character string with no signal at all — the loss is undetectable after the fact.

## 3. Mojibake: detect, then repair with a guard

Mojibake is UTF-8 bytes that were decoded as a single-byte codec. Measured [observed] on
`"ação — “aspas” €5"`:

- Encoded as UTF-8, then decoded as **cp1252** → raises (`0x9d` undefined). The strict codec catches it.
- Encoded as UTF-8, then decoded as **latin-1** → `'aÃ§Ã£o â\x80\x94 â\x80\x9caspasâ\x80\x9d â\x82¬5'`.
  No error, visibly broken.
- Repair by re-encoding to latin-1 and decoding as UTF-8 → round-trips to the original exactly [observed].

### Detection signals

- Sequences of `Ã`, `Â`, `â€`, `Ð`, `Ñ` followed by punctuation-range characters.
- A high ratio of characters in `U+0080`–`U+00BF` in text that is supposed to be a Western language.
- `C1` control characters (`U+0080`–`U+009F`) in prose — true ISO-8859-1 decoding of cp1252 bytes.

### Repair procedure with its guard

```python
def repair_mojibake(text: str) -> tuple[str, bool]:
    """Return (text, repaired). Only claims a repair when the round-trip is exact."""
    try:
        candidate = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text, False          # not this failure mode; leave it alone
    if candidate.encode("utf-8").decode("utf-8") != candidate:
        return text, False
    return candidate, True
```

The guard matters: a blind `encode("latin-1").decode("utf-8")` applied to text that was *never*
mojibake will either raise or produce garbage. Attempt it once, verify, and record `repaired=true` in
provenance — a repair that leaves no trace is indistinguishable from data that was always correct,
which makes the upstream bug unfixable.

Apply the repair **once**, at ingest. Double-repair is a real failure: text mangled twice needs the
transformation applied twice, and the only safe way to know is the recorded flag, not a re-detection.

## 4. Normalization policy

Normalize to **NFC**, once, at the ingest boundary, after the text is fully assembled. Three facts
from UAX #15 (verified 2026-07-29) shape the policy:

- **Idempotence:** `toNFC(toNFC(x)) = toNFC(x)`, and `isNFx(s)` is true "if and only if `toNFX(s)` is
  identical to `s`". Re-normalizing is safe, so a defensive normalize costs nothing but time.
- **Not closed under concatenation:** "none of the Normalization Forms are closed under string
  concatenation" — for two normalized strings X and Y, "their string concatenation X+Y is *not*
  guaranteed to be normalized". Measured [observed]: `"A"` + `"́o"` (combining acute, then `o`), each
  normalized, concatenates to a string that is **not** NFC. **Consequence for this pipeline:** when
  page text from several engines is joined, normalize the *joined* result, not only each page.
- **NFKC/NFKD lose information:** "Neither NFKD nor NFKC maintains compatibility composites", they
  "will prevent round-trip conversion to and from many legacy character sets", and they "must *not*
  be blindly applied to arbitrary text". Measured [observed]: NFKC turns `ﬁ` into `fi` and `m²` into
  `m2` — a unit silently becomes a different quantity. Use NFKC only inside a *search index*, never
  for the stored document text.

Also record NFC as a fact, because a corpus half-normalized is worse than one consistently un-normalized:
equality comparisons and deduplication both silently fail across the boundary. Measured [observed]:
NFC `"ação"` is 4 code points, NFD is 6 — the same word, never equal by byte comparison.

## 5. Container-specific rules

### HTML

- Declared charset is frequently wrong; the ladder's UTF-8 probe (rung 3) catches most of it.
- A `<meta charset>` inside the document is itself bytes you must decode to read. Read it from an
  ASCII-safe prefix scan, then decode the whole document.
- Malformed markup and wrong encoding are *different* failures. Fix the encoding first: a wrong
  decode breaks tag boundaries and makes every parser complaint downstream a phantom.
- Entity-encoded text (`&amp;#233;`) survives decoding and needs a separate unescape pass; record
  whether you performed it.

### XML

- The XML declaration's `encoding` attribute is authoritative *unless* a BOM disagrees, in which case
  the BOM wins (WHATWG rule above).
- A declaration claiming UTF-8 over cp1252 bytes normally raises in a strict parser. Do not "fix" this
  by switching the parser to a lenient mode — fix the decode, or record `malformed`.

### CSV / TXT

- A UTF-8 BOM appears as a leading `﻿` when decoded as plain `utf-8`, which then becomes part of
  the first column's header name. Use `utf-8-sig` when a BOM is possible, and record which you used.
- Line-ending mixtures (`\r\n`, `\n`, bare `\r`) are not an encoding problem; keep them out of the
  encoding metrics or the signal gets muddy.

## 6. Metrics to publish

| Metric | Definition | Reads as |
|---|---|---|
| `replacement_char_rate` | U+FFFD per 1000 characters | Decode damage. Non-zero always means a decision was lossy |
| `fallback_rung_share` | Documents decoded at rung 5 or 6 | How often the ladder gave up |
| `mojibake_repair_rate` | Documents where the guarded repair succeeded | An upstream producer bug worth reporting |
| `detector_confidence_p10` | 10th percentile of detector confidence | How much of the corpus is being guessed at |
| `nfc_normalized_share` | Should be 1.0 | Anything below means a mixed corpus and broken deduplication |

All five are heuristics about *process*, not verdicts about content. Route them to alerts and to
quarantine review — never to an automatic discard.

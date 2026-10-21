"""Local PDF extraction. No uploaded document is fetched or published by the web API."""
from __future__ import annotations
import hashlib
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from .domain import brl


_BRL_AMOUNT = r"(R\$\s*(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2})(?![0-9,]|\.[0-9])"
_BR_DATE = r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})"
_DATE_FIELDS = {
    "signature_date", "start_date", "end_date", "publication_date", "amendment_date",
}
_VALUE_FIELDS = {
    "estimated_cents", "global_value", "amendment_cents", "installment_cents",
    "payment_cents", "counterpart_cents",
}
_OCR_ROUTES = {"ocr_candidate", "review_encoding", "hybrid_review"}
_FAMILY_TERMS = (
    ("amendment", r"\bTERMO\s+ADITIVO\b|\bADITIVO\b"),
    ("contract", r"\bCONTRATO\b"),
    ("agreement", r"\bCONV[ÊE]NIO\b"),
    ("work_plan", r"\bPLANO\s+DE\s+TRABALHO\b"),
)
_FAMILY_PRIORITY = {"amendment": 0, "contract": 1, "agreement": 2, "work_plan": 3}
_PRIVACY_PATTERNS = (
    ("cpf", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")),
    ("cpf", re.compile(r"\bCPF\b[^\d]{0,12}(\d{11})(?!\d)", re.I)),
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.I)),
    ("phone", re.compile(r"\b(?:TELEFONE|TEL\.?|CELULAR|WHATSAPP|FONE)\b[^\d]{0,12}"
                          r"(\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4})(?!\d)", re.I)),
    ("phone", re.compile(r"(?<!\d)\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}(?!\d)")),
    ("signature", re.compile(r"\b(?:ASSINATURA|ASSINADO\s+(?:POR|DIGITALMENTE)|"
                              r"SIGNAT[AÁ]RIO)\b", re.I)),
    ("rg", re.compile(r"\bRG\b[^\d]{0,12}(\d{5,12})(?!\d)", re.I)),
)


def privacy_flags(text: str) -> list[dict]:
    """Find review-only privacy signals without retaining the matched value."""
    found = {}
    for kind, pattern in _PRIVACY_PATTERNS:
        for match in pattern.finditer(text or ""):
            group = 1 if match.lastindex else 0
            start, end = match.start(group), match.end(group)
            found[(kind, start, end)] = {"kind": kind, "start": start, "end": end}
    return sorted(found.values(), key=lambda item: (item["start"], item["end"], item["kind"]))[:100]


def _privacy(pages: list[dict]) -> dict:
    flags = []
    for page in pages:
        for flag in page.get("privacy_flags", []):
            flags.append(flag | {"page": page["page"]})
    counts = Counter(flag["kind"] for flag in flags)
    unreviewed = [{"page": page["page"], "route": page["route"]}
                  for page in pages if page.get("route") != "native"]
    return {
        "review_required": bool(flags or unreviewed),
        "flags": flags[:200],
        "kinds": [{"kind": kind, "count": count,
                   "pages": sorted({flag["page"] for flag in flags if flag["kind"] == kind})}
                  for kind, count in sorted(counts.items())],
        "unreviewed_routes": unreviewed[:100],
        "text_basis": "native_text_only",
        "publication_allowed": False,
    }


def _iso_br_date(raw: str) -> str | None:
    """Parse an explicit Brazilian dd/mm/yyyy date; never guess an ambiguous one."""
    try:
        day, month, year = (int(part) for part in raw.split("/"))
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        return None


def candidates(text: str) -> list[dict]:
    output = []
    patterns = {
        "agreement_reference": r"CONV[ÊE]NIO\s*(?:N[°ºO.]?\s*)?([0-9]{3,8}/[0-9]{4})",
        "proposal_reference": r"PROPOSTA\s*(?:N[°ºO.]?\s*)?([0-9]{3,8}/[0-9]{4})",
        "contract_reference": r"CONTRATO\s*(?:N[°ºO.]?\s*)?([0-9]{1,8}/[0-9]{4})",
        "amendment_reference": r"TERMO\s+ADITIVO\s*(?:N[°ºO.]?\s*)?([0-9]{1,4}/[0-9]{4})",
        "process_reference": r"PROCESSO\s*(?:ADMINISTRATIVO)?\s*(?:N[°ºO.]?\s*)?([0-9]{3,7}/[0-9]{4}|[0-9]{5}\.[0-9]{6}/[0-9]{4}-[0-9]{2})",
        "cnpj_reference": r"(?:CNPJ(?:\s*N[°ºO.]?)?\s*:?\s*)?([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})",
        "estimated_cents": rf"VALOR\s+ESTIMADO\s*:?\s*{_BRL_AMOUNT}",
        "global_value": rf"VALOR\s+(?:GLOBAL|TOTAL|HOMOLOGADO)\s*:?\s*{_BRL_AMOUNT}",
        "amendment_cents": rf"VALOR\s+(?:DO\s+)?(?:TERMO\s+)?ADITIVO\s*:?\s*{_BRL_AMOUNT}",
        "installment_cents": rf"VALOR\s+(?:DA\s+)?PARCELA\s*:?\s*{_BRL_AMOUNT}",
        "payment_cents": rf"VALOR\s+(?:PAGO|DO\s+PAGAMENTO)\s*:?\s*{_BRL_AMOUNT}",
        "counterpart_cents": rf"(?:VALOR\s+DA\s+)?CONTRAPARTIDA\s*:?\s*{_BRL_AMOUNT}",
        "planned_capacity": r"AT[ÉE]\s+([0-9]+)\s+CRIAN[ÇC]AS",
        "legal_basis": r"LEI\s+(?:FEDERAL\s+)?(?:N[°ºO.]?\s*)?([0-9]{1,2}\.[0-9]{3}(?:/[0-9]{2,4})?|[0-9]{4,5}/[0-9]{2,4})",
        "signature_date": rf"(?:DATA\s+(?:DA|DE)\s+ASSINATURA|ASSINADO\s+EM)\s*:?\s*{_BR_DATE}",
        "start_date": rf"(?:DATA\s+(?:DE\s+)?IN[ÍI]CIO|IN[ÍI]CIO\s+(?:DA\s+)?VIG[ÊE]NCIA)\s*:?\s*{_BR_DATE}",
        "end_date": rf"(?:DATA\s+(?:DE\s+)?(?:T[ÉE]RMINO|FIM)|T[ÉE]RMINO\s+(?:DA\s+)?VIG[ÊE]NCIA)\s*:?\s*{_BR_DATE}",
        "publication_date": rf"(?:DATA\s+(?:DE\s+)?PUBLICA[ÇC][ÃA]O|PUBLICADO\s+EM)\s*:?\s*{_BR_DATE}",
        "amendment_date": rf"DATA\s+(?:DO|DE)\s+(?:TERMO\s+)?ADITIVO\s*:?\s*{_BR_DATE}",
    }
    for field, pattern in patterns.items():
        if field.endswith(("_reference", "_date")) or field == "legal_basis":
            # A supported identifier must be a complete lexical token: never
            # invent 12/2025 from 12/20255, or CONTRATO from SUBCONTRATO.
            # Standalone CNPJ numbers also cannot start inside another number.
            prefix = r"(?<![\w./-])" if field == "cnpj_reference" else r"(?<!\w)"
            pattern = prefix + pattern + r"(?![\w/]|[.-][\w])"
        for match in re.finditer(pattern, text, re.I):
            raw = match.group(1)
            if field in _DATE_FIELDS:
                parsed = _iso_br_date(raw)
                item = {"field": field, "value": parsed or raw, "raw": raw,
                        "start": match.start(1), "end": match.end(1), "state": "candidate",
                        "publication_allowed": False, "date_valid": parsed is not None}
            else:
                value = (brl(raw) if field in _VALUE_FIELDS else
                         int(raw) if field == "planned_capacity" else raw)
                item = {"field": field, "value": value, "raw": raw,
                        "start": match.start(1), "end": match.end(1), "state": "candidate",
                        "publication_allowed": False}
            output.append(item)
    return output


def _cell(value) -> str:
    return "" if value is None else re.sub(r"\s+", " ", str(value)).strip()


def _normalized_table(table) -> list[list[str]]:
    if not isinstance(table, list):
        return []
    rows = [[_cell(cell) for cell in row] for row in table if isinstance(row, list)]
    return [row for row in rows if any(row)]


def _multipage_tables(pages: list[dict]) -> list[dict]:
    """Join only consecutive pages whose first table repeats an identical header.

    This is a conservative review aid, not proof that a table is complete. A
    page with several tables is never joined automatically, and single-page
    tables remain in the per-page extraction.
    """
    groups: list[dict] = []
    previous_single: dict | None = None
    for page in pages:
        tables = [_normalized_table(table) for table in page.get("tables", [])]
        tables = [table for table in tables if len(table) >= 2]
        if len(tables) != 1:
            for table in tables:
                groups.append({"header": table[0], "pages": [page["page"]],
                               "rows": [{"page": page["page"], "cells": row} for row in table[1:]]})
            previous_single = None
            continue
        table = tables[0]
        header, rows = table[0], table[1:]
        if (previous_single is not None
                and previous_single["pages"][-1] == page["page"] - 1
                and previous_single["header"] == header):
            previous_single["pages"].append(page["page"])
            previous_single["rows"].extend({"page": page["page"], "cells": row} for row in rows)
        else:
            previous_single = {"header": header, "pages": [page["page"]],
                               "rows": [{"page": page["page"], "cells": row} for row in rows]}
            groups.append(previous_single)
    return [{"pages": group["pages"], "header": group["header"], "rows": group["rows"],
             "source": "native_tables", "continuation_basis": "repeated_header",
             "review_required": True, "publication_allowed": False}
            for group in groups if len(group["pages"]) > 1]


def _document_family(pages: list[dict]) -> dict:
    """Lexical family markers from native text only; never a legal conclusion."""
    evidence = []
    for page in pages:
        text = page.get("text") or ""
        for family, pattern in _FAMILY_TERMS:
            for match in re.finditer(pattern, text, re.I):
                evidence.append({"family": family, "term": match.group(0),
                                 "page": page["page"], "start": match.start(), "end": match.end()})
    if not evidence:
        return {"primary": None, "families": [], "evidence": [],
                "text_basis": "native_text_only", "review_required": True,
                "publication_allowed": False}
    counts = Counter(item["family"] for item in evidence)
    first_page = min(item["page"] for item in evidence)
    first_page_evidence = [item for item in evidence if item["page"] == first_page]
    primary = min(first_page_evidence,
                  key=lambda item: (item["start"], _FAMILY_PRIORITY[item["family"]]))["family"]
    families = [{"family": family, "count": count,
                 "pages": sorted({item["page"] for item in evidence if item["family"] == family})}
                for family, count in sorted(counts.items(),
                                            key=lambda pair: (-pair[1], _FAMILY_PRIORITY[pair[0]]))]
    return {"primary": primary, "families": families, "evidence": evidence[:100],
            "text_basis": "native_text_only", "review_required": True,
            "publication_allowed": False}


def ocr_eligible(page: dict) -> bool:
    """Prefer the explicit route decision; keep legacy stored pages readable."""
    value = page.get("ocr_eligible") if isinstance(page, dict) else None
    if type(value) is bool:
        return value
    return isinstance(page, dict) and page.get("route") in _OCR_ROUTES


def inspect_pdf(path: Path, max_pages: int = 100, max_bytes: int = 32 * 1024 * 1024) -> dict:
    import pdfplumber
    if path.stat().st_size > max_bytes or not path.read_bytes()[:5] == b"%PDF-":
        raise ValueError("Invalid PDF or byte budget exceeded")
    result = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "filename": path.name,
              "extractor_version": "native-pdf-v2", "pages": [], "original_preserved": True,
              "document_family": None, "multipage_tables": [], "privacy": None}
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > max_pages:
            raise ValueError("Page budget exceeded; split the reviewed processing job")
        for index, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            image_area = max((max(0, im["x1"] - im["x0"]) * max(0, im["bottom"] - im["top"]) for im in page.images), default=0)
            fraction = min(1, image_area / max(page.width * page.height, 1))
            text_length = len(text.strip())
            rotation = int(page.rotation or 0)
            rotated = rotation in (90, 270)
            effective_width, effective_height = ((page.height, page.width) if rotated
                                                 else (page.width, page.height))
            orientation = "landscape" if effective_width > effective_height else "portrait"
            if not text_length and fraction <= 0:
                route = "inspect_blank_or_graphic"
            elif not text_length:
                route = "ocr_candidate"
            elif text.count("\ufffd") / max(len(text), 1) > .02:
                route = "review_encoding"
            elif rotation not in (0, 90, 180, 270):
                route = "review_orientation"
            elif fraction > .65 and text_length < 200:
                route = "ocr_candidate"
            elif fraction > .35 and text_length < 2000:
                route = "hybrid_review"
            else:
                route = "native"
            eligible = (route in _OCR_ROUTES
                        or (route == "review_orientation" and (not text_length or fraction > .35)))
            tables = page.extract_tables() if route in {"native", "hybrid_review", "review_orientation"} else []
            words = [{key: word[key] for key in ("text", "x0", "top", "x1", "bottom")} for word in page.extract_words()]
            flags = privacy_flags(text)
            result["pages"].append({"page": index, "width": page.width, "height": page.height,
                                    "rotation": rotation, "orientation": orientation,
                                    "route": route, "ocr_eligible": eligible,
                                    "text": text, "text_length": text_length,
                                    "image_fraction": round(fraction, 4), "words": words,
                                    "tables": tables, "candidates": candidates(text),
                                    "privacy_flags": flags,
                                    "privacy_review_required": bool(flags) or route != "native"})
    result["document_family"] = _document_family(result["pages"])
    result["multipage_tables"] = _multipage_tables(result["pages"])
    result["privacy"] = _privacy(result["pages"])
    return result


def ocr_page(path: Path, number: int, language: str = "por", timeout: int = 90) -> str:
    """Explicit last-resort OCR for one inspected page. Original bytes never change."""
    if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3})*", language) or number < 1:
        raise ValueError("Invalid OCR parameters")
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        raise RuntimeError("OCR is optional: install tesseract-ocr-por and poppler-utils in the document worker")
    with tempfile.TemporaryDirectory(prefix="bdt-ocr-") as folder:
        prefix = str(Path(folder) / "page")
        subprocess.run(["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-r", "300", "-png", str(path.resolve()), prefix], check=True, capture_output=True, timeout=timeout)
        result = subprocess.run(["tesseract", prefix + ".png", "stdout", "-l", language, "--psm", "3"], check=True, capture_output=True, text=True, timeout=timeout)
        if not result.stdout.strip():
            raise ValueError("OCR returned no usable text; review required")
        return result.stdout

"""Local PDF extraction. No uploaded document is fetched or published by the web API."""
from __future__ import annotations
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from .domain import brl


def candidates(text: str) -> list[dict]:
    output = []
    patterns = {
        "agreement_reference": r"CONV[ÊE]NIO\s*(?:N[°ºO.]?\s*)?([0-9]{3,8}/[0-9]{4})",
        "proposal_reference": r"PROPOSTA\s*(?:N[°ºO.]?\s*)?([0-9]{3,8}/[0-9]{4})",
        "estimated_cents": r"VALOR\s+ESTIMADO\s*:?\s*(R\$\s*[0-9.]+,[0-9]{2})",
        "planned_capacity": r"AT[ÉE]\s+([0-9]+)\s+CRIAN[ÇC]AS",
    }
    for field, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.I):
            raw = match.group(1)
            value = brl(raw) if field == "estimated_cents" else int(raw) if field == "planned_capacity" else raw
            output.append({"field": field, "value": value, "raw": raw, "start": match.start(1), "end": match.end(1), "state": "candidate", "publication_allowed": False})
    return output


def inspect_pdf(path: Path, max_pages: int = 100, max_bytes: int = 32 * 1024 * 1024) -> dict:
    import pdfplumber
    if path.stat().st_size > max_bytes or not path.read_bytes()[:5] == b"%PDF-":
        raise ValueError("Invalid PDF or byte budget exceeded")
    result = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "filename": path.name, "pages": [], "original_preserved": True}
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > max_pages:
            raise ValueError("Page budget exceeded; split the reviewed processing job")
        for index, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            image_area = max((max(0, im["x1"] - im["x0"]) * max(0, im["bottom"] - im["top"]) for im in page.images), default=0)
            fraction = min(1, image_area / max(page.width * page.height, 1))
            if fraction > .65 and len(text.strip()) < 200:
                route = "ocr_candidate"
            elif not text.strip():
                route = "inspect_blank_or_graphic"
            elif text.count("\ufffd") / max(len(text), 1) > .02:
                route = "review_encoding"
            else:
                route = "native"
            words = [{key: word[key] for key in ("text", "x0", "top", "x1", "bottom")} for word in page.extract_words()]
            result["pages"].append({"page": index, "width": page.width, "height": page.height, "rotation": page.rotation,
                                    "route": route, "text": text, "words": words,
                                    "tables": page.extract_tables() if route == "native" else [], "candidates": candidates(text)})
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

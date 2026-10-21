"""Synthetic PDF structure tests: families, roles, multipage tables, rotation and hybrid pages.

No file here is an official document, and every extracted value remains a
review candidate rather than a published fact.
"""
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from bdt.documents import candidates, inspect_pdf, ocr_eligible


def _native_roles_pdf(path: Path) -> None:
    page = canvas.Canvas(str(path), pagesize=letter)
    page.drawString(72, 720, "CONVENIO N. 123/2025")
    page.drawString(72, 700, "PLANO DE TRABALHO")
    page.drawString(72, 680, "DATA DE ASSINATURA: 01/02/2025")
    page.drawString(72, 660, "DATA DE INICIO: 03/02/2025")
    page.drawString(72, 640, "DATA DE TERMINO: 31/12/2025")
    page.drawString(72, 620, "VALOR DO ADITIVO: R$ 10.000,00")
    page.save()


def _table_pdf(path: Path, headers: list[list[str]]) -> None:
    page = canvas.Canvas(str(path), pagesize=letter)
    for number, header in enumerate(headers, 1):
        data = [header] + [[str(number * 10 + index), f"Item {number}-{index}", "1,00"]
                           for index in range(2)]
        table = Table(data, colWidths=[60, 300, 80])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
        table.wrapOn(page, 500, 700)
        table.drawOn(page, 72, 650)
        page.showPage()
    page.save()


def test_family_and_dates_keep_their_roles(tmp_path):
    path = tmp_path / "synthetic-roles.pdf"
    _native_roles_pdf(path)
    result = inspect_pdf(path)

    family = result["document_family"]
    assert family["primary"] == "agreement"
    assert {item["family"] for item in family["families"]} == {
        "agreement", "work_plan", "amendment",
    }
    assert family["review_required"] is True
    assert family["publication_allowed"] is False

    found = {item["field"]: item for item in result["pages"][0]["candidates"]}
    assert found["signature_date"]["value"] == "2025-02-01"
    assert found["start_date"]["value"] == "2025-02-03"
    assert found["end_date"]["value"] == "2025-12-31"
    assert found["amendment_cents"]["value"] == 1_000_000
    assert all(item["state"] == "candidate" for item in found.values())
    assert all(item["publication_allowed"] is False for item in found.values())


def test_impossible_date_is_visible_but_not_normalized():
    found = candidates("DATA DE ASSINATURA: 31/02/2025")
    item = next(value for value in found if value["field"] == "signature_date")
    assert item["value"] == "31/02/2025"
    assert item["date_valid"] is False
    assert item["state"] == "candidate"
    assert item["publication_allowed"] is False


def test_multipage_table_joins_only_repeated_headers(tmp_path):
    path = tmp_path / "synthetic-table.pdf"
    _table_pdf(path, [
        ["ITEM", "DESCRICAO", "VALOR"],
        ["ITEM", "DESCRICAO", "VALOR"],
        ["OUTRO", "CABECALHO", "VALOR"],
    ])
    result = inspect_pdf(path)

    assert len(result["pages"]) == 3
    assert result["multipage_tables"] == [{
        "pages": [1, 2],
        "header": ["ITEM", "DESCRICAO", "VALOR"],
        "rows": [
            {"page": 1, "cells": ["10", "Item 1-0", "1,00"]},
            {"page": 1, "cells": ["11", "Item 1-1", "1,00"]},
            {"page": 2, "cells": ["20", "Item 2-0", "1,00"]},
            {"page": 2, "cells": ["21", "Item 2-1", "1,00"]},
        ],
        "source": "native_tables",
        "continuation_basis": "repeated_header",
        "review_required": True,
        "publication_allowed": False,
    }]


def test_rotation_metadata_changes_effective_orientation(tmp_path):
    path = tmp_path / "synthetic-rotated.pdf"
    page = canvas.Canvas(str(path), pagesize=letter)
    page.setPageRotation(90)
    page.drawString(72, 720, "CONTRATO N. 45/2024")
    page.save()

    result = inspect_pdf(path)
    assert result["pages"][0]["rotation"] == 90
    assert result["pages"][0]["orientation"] == "landscape"
    assert result["pages"][0]["route"] == "native"
    assert result["pages"][0]["ocr_eligible"] is False


def test_hybrid_page_keeps_native_stamp_and_requires_ocr_review(tmp_path):
    image_path = tmp_path / "scan.png"
    Image.new("RGB", (1000, 1400), "white").save(image_path)
    path = tmp_path / "synthetic-hybrid.pdf"
    page = canvas.Canvas(str(path), pagesize=letter)
    page.drawImage(str(image_path), 20, 20, width=572, height=752)
    page.drawString(72, 720, "CARIMBO DE PROTOCOLO " + "texto " * 60)
    page.save()

    result = inspect_pdf(path)
    extracted = result["pages"][0]
    assert extracted["route"] == "hybrid_review"
    assert extracted["ocr_eligible"] is True
    assert extracted["image_fraction"] > .65
    assert extracted["text_length"] >= 200
    assert extracted["text"].startswith("CARIMBO DE PROTOCOLO")


def test_legacy_ocr_route_remains_eligible_but_blank_does_not():
    assert ocr_eligible({"route": "ocr_candidate"}) is True
    assert ocr_eligible({"route": "native"}) is False
    assert ocr_eligible({"route": "native", "ocr_eligible": True}) is True
    assert ocr_eligible({"route": "ocr_candidate", "ocr_eligible": False}) is False

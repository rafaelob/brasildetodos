# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared helpers and fixtures for Brasil de Todos E2E test suite."""
from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from bdt.api import create_app, password_hash
from bdt.storage import Database, Municipality, Place, User
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
DATA_DB_PATH = PROJECT_ROOT / "data" / "bdt.db"

CSRF_HEADERS = {
    "x-bdt-client": "web",
    "origin": "http://localhost:8000",
}

CSRF_HEADERS_8008 = {
    "x-bdt-client": "web",
    "origin": "http://127.0.0.1:8008",
}

# Standard test users
CONTRIBUTOR_USER = "contributor_e2e"
CONTRIBUTOR_PASS = "ContributorPass123!"
REVIEWER_USER = "reviewer_e2e"
REVIEWER_PASS = "ReviewerPass123!"


def seed_isolated_database(db: Database) -> None:
    """Populate minimal test records required for end-to-end user workflows."""
    db.initialize()
    with db.session() as session:
        # 1. Boa Vista (RR) municipality
        muni = Municipality(
            id="1400100",
            name="Boa Vista",
            state="RR",
            source={"dataset": "ibge", "url": "https://ibge.gov.br", "record_id": "1400100"},
        )
        session.merge(muni)

        # 2. Test School with CNEFE geolocation & provenance
        school_source = {
            "dataset": "inep-schools",
            "url": "https://download.inep.gov.br/censo_escolar/microdados_censo_escolar_2023.zip",
            "record_id": "14001001",
            "reference_date": "2023-12-31",
            "collected_at": "2026-09-06T00:00:00+00:00",
            "snapshot_sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        }
        school = Place(
            id="school:14001001",
            kind="school",
            name="Escola Municipal Teste Boa Vista",
            search_name="escola municipal teste boa vista",
            municipality_id="1400100",
            state="RR",
            latitude=2.8235,
            longitude=-60.6758,
            dataset="inep-schools",
            catalogue_eligible=True,
            payload={
                "id": "school:14001001",
                "kind": "school",
                "name": "Escola Municipal Teste Boa Vista",
                "municipality_id": "1400100",
                "state": "RR",
                "latitude": 2.8235,
                "longitude": -60.6758,
                "geo_source": "synthetic_test_only",
                "declared_services": ["ensino_fundamental"],
                "source": school_source,
            },
            fingerprint="f" * 64,
            updated_at="2026-09-06T00:00:00+00:00",
        )
        session.merge(school)

        # 3. Test Health Facility with official provenance
        health_source = {
            "dataset": "cnes-national-bulk",
            "url": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip",
            "record_id": "9999991",
            "reference_date": None,
            "collected_at": "2026-09-06T00:00:00+00:00",
            "snapshot_sha256": "c1d2e3f4a5b6c1d2e3f4a5b6c1d2e3f4a5b6c1d2e3f4a5b6c1d2e3f4a5b6c1d2",
        }
        health = Place(
            id="health:9999991",
            kind="health",
            name="Unidade Basica de Saude Teste",
            search_name="unidade basica de saude teste",
            municipality_id="1400100",
            state="RR",
            latitude=2.8200,
            longitude=-60.6700,
            dataset="cnes-national-bulk",
            catalogue_eligible=True,
            payload={
                "id": "health:9999991",
                "kind": "health",
                "name": "Unidade Basica de Saude Teste",
                "municipality_id": "1400100",
                "state": "RR",
                "latitude": 2.8200,
                "longitude": -60.6700,
                "geo_source": "CNES",
                "source": health_source,
            },
            fingerprint="e" * 64,
            updated_at="2026-09-06T00:00:00+00:00",
        )
        session.merge(health)

        # 4. Users: Contributor and Reviewer
        contributor = User(
            username=CONTRIBUTOR_USER,
            password_hash=password_hash(CONTRIBUTOR_PASS),
            role="contributor",
        )
        session.merge(contributor)

        reviewer = User(
            username=REVIEWER_USER,
            password_hash=password_hash(REVIEWER_PASS),
            role="reviewer",
        )
        session.merge(reviewer)
        session.commit()


def get_readonly_client() -> TestClient:
    """Return a TestClient connected to the real production data database if available."""
    if DATA_DB_PATH.exists() and DATA_DB_PATH.stat().st_size > 100000:
        db_url = f"sqlite:///{DATA_DB_PATH}"
    else:
        # Fallback to seeded temp db if data/bdt.db is missing
        tmp = os.path.join(tempfile.gettempdir(), "bdt_e2e_ro_fallback.db")
        db = Database(f"sqlite:///{tmp}")
        seed_isolated_database(db)
        db_url = f"sqlite:///{tmp}"

    app = create_app(db_url, testing=True)
    return TestClient(app, raise_server_exceptions=False)


def get_isolated_client() -> tuple[TestClient, str]:
    """Create a completely isolated temporary database and client for write tests."""
    fd, path = tempfile.mkstemp(prefix="bdt_e2e_mut_", suffix=".db")
    os.close(fd)
    db = Database(f"sqlite:///{path}")
    seed_isolated_database(db)
    app = create_app(f"sqlite:///{path}", testing=True)
    client = TestClient(app, raise_server_exceptions=False)
    return client, path


def get_auth_client(role: str = "contributor", client: TestClient | None = None) -> TestClient:
    """Return a TestClient with an authenticated session cookie for the requested role."""
    if client is None:
        client, _ = get_isolated_client()

    username = CONTRIBUTOR_USER if role == "contributor" else REVIEWER_USER
    password = CONTRIBUTOR_PASS if role == "contributor" else REVIEWER_PASS

    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
    return client


def calculate_wcag_contrast(hex1: str, hex2: str) -> float:
    """Calculate the WCAG 2.1 contrast ratio between two hex color codes."""
    def parse_hex(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def srgb_to_linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    def rel_lum(r: int, g: int, b: int) -> float:
        return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)

    r1, g1, b1 = parse_hex(hex1)
    r2, g2, b2 = parse_hex(hex2)
    l1 = rel_lum(r1, g1, b1)
    l2 = rel_lum(r2, g2, b2)
    brightest = max(l1, l2)
    darkest = min(l1, l2)
    return (brightest + 0.05) / (darkest + 0.05)


def parse_svg_elements(svg_text: str) -> dict[str, Any]:
    """Parse SVG content and extract structure, tags, colors, and security attributes."""
    root = ET.fromstring(svg_text)
    tags = [elem.tag.split("}")[-1] for elem in root.iter()]
    colors = set(re.findall(r"#[0-9a-fA-F]{3,8}", svg_text))
    return {
        "tag": root.tag.split("}")[-1],
        "viewBox": root.attrib.get("viewBox", ""),
        "width": root.attrib.get("width", ""),
        "height": root.attrib.get("height", ""),
        "has_scripts": "script" in tags or "onload" in svg_text.lower(),
        "tags": tags,
        "colors": colors,
    }

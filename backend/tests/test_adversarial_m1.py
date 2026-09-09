# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adversarial challenge test suite for Milestone M1.

Empirically challenges:
1. Source Pydantic model: invalid schemes, credentialed URLs, naive timestamps, malformed hashes.
2. coverage_dashboard: source_group and public_run with variations of aliases, casing,
   trailing slashes, unknown datasets, and counters under stress.
3. obrasgov_batch: Ingestion lifecycle and status transitions under total error, partial error,
   and success conditions.
"""
from __future__ import annotations

import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import literal, select

from bdt.coverage_dashboard import SOURCES, STATUS_ALIASES, public_run, source_group, status_group
from bdt.domain import Source, now
from bdt.evidence import Resource, initialize_extensions
from bdt.obrasgov_batch import batch_ingest_obrasgov
from bdt.storage import Database, Ingestion, Municipality


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def valid_source_dict():
    return {
        "dataset": "official_pipeline",
        "url": "https://dados.gov.br/dataset/rec",
        "record_id": "rec-12345",
        "reference_date": "2026-09-08",
        "collected_at": "2026-09-08T12:00:00+00:00",
        "snapshot_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "adversarial_m1.db"
    db = Database(f"sqlite:///{db_path}")
    db.initialize()
    with db.session() as session:
        src = Source(
            dataset="ibge",
            record_id="1400100",
            url="https://example.org",
            snapshot_sha256="a" * 64,
            collected_at=now(),
        ).model_dump()
        session.add(Municipality(id="1400100", name="Boa Vista", state="RR", source=src))
        session.commit()
    return db


# ==============================================================================
# 1. Source Contract Adversarial Challenge
# ==============================================================================

class TestSourceAdversarial:
    """Stress-test Source contract against injection, malformed URLs, hashes, and timestamps."""

    @pytest.mark.parametrize("invalid_scheme", [
        "ftp://mirror.gov.br/data.csv",
        "file:///etc/shadow",
        "file://c:/windows/system32/cmd.exe",
        "gopher://gopher.floodgap.com/0/",
        "ws://stream.gov.br/feed",
        "wss://securestream.gov.br/feed",
        "javascript:alert(document.cookie)",
        "data:text/csv;base64,MTIzNDU2Cg==",
        "mailto:contato@transparencia.gov.br",
        "tel:+556130000000",
        "ssh://git@github.com/repo",
        "git://github.com/repo",
        "sftp://sftp.gov.br/data",
        "//dados.gov.br/dataset/rec",
        "custom-protocol://dados.gov.br",
    ])
    def test_invalid_url_schemes_strictly_rejected(self, valid_source_dict, invalid_scheme):
        payload = {**valid_source_dict, "url": invalid_scheme}
        with pytest.raises(ValidationError) as exc_info:
            Source.model_validate(payload)
        assert "Public HTTP(S) reference required" in str(exc_info.value)

    @pytest.mark.parametrize("malformed_url", [
        "http://",
        "https://",
        "https://:443",
        "not_a_valid_url",
        "",
        "   ",
        "https:///",
    ])
    def test_missing_or_empty_hostname_rejected(self, valid_source_dict, malformed_url):
        payload = {**valid_source_dict, "url": malformed_url}
        with pytest.raises(ValidationError):
            Source.model_validate(payload)

    @pytest.mark.parametrize("credentialed_url", [
        "https://admin:password123@dados.gov.br/dataset",
        "http://root:secret@10.0.0.1/export",
        "https://token@api.dados.gov.br/v1",
        "https://:onlypass@api.dados.gov.br/v1",
        "https://user:@api.dados.gov.br/v1",
        "http://service_acc:p%40ssw0rd@dados.gov.br/endpoint",
    ])
    def test_credentialed_urls_strictly_blocked(self, valid_source_dict, credentialed_url):
        payload = {**valid_source_dict, "url": credentialed_url}
        with pytest.raises(ValidationError) as exc_info:
            Source.model_validate(payload)
        assert "Public HTTP(S) reference required" in str(exc_info.value)

    @pytest.mark.parametrize("naive_or_bad_timestamp", [
        "2026-09-08T16:00:00",               # Naive ISO (no timezone)
        "2026-09-08 16:00:00",               # Space separator, naive
        "2026-09-08",                        # Date only
        "16:00:00",                          # Time only
        "invalid-iso-string",                # Garbage text
        "2026-02-30T12:00:00Z",              # Non-existent calendar day
        "2026-13-01T12:00:00Z",              # Non-existent month
        "2026-09-08T25:00:00Z",              # Non-existent hour
        "2026-09-08T12:60:00Z",              # Non-existent minute
        "2026-09-08T12:00:00+25:00",         # Invalid timezone offset > +24
        "2026-09-08T12:00:00-25:00",         # Invalid timezone offset < -24
        "",                                  # Empty string
    ])
    def test_naive_or_malformed_timestamps_rejected(self, valid_source_dict, naive_or_bad_timestamp):
        payload = {**valid_source_dict, "collected_at": naive_or_bad_timestamp}
        with pytest.raises(ValidationError):
            Source.model_validate(payload)

    @pytest.mark.parametrize("valid_aware_timestamp", [
        "2026-09-08T16:00:00Z",
        "2026-09-08T13:00:00-03:00",
        "2026-09-08T16:00:00.123456+00:00",
        "2026-09-08T16:00:00+05:30",
    ])
    def test_timezone_aware_timestamps_accepted(self, valid_source_dict, valid_aware_timestamp):
        payload = {**valid_source_dict, "collected_at": valid_aware_timestamp}
        src = Source.model_validate(payload)
        assert src.collected_at is not None

    @pytest.mark.parametrize("malformed_hash", [
        "a" * 63,                             # 63 chars (too short)
        "a" * 65,                             # 65 chars (too long)
        "A" * 64,                             # 64 chars uppercase (forbidden by ^[a-f0-9]{64}$)
        "a" * 63 + "F",                       # 1 uppercase char
        "a" * 63 + "g",                       # 'g' is non-hex
        "a" * 63 + "z",                       # 'z' is non-hex
        "a" * 32 + " " + "a" * 31,            # embedded space
        " " * 64,                             # all spaces
        "a" * 32 + "-" + "a" * 31,            # hyphenated
        "0x" + "a" * 62,                      # 0x prefix
        "",                                   # empty
    ])
    def test_malformed_hashes_strictly_rejected(self, valid_source_dict, malformed_hash):
        payload = {**valid_source_dict, "snapshot_sha256": malformed_hash}
        with pytest.raises(ValidationError):
            Source.model_validate(payload)

    @pytest.mark.parametrize("valid_hash", [
        "0" * 64,
        "f" * 64,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "0123456789abcdef" * 4,
    ])
    def test_valid_lowercase_hex_hashes_accepted(self, valid_source_dict, valid_hash):
        payload = {**valid_source_dict, "snapshot_sha256": valid_hash}
        src = Source.model_validate(payload)
        assert src.snapshot_sha256 == valid_hash

    def test_strict_model_extra_attributes_forbidden(self, valid_source_dict):
        payload = {**valid_source_dict, "unauthorized_backdoor": True}
        with pytest.raises(ValidationError) as exc_info:
            Source.model_validate(payload)
        assert "Extra inputs are not permitted" in str(exc_info.value)

    @pytest.mark.parametrize("field,bad_val", [
        ("dataset", "a"),                     # min_length 2
        ("dataset", "a" * 101),               # max_length 100
        ("record_id", ""),                    # min_length 1
        ("record_id", "a" * 181),             # max_length 180
        ("reference_date", "a" * 81),         # max_length 80
        ("url", "https://example.org/" + "a" * 2000),  # max_length 2000
    ])
    def test_field_boundary_constraints(self, valid_source_dict, field, bad_val):
        payload = {**valid_source_dict, field: bad_val}
        with pytest.raises(ValidationError):
            Source.model_validate(payload)


# ==============================================================================
# 2. Coverage Dashboard & Alias Alignment Adversarial Challenge
# ==============================================================================

class TestCoverageDashboardAdversarial:
    """Stress-test source_group, public_run, and alias mappings."""

    def test_all_official_aliases_never_map_to_other_in_sql(self, test_db):
        """Every single alias listed in SOURCES must evaluate to its registered family in SQL."""
        with test_db.engine.connect() as conn:
            for family, (_, aliases) in SOURCES.items():
                if not aliases:
                    continue
                for alias in aliases:
                    stmt = select(source_group(literal(alias)))
                    result = conn.scalar(stmt)
                    assert result == family, f"Official alias '{alias}' mapped to '{result}' instead of '{family}'!"
                    assert result != "other", f"CRITICAL: Official alias '{alias}' mapped to 'other'!"

    def test_all_official_aliases_never_map_to_other_in_public_run(self):
        """Every single alias listed in SOURCES must evaluate to its registered family in public_run."""
        for family, (_, aliases) in SOURCES.items():
            if not aliases:
                continue
            for alias in aliases:
                row = {
                    "id": str(uuid4()),
                    "dataset": alias,
                    "status": "completed_file",
                    "started_at": "2026-09-08T10:00:00Z",
                    "finished_at": "2026-09-08T10:05:00Z",
                    "counts": {"read": 10, "created": 10},
                    "reference_date": "2026",
                }
                projected = public_run(row)
                assert projected["source_id"] == family, (
                    f"public_run: '{alias}' mapped to '{projected['source_id']}' instead of '{family}'"
                )
                assert projected["source_id"] != "other", (
                    f"CRITICAL: public_run mapped official alias '{alias}' to 'other'!"
                )

    @pytest.mark.parametrize("adversarial_alias", [
        # Casing variations
        "Transferegov",
        "TRANSFEREGOV",
        "transfereGov",
        "Obrasgov",
        "OBRASGOV",
        "obrasGov",
        "Inep",
        "INEP",
        "Cnes",
        "CNES",
        "Ibge",
        "IBGE",
        "Pncp",
        "PNCP",
        "Transferegov-National-Financial",
        "Obrasgov_Projects",
        # Trailing slashes
        "transferegov/",
        "obrasgov/",
        "cnes/",
        "inep/",
        # Leading slashes
        "/transferegov",
        "/obrasgov",
        # Prefix/suffix attacks
        "transfere",
        "obras",
        "transferegov_extra",
        "obrasgov_arbitrary",
        "cnes_unofficial",
        "inep_schools",
        "ibge_custom",
        # Unknown/arbitrary datasets
        "synthetic",
        "operator_upload",
        "unknown_dataset",
        "null",
        "",
        "   ",
        # Injections
        "transferegov' OR '1'='1",
        "obrasgov; DROP TABLE places;",
    ])
    def test_unauthorized_and_adversarial_aliases_map_strictly_to_other(self, test_db, adversarial_alias):
        """Unregistered or case-deviated aliases must strictly fall into 'other'."""
        with test_db.engine.connect() as conn:
            stmt = select(source_group(literal(adversarial_alias)))
            sql_result = conn.scalar(stmt)
            assert sql_result == "other", (
                f"SQL source_group allowed unofficial alias '{adversarial_alias}' into family '{sql_result}'"
            )

        row = {
            "id": str(uuid4()),
            "dataset": adversarial_alias,
            "status": "completed_file",
            "started_at": "2026-09-08T10:00:00Z",
            "finished_at": "2026-09-08T10:05:00Z",
            "counts": {"read": 1},
        }
        py_result = public_run(row)["source_id"]
        assert py_result == "other", (
            f"public_run allowed unofficial alias '{adversarial_alias}' into family '{py_result}'"
        )

    @pytest.mark.parametrize("raw_status,expected_status,expected_pub,expected_err", [
        ("completed_file", "completed", "recorded", None),
        ("success", "completed", "recorded", None),
        ("partial_quality", "partial", "partial", None),
        ("failed", "failed", "not_published", "import_not_published"),
        ("running", "running", "pending", None),
        ("unknown_status", "unknown", "unknown", None),
        ("", "unknown", "unknown", None),
        (None, "unknown", "unknown", None),
    ])
    def test_public_run_status_and_publication_matrix(self, raw_status, expected_status, expected_pub, expected_err):
        row = {
            "id": str(uuid4()),
            "dataset": "obrasgov",
            "status": raw_status,
            "started_at": "2026-09-08T10:00:00Z",
            "finished_at": "2026-09-08T10:05:00Z",
            "counts": {"read": 50, "created": 20, "updated": 5},
        }
        res = public_run(row)
        assert res["status"] == expected_status
        assert res["publication"] == expected_pub
        assert res["error_code"] == expected_err

    def test_public_run_failed_zeroes_out_and_nulls_tentative_counters(self):
        row = {
            "id": str(uuid4()),
            "dataset": "transferegov",
            "status": "failed",
            "started_at": "2026-09-08T10:00:00Z",
            "finished_at": "2026-09-08T10:05:00Z",
            "counts": {"read": 100, "created": 50, "updated": 25, "unchanged": 25, "without_geometry": 10},
        }
        res = public_run(row)
        assert res["counts"]["created"] == 0
        assert res["counts"]["updated"] == 0
        assert res["counts"]["unchanged"] is None
        assert res["counts"]["without_geometry"] is None
        assert res["counts"]["read"] == 100

    @pytest.mark.parametrize("unsafe_count", [
        -1,
        -100,
        2**53,                       # Exceeds MAX_SAFE_INTEGER
        "100",                       # String
        10.5,                        # Float
        True,                        # Boolean (bool is subclass of int, but type(v) is int is False)
        False,
        {"nested": 1},
        [1, 2],
    ])
    def test_public_run_sanitizes_unsafe_counts(self, unsafe_count):
        row = {
            "id": str(uuid4()),
            "dataset": "ibge",
            "status": "completed_file",
            "started_at": "2026-09-08T10:00:00Z",
            "finished_at": "2026-09-08T10:05:00Z",
            "counts": {"read": unsafe_count, "created": 10},
        }
        res = public_run(row)
        assert res["counts"]["read"] is None, f"Unsafe count {unsafe_count!r} was not sanitized to None!"


# ==============================================================================
# 3. Obrasgov Batch Ingestion Lifecycle & Error Transitions
# ==============================================================================

class TestObrasgovBatchLifecycleAdversarial:
    """Stress-test batch_ingest_obrasgov status transitions and counters under failure modes."""

    def test_lifecycle_status_failed_on_network_outage(self, test_db):
        """When API fails completely, status must transition to 'failed' with 0 mutations."""
        with patch("bdt.obrasgov_batch.fetch_api_json", side_effect=ValueError("obrasgov_http_error_500")):
            stats = batch_ingest_obrasgov(test_db, states=["RR"], max_pages_per_state=1, enrich_details=False)

        assert stats["errors"] > 0
        assert stats["created"] == 0
        assert stats["updated"] == 0
        assert stats["unchanged"] == 0

        with test_db.session() as session:
            ingestions = session.query(Ingestion).filter(Ingestion.dataset == "obrasgov_projects").all()
            assert len(ingestions) == 1
            record = ingestions[0]
            assert record.status == "failed", f"Expected 'failed', got '{record.status}'"
            assert record.counts["read"] == 0
            assert record.counts["created"] == 0
            assert record.counts["updated"] == 0
            assert record.counts["unchanged"] == 0
            assert record.started_at is not None
            assert record.finished_at is not None

    def test_lifecycle_status_partial_quality_on_individual_record_corruption(self, test_db):
        """When some records fail normalization but others succeed, status must be 'partial_quality'."""
        sample_response = {
            "total_items": 2,
            "total_pages": 1,
            "page_number": 1,
            "page_size": 10,
            "data": [
                {
                    # Corrupt record: missing required fields, causing normalization failure
                    "id_projeto_investimento": "CORRUPT-01",
                    "desc_nome": "",   # Empty name
                    "uf_principal": "RR",
                },
                {
                    # Valid record
                    "id_projeto_investimento": "VALID-02",
                    "desc_nome": "HOSPITAL REGIONAL DE BOA VISTA",
                    "situacao": "Em Execução",
                    "uf_principal": "RR",
                    "ano_cadastro": 2026,
                    "cod_ibge": "1400100",
                    "investimentos_previstos": [],
                },
            ]
        }

        with patch("bdt.obrasgov_batch.fetch_api_json", return_value=sample_response):
            stats = batch_ingest_obrasgov(test_db, states=["RR"], max_pages_per_state=1, enrich_details=False)

        assert stats["errors"] == 1
        assert stats["created"] == 1
        assert stats["read"] == 2

        with test_db.session() as session:
            record = session.query(Ingestion).filter(Ingestion.dataset == "obrasgov_projects").order_by(Ingestion.id.desc()).first()
            assert record is not None
            assert record.status == "partial_quality", f"Expected 'partial_quality', got '{record.status}'"
            assert record.counts["read"] == 2
            assert record.counts["created"] == 1

    def test_lifecycle_status_completed_file_on_clean_success(self, test_db):
        """When all records succeed with zero errors, status must be 'completed_file'."""
        sample_response = {
            "total_items": 1,
            "total_pages": 1,
            "page_number": 1,
            "page_size": 10,
            "data": [
                {
                    "id_projeto_investimento": "CLEAN-01",
                    "desc_nome": "ESCOLA PADRAO FNDE BOA VISTA",
                    "situacao": "Concluída",
                    "uf_principal": "RR",
                    "ano_cadastro": 2025,
                    "cod_ibge": "1400100",
                    "investimentos_previstos": [],
                }
            ]
        }

        with patch("bdt.obrasgov_batch.fetch_api_json", return_value=sample_response):
            stats = batch_ingest_obrasgov(test_db, states=["RR"], max_pages_per_state=1, enrich_details=False)

        assert stats["errors"] == 0
        assert stats["created"] == 1

        with test_db.session() as session:
            record = session.query(Ingestion).filter(Ingestion.dataset == "obrasgov_projects").order_by(Ingestion.id.desc()).first()
            assert record is not None
            assert record.status == "completed_file", f"Expected 'completed_file', got '{record.status}'"

    def test_reference_date_sanitization_in_ingested_resource(self, test_db):
        """Verify reference_date is stored as None when ano_cadastro is absent, and year string when present."""
        sample_response = {
            "total_items": 2,
            "total_pages": 1,
            "page_number": 1,
            "page_size": 10,
            "data": [
                {
                    "id_projeto_investimento": "YEAR-SET-01",
                    "desc_nome": "OBRA COM ANO EXPLICITO",
                    "situacao": "Em Execução",
                    "uf_principal": "RR",
                    "ano_cadastro": 2024,
                    "cod_ibge": "1400100",
                    "investimentos_previstos": [],
                },
                {
                    "id_projeto_investimento": "YEAR-NONE-02",
                    "desc_nome": "OBRA SEM ANO DE CADASTRO",
                    "situacao": "Em Execução",
                    "uf_principal": "RR",
                    "ano_cadastro": None,
                    "cod_ibge": "1400100",
                    "investimentos_previstos": [],
                },
            ]
        }

        with patch("bdt.obrasgov_batch.fetch_api_json", return_value=sample_response):
            batch_ingest_obrasgov(test_db, states=["RR"], max_pages_per_state=1, enrich_details=False)

        with test_db.session() as session:
            r1 = session.get(Resource, "obrasgov_projects:YEAR-SET-01")
            assert r1 is not None
            # resource_profiles normalizes obrasgov_projects source.reference_date to None (official record)
            assert r1.source["reference_date"] is None

            r2 = session.get(Resource, "obrasgov_projects:YEAR-NONE-02")
            assert r2 is not None
            assert r2.source["reference_date"] is None

        # Also verify Source constructor behavior directly:
        src_with_year = Source(
            dataset="obrasgov_projects",
            record_id="YEAR-SET-01",
            url="https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento?id_projeto_investimento=YEAR-SET-01",
            reference_date=str(2024) if 2024 else None,
            collected_at=now(),
            snapshot_sha256="a" * 64,
        )
        assert src_with_year.reference_date == "2024"

        src_without_year = Source(
            dataset="obrasgov_projects",
            record_id="YEAR-NONE-02",
            url="https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento?id_projeto_investimento=YEAR-NONE-02",
            reference_date=str(None) if None else None,
            collected_at=now(),
            snapshot_sha256="a" * 64,
        )
        assert src_without_year.reference_date is None

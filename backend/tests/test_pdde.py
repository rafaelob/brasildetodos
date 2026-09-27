"""Testes sintéticos do coletor/importador PDDE Básico; nenhuma rede é usada."""
import gzip
import hashlib
import json

import pytest
from sqlalchemy import func, select

import bdt.pdde as pdde
from bdt.domain import PlaceInput, digest, now
from bdt.pdde import ACCESS_NOTE, DATASET, PddePayment, collect_pdde, import_pdde
from bdt.storage import Ingestion, upsert_place

HEADER = ["AN_EXERCICIO", "SG_UF", "NO_MUNICIPIO", "CO_MUNICIPIO_IBGE", "CO_ESCOLA", "NO_ESCOLA",
          "QT_ALUNOS", "NO_ESFERA_ADM", "NO_REGIAO", "LOCALIZACAO", "CNPJ_UEX", "NO_UEX", "NO_CARGO",
          "DT_INI_VINCULACAO", "DS_PROGRAMA_FNDE", "SG_DESTINACAO", "VL_PAGO_CUSTEIO", "VL_PAGO_CAPITAL",
          "VL_PAGO_TOTAL"]


def payment(*, exercise="2025", state="BA", municipality="São Gonçalo", ibge="1234567",
            school="12345678", school_name="Escola Municipal São João", students="120",
            sphere="ADMINISTRAÇÃO PÚBLICA MUNICIPAL", region="NORDESTE", location="URBANA",
            cnpj="12345678000199", recipient="Prefeitura Municipal de São Gonçalo", role="PREFEITO(A)",
            start="2025-03-10", program="PDDE", destinacao="PDDE Basico - 2 Parcela",
            custeio="1.000,00", capital="234,56", total="1.234,56"):
    return {"AN_EXERCICIO": exercise, "SG_UF": state, "NO_MUNICIPIO": municipality,
            "CO_MUNICIPIO_IBGE": ibge, "CO_ESCOLA": school, "NO_ESCOLA": school_name,
            "QT_ALUNOS": students, "NO_ESFERA_ADM": sphere, "NO_REGIAO": region, "LOCALIZACAO": location,
            "CNPJ_UEX": cnpj, "NO_UEX": recipient, "NO_CARGO": role, "DT_INI_VINCULACAO": start,
            "DS_PROGRAMA_FNDE": program, "SG_DESTINACAO": destinacao,
            "VL_PAGO_CUSTEIO": custeio, "VL_PAGO_CAPITAL": capital, "VL_PAGO_TOTAL": total}


def write_manifest(folder, compressed, *, product_id=66):
    manifest = {"dataset": DATASET, "product_id": product_id, "url": pdde.artifact_url(product_id),
                "sha256": hashlib.sha256(compressed).hexdigest(), "bytes": len(compressed),
                "collected_at": now(), "reference_date": None, "access_note": ACCESS_NOTE}
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def write_artifact(folder, rows, *, header=None, product_id=66, encoding="cp1252"):
    columns = header if header is not None else HEADER
    text = ";".join(columns) + "\r\n"
    text += "".join(";".join(str(item.get(name, "")) for name in columns) + "\r\n" for item in rows)
    compressed = gzip.compress(text.encode(encoding))
    (folder / "artifact.gz").write_bytes(compressed)
    return write_manifest(folder, compressed, product_id=product_id)


def test_import_writes_rows_links_and_one_success_ingestion(database, source, tmp_path):
    with database.session() as session:
        upsert_place(session, PlaceInput(id="inep:12345678", kind="school", name="Escola Sintética",
                                         municipality_id="1234567", state="BA", source=source))
    manifest = write_artifact(tmp_path, [
        payment(),
        payment(ibge="9999999", municipality="Cidade Ausente", school="87654321"),
    ])
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["reference_date"] == "2025"
    assert result["exercises"] == ["2025"]
    with database.session() as session:
        stored = {row.school_code: row for row in session.scalars(select(PddePayment))}
        assert set(stored) == {"12345678", "87654321"}
        linked = stored["12345678"]
        assert linked.key == digest(["66", "2025", "12345678", "12345678000199", "2025-03-10", "1.234,56"])
        assert linked.municipality_id == "1234567"
        assert linked.municipality_name == "São Gonçalo"
        assert linked.school_place_id == "inep:12345678"
        assert linked.recipient_cnpj == "12345678000199"
        assert linked.recipient_name == "Prefeitura Municipal de São Gonçalo"
        assert linked.payload["NO_ESCOLA"] == "Escola Municipal São João"
        assert linked.values == {"VL_PAGO_CUSTEIO": "1.000,00", "VL_PAGO_CAPITAL": "234,56",
                                 "VL_PAGO_TOTAL": "1.234,56"}
        assert linked.source == {"url": manifest["url"], "sha256": manifest["sha256"],
                                 "collected_at": manifest["collected_at"], "reference_date": "2025"}
        unlinked = stored["87654321"]
        assert unlinked.municipality_id is None
        assert unlinked.municipality_name == "Cidade Ausente"
        assert unlinked.school_place_id is None
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1
    assert loads[0].status == "success"
    assert loads[0].counts == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert loads[0].source["product_id"] == 66
    assert loads[0].source["reference_date"] == "2025"
    assert loads[0].source["sha256"] == manifest["sha256"]


def test_multiple_exercises_leave_reference_date_open(database, tmp_path):
    write_artifact(tmp_path, [payment(exercise="2025"), payment(exercise="2026")])
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["reference_date"] is None
    assert result["exercises"] == ["2025", "2026"]


def test_malformed_rows_are_rejected_and_counted(database, tmp_path):
    write_artifact(tmp_path, [payment(), payment(exercise="20X5"), payment(school="1234")])
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 3, "created": 1, "unchanged": 0, "rejected": 2}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PddePayment)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts == {"read": 3, "created": 1, "unchanged": 0, "rejected": 2}


def test_reimport_of_identical_bytes_reports_unchanged(database, tmp_path):
    write_artifact(tmp_path, [payment(), payment(school="87654321", ibge="9999999")])
    first = import_pdde(database, tmp_path)
    second = import_pdde(database, tmp_path)
    assert first["counts"]["created"] == 2
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PddePayment)) == 2
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 2


def test_full_row_key_keeps_rows_without_identity_values_distinct(database, tmp_path):
    write_artifact(tmp_path, [
        payment(cnpj="", start="", total=""),
        payment(cnpj="", start="", total="", school_name="Outra Escola Sintética"),
    ])
    first = import_pdde(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PddePayment)) == 2
    second = import_pdde(database, tmp_path)
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}


def test_same_identity_different_parcela_keeps_both_rows(database, tmp_path):
    write_artifact(tmp_path, [payment(destinacao="PDDE Basico - 1 Parcela"),
                              payment(destinacao="PDDE Basico - 2 Parcela")])
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        stored = list(session.scalars(select(PddePayment)))
        assert len({row.key for row in stored}) == 2
        assert {row.payload["SG_DESTINACAO"] for row in stored} == {"PDDE Basico - 1 Parcela",
                                                                    "PDDE Basico - 2 Parcela"}
    again = import_pdde(database, tmp_path)
    assert again["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}


def test_occupied_identity_key_falls_back_to_full_row_hash(database, tmp_path):
    write_artifact(tmp_path, [payment()])
    import_pdde(database, tmp_path)
    write_artifact(tmp_path, [payment(school_name="Outra Escola Sintética")])
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        stored = list(session.scalars(select(PddePayment)))
        assert len({row.key for row in stored}) == 2
        assert sorted(row.payload["NO_ESCOLA"] for row in stored) == ["Escola Municipal São João",
                                                                      "Outra Escola Sintética"]
    again = import_pdde(database, tmp_path)
    assert again["counts"] == {"read": 1, "created": 0, "unchanged": 1, "rejected": 0}


def test_utf8_artifact_preserves_accents(database, tmp_path):
    write_artifact(tmp_path, [payment(school_name="Ação Educativa São João")], encoding="utf-8")
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        stored = session.scalar(select(PddePayment))
        assert stored.payload["NO_ESCOLA"] == "Ação Educativa São João"
        assert stored.payload["NO_MUNICIPIO"] == "São Gonçalo"


def test_undecodable_artifact_is_refused(database, tmp_path):
    compressed = gzip.compress(b"AN_EXERCICIO;CO_ESCOLA\r\n2025;\x81\r\n")
    (tmp_path / "artifact.gz").write_bytes(compressed)
    write_manifest(tmp_path, compressed)
    with pytest.raises(ValueError, match="encoding_unsupported"):
        import_pdde(database, tmp_path)


def test_collect_and_import_round_trip_without_network(database, tmp_path, monkeypatch):
    text = ";".join(HEADER) + "\r\n"
    text += ";".join(str(payment()[name]) for name in HEADER) + "\r\n"
    compressed = gzip.compress(text.encode("cp1252"))

    def fake_download(url, target, max_bytes):
        target.write_bytes(compressed)
        return {"url": url, "sha256": hashlib.sha256(compressed).hexdigest(), "bytes": len(compressed),
                "collected_at": now(), "status_code": 200, "etag": None}

    monkeypatch.setattr(pdde, "safe_download", fake_download)
    collected = collect_pdde(tmp_path, product_id=66)
    assert collected["reference_date"] is None
    assert collected["access_note"] == ACCESS_NOTE
    assert (tmp_path / "collection.json").exists()
    result = import_pdde(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    assert result["reference_date"] == "2025"


def test_gzip_bomb_is_refused(database, tmp_path):
    compressed = gzip.compress(b"A" * (1024 * 1024))
    assert (1024 * 1024) / len(compressed) > pdde.MAX_COMPRESSION_RATIO
    (tmp_path / "artifact.gz").write_bytes(compressed)
    write_manifest(tmp_path, compressed)
    with pytest.raises(ValueError, match="byte_limit"):
        import_pdde(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PddePayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_collect_refuses_another_product_id_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(pdde, "safe_download", lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(json.dumps({"dataset": DATASET, "product_id": 24}), encoding="utf-8")
    with pytest.raises(ValueError, match="product_id"):
        collect_pdde(tmp_path, product_id=66)


def test_header_without_required_columns_is_refused(database, tmp_path):
    columns = [name for name in HEADER if name != "CO_ESCOLA"]
    write_artifact(tmp_path, [payment()], header=columns)
    with pytest.raises(ValueError, match="header"):
        import_pdde(database, tmp_path)


def test_tampered_artifact_is_refused(database, tmp_path):
    write_artifact(tmp_path, [payment()])
    artifact = tmp_path / "artifact.gz"
    artifact.write_bytes(artifact.read_bytes() + b"x")
    with pytest.raises(ValueError, match="artifact_size_mismatch"):
        import_pdde(database, tmp_path)


def test_header_only_artifact_is_refused(database, tmp_path):
    write_artifact(tmp_path, [])
    with pytest.raises(ValueError, match="no_data_rows"):
        import_pdde(database, tmp_path)

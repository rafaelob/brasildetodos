"""Testes sintéticos do coletor/importador SICONFI; nenhuma rede é usada."""
import hashlib
import json
import types
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

import bdt.siconfi as siconfi
from bdt.domain import digest, now
from bdt.siconfi import DATASET, SiconfiReport, collect_siconfi, import_siconfi
from bdt.storage import Ingestion


def rreo_row(**overrides):
    row = {"exercicio": "2024", "demonstrativo": "RREO", "periodo": "3", "periodicidade": "Bimestral",
           "instituicao": "Prefeitura Municipal Sintética", "cod_ibge": "1234567", "uf": "BA",
           "populacao": 100000, "anexo": "RREO-Anexo 01", "esfera": "M",
           "rotulo": "Receita Total", "coluna": "Até o Bimestre", "cod_conta": "1.0.0.0.00.00.00",
           "conta": "Receitas Correntes", "valor": "1.234,56"}
    row.update(overrides)
    return row


def manifest_plan():
    return {"dataset": DATASET, "base_url": siconfi.BASE_URL, "page_size": 5000, "max_pages": 20,
            "queries": [{"dataset": "rreo", "params": {"an_exercicio": "2024"}}]}


def write_collection(folder, *, rreo_pages=(), dca_pages=(), status="complete"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for dataset, pages in (("rreo", rreo_pages), ("dca", dca_pages)):
        for index, items in enumerate(pages):
            page = {"items": list(items), "hasMore": False, "limit": 5000, "offset": 0,
                    "count": len(items), "links": []}
            raw = json.dumps(page, ensure_ascii=False).encode("utf-8")
            directory = folder / dataset
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"page-{index}.json").write_bytes(raw)
            entries.append({"index": index, "dataset": dataset,
                            "url": siconfi.BASE_URL + dataset + "?limit=5000&offset=0",
                            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                            "collected_at": now()})
    plan = manifest_plan()
    manifest = {"dataset": DATASET, "plan": plan, "plan_sha256": digest(plan),
                "started": now(), "finished": now(), "status": status, "pages": entries,
                "queries_incomplete": [], "not_national_coverage": siconfi.NOT_NATIONAL_COVERAGE,
                "license": "ODbL"}
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def write_fake_page(url, target, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"url": url, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "collected_at": now(), "etag": None, "status_code": 200}


def test_import_writes_rows_links_and_one_success_ingestion(database, tmp_path):
    manifest = write_collection(tmp_path, rreo_pages=[[
        rreo_row(),
        rreo_row(cod_ibge="9999999", rotulo="Despesa Total", valor="9.876,54"),
    ]])
    result = import_siconfi(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "complete"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        stored = {row.payload["rotulo"]: row for row in session.scalars(select(SiconfiReport))}
        assert set(stored) == {"Receita Total", "Despesa Total"}
        linked = stored["Receita Total"]
        assert linked.key == digest(["rreo", "1234567", "2024", "3", "RREO-Anexo 01",
                                     "1.0.0.0.00.00.00", "Até o Bimestre", "Receita Total"])
        assert linked.dataset == "rreo"
        assert linked.entity_code == "1234567"
        assert linked.municipality_id == "1234567"
        assert linked.exercise == "2024"
        assert linked.period == "3"
        assert linked.annex == "RREO-Anexo 01"
        assert linked.account_code == "1.0.0.0.00.00.00"
        assert linked.account == "Receitas Correntes"
        assert linked.column_label == "Até o Bimestre"
        assert linked.value_text == "1.234,56"
        assert linked.payload["populacao"] == 100000
        assert linked.source == {"url": manifest["pages"][0]["url"],
                                 "sha256": manifest["pages"][0]["sha256"],
                                 "collected_at": manifest["pages"][0]["collected_at"],
                                 "reference_date": "2024"}
        assert stored["Despesa Total"].municipality_id is None
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1
    assert loads[0].status == "success"
    assert loads[0].counts == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert loads[0].source["manifest_sha256"] == result["manifest_sha256"]


def test_entity_link_requires_seven_digits_present_in_municipalities(database, tmp_path):
    write_collection(tmp_path, rreo_pages=[[
        rreo_row(),
        rreo_row(cod_ibge="5300108", rotulo="R2"),
        rreo_row(cod_ibge="29", rotulo="R3"),
        rreo_row(cod_ibge=1234567, rotulo="R4"),
    ]])
    result = import_siconfi(database, tmp_path)
    assert result["counts"] == {"read": 4, "created": 4, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        links = {row.payload["rotulo"]: row.municipality_id for row in session.scalars(select(SiconfiReport))}
    assert links == {"Receita Total": "1234567", "R2": None, "R3": None, "R4": "1234567"}


def test_malformed_rows_are_rejected_and_counted(database, tmp_path):
    write_collection(tmp_path, rreo_pages=[[
        rreo_row(),
        rreo_row(exercicio="20X4"),
        rreo_row(valor=""),
        rreo_row(cod_ibge="123"),
        rreo_row(rotulo=""),
        {"exercicio": "2024"},
    ]])
    result = import_siconfi(database, tmp_path)
    assert result["counts"] == {"read": 6, "created": 1, "unchanged": 0, "rejected": 5}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
    assert load.status == "success"
    assert load.counts == {"read": 6, "created": 1, "unchanged": 0, "rejected": 5}


def test_reimport_of_identical_pages_is_idempotent(database, tmp_path):
    write_collection(tmp_path, rreo_pages=[[rreo_row(), rreo_row(rotulo="Outra Conta", valor="10,00")]])
    first = import_siconfi(database, tmp_path)
    second = import_siconfi(database, tmp_path)
    assert first["counts"]["created"] == 2
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 2
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 2


def test_collect_refuses_a_different_plan_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(siconfi, "safe_download", lambda *args, **kwargs: pytest.fail("network download attempted"))
    stored_plan = {"dataset": DATASET, "base_url": siconfi.BASE_URL, "page_size": 5000, "max_pages": 20,
                   "queries": [{"dataset": "dca", "params": {"an_exercicio": "2023"}}]}
    (tmp_path / "collection.json").write_text(
        json.dumps({"dataset": DATASET, "plan": stored_plan, "plan_sha256": digest(stored_plan)}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="plan_mismatch"):
        collect_siconfi(tmp_path, rreo=[{"an_exercicio": "2024"}])
    assert not (tmp_path / "rreo").exists()


def test_collect_pagination_complete_and_bounded_without_network(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(siconfi, "time", types.SimpleNamespace(sleep=lambda seconds: sleeps.append(seconds)))

    def complete_download(url, target, *args, **kwargs):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return write_fake_page(url, target, {"items": [rreo_row()], "hasMore": False, "limit": 5000,
                                             "offset": offset, "count": 1, "links": []})

    def bounded_download(url, target, *args, **kwargs):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return write_fake_page(url, target, {"items": [rreo_row()], "hasMore": True, "limit": 5000,
                                             "offset": offset, "count": 1, "links": []})

    monkeypatch.setattr(siconfi, "safe_download", complete_download)
    complete_folder = tmp_path / "complete"
    complete = collect_siconfi(complete_folder, rreo=[{"an_exercicio": "2024", "nr_periodo": "3"}])
    assert complete["status"] == "complete"
    assert len(complete["pages"]) == 1
    assert complete["pages"][0]["dataset"] == "rreo"
    assert (complete_folder / "rreo" / "page-0.json").is_file()
    assert sleeps == []

    monkeypatch.setattr(siconfi, "safe_download", bounded_download)
    bounded_folder = tmp_path / "bounded"
    bounded = collect_siconfi(bounded_folder, rreo=[{"an_exercicio": "2024", "nr_periodo": "3"}], max_pages=2)
    assert bounded["status"] == "bounded"
    assert [page["index"] for page in bounded["pages"]] == [0, 1]
    assert (bounded_folder / "rreo" / "page-1.json").is_file()
    assert sleeps == [1.0]
    assert bounded["queries_incomplete"] == [
        {"dataset": "rreo", "params": {"an_exercicio": "2024", "nr_periodo": "3"}}]
    assert "limit=5000" in bounded["pages"][0]["url"] and "offset=0" in bounded["pages"][0]["url"]


def test_tampered_page_is_refused_and_ingestion_failed(database, tmp_path):
    write_collection(tmp_path, rreo_pages=[[rreo_row()]])
    page = tmp_path / "rreo" / "page-0.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="size_mismatch"):
        import_siconfi(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_same_length_page_tampering_is_refused_by_hash(database, tmp_path):
    # Um byte trocado mantém o tamanho: só a conferência de SHA-256 pode pegar.
    manifest = write_collection(tmp_path, rreo_pages=[[rreo_row()]])
    page = tmp_path / "rreo" / "page-0.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][0]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][0]["sha256"]
    with pytest.raises(ValueError, match="siconfi_page_hash_mismatch"):
        import_siconfi(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_duplicate_manifest_page_is_refused_before_import(database, tmp_path):
    write_collection(tmp_path, rreo_pages=[[rreo_row()]])
    checkpoint = tmp_path / "collection.json"
    manifest = json.loads(checkpoint.read_text(encoding="utf-8"))
    manifest["pages"].append(dict(manifest["pages"][0]))
    checkpoint.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="siconfi_manifest_duplicate_page"):
        import_siconfi(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 0


def test_later_page_hash_mismatch_rolls_back_flushed_rows(database, tmp_path):
    # A primeira página entra em lote (batch_size=1) e a segunda falha; nada pode
    # ficar commitado e a ingestão precisa registrar o retrocesso.
    write_collection(tmp_path, rreo_pages=[[rreo_row()], [rreo_row(rotulo="Segunda Página")]])
    page = tmp_path / "rreo" / "page-1.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    with pytest.raises(ValueError, match="siconfi_page_hash_mismatch"):
        import_siconfi(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_manifest_changed_during_import_rolls_back_flushed_rows(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_collection(tmp_path, rreo_pages=[[rreo_row()]])
    checkpoint = tmp_path / "collection.json"
    flush = siconfi._flush_batch

    def flush_then_change_manifest(session, batch, counts, known_municipalities):
        flush(session, batch, counts, known_municipalities)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(siconfi, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="siconfi_manifest_changed_during_import"):
        import_siconfi(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SiconfiReport)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_no_national_coverage_claim(database, tmp_path):
    manifest = write_collection(tmp_path, rreo_pages=[[rreo_row()]])
    assert "nacional" in manifest["not_national_coverage"]
    result = import_siconfi(database, tmp_path)
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
    assert load.source["collection_status"] == "complete"
    assert load.source["national_catalog_certified"] is False
    assert load.source["not_national_coverage"] == manifest["not_national_coverage"]

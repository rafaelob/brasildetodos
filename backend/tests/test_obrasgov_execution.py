"""Testes sintéticos do coletor/importador de execução física do ObrasGov; nenhuma rede é usada."""
import hashlib
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

import bdt.obrasgov_execution as og
from bdt.domain import digest, now
from bdt.obrasgov_execution import (
    DATASET,
    NOT_NATIONAL_COVERAGE,
    ObrasgovExecution,
    collect_obrasgov_execution,
    import_obrasgov_execution,
    page_url,
)
from bdt.storage import Ingestion

PLAN = {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}


def make_item(execution_id=1, **overrides):
    item = {
        "id_execucao_fisica": execution_id,
        "id_projeto_investimento": "107712.23-56",
        "percentual_execucao_fisica": 42.5,
        "dt_inicial_execucao": "2024-01-10",
        "dt_final_execucao": "2025-06-30",
        "tipo_instrumento": "Contrato",
        "tipo_forma_execucao": "Execução direta",
        "dt_criacao_instrumento": "2023-12-01",
        "dt_cadastro_execucao": "2024-02-15",
        "dt_atualizacao_execucao": "2024-08-01",
        "indicativos": ["INDICATIVO"],
        "motivos": [],
    }
    item.update(overrides)
    return item


def envelope(rows, *, page=1, total_pages=1, total_items=None, page_size=2):
    return {"data": rows, "total_pages": total_pages,
            "total_items": len(rows) if total_items is None else total_items,
            "page_number": page, "page_size": page_size}


def write_pages(folder, pages, *, plan=None, status="complete", terminal="declared_total_pages",
                finished_at=None):
    plan = dict(plan or PLAN)
    pages_dir = folder / "execucao"
    pages_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, payload in enumerate(pages, start=1):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        (pages_dir / f"page-{index}.json").write_bytes(body)
        entries.append({"index": index, "url": page_url(index, plan["page_size"]),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    last = pages[-1] if pages else {"total_pages": 0, "total_items": 0}
    manifest = {"dataset": DATASET, "plan": plan, "started_at": now(),
                "finished_at": finished_at or now(), "status": status, "terminal": terminal,
                "pages": entries, "total_pages": last["total_pages"],
                "total_items": last["total_items"], "not_national_coverage": NOT_NATIONAL_COVERAGE,
                "url": og.API_URL}
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def install_api(monkeypatch, pages):
    calls, sleeps = [], []

    def fake_download(url, target, max_bytes=256 * 1024 * 1024):
        number = int(parse_qs(urlsplit(url).query)["pagina"][0])
        body = json.dumps(pages[number - 1], ensure_ascii=False).encode("utf-8")
        target.write_bytes(body)
        calls.append(url)
        return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                "collected_at": now(), "status_code": 200, "etag": None}

    monkeypatch.setattr(og, "safe_download", fake_download)
    monkeypatch.setattr(og.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def test_collect_complete_writes_pages_and_manifest(tmp_path, monkeypatch):
    pages = [envelope([make_item(1), make_item(2)], page=1, total_pages=2, total_items=3),
             envelope([make_item(3)], page=2, total_pages=2, total_items=3)]
    calls, sleeps = install_api(monkeypatch, pages)
    result = collect_obrasgov_execution(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)
    assert result["status"] == "complete"
    assert result["terminal"] == "declared_total_pages"
    assert [entry["index"] for entry in result["pages"]] == [1, 2]
    assert calls == [page_url(1, 2), page_url(2, 2)]
    assert sleeps == [1.0]
    assert result["total_items"] == 3
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    stored = json.loads((tmp_path / "collection.json").read_text(encoding="utf-8"))
    assert stored["plan"] == {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}
    assert stored["pages"][0]["sha256"] == hashlib.sha256(
        (tmp_path / "execucao" / "page-1.json").read_bytes()).hexdigest()


def test_collect_bounded_at_max_pages_and_short_delay_refused(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope([make_item(1)], page=1, total_pages=3, total_items=4)])
    result = collect_obrasgov_execution(tmp_path, page_size=2, max_pages=1, delay_seconds=1.0)
    assert result["status"] == "bounded"
    assert result["terminal"] == "max_pages_bound"
    assert len(result["pages"]) == 1
    assert len(calls) == 1
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_obrasgov_execution(tmp_path / "other", page_size=2, max_pages=1, delay_seconds=0.5)


def test_collect_refuses_different_plan_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(og, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(json.dumps(
        {"dataset": DATASET, "plan": {"page_size": 100, "max_pages": 10, "delay_seconds": 1.0}}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="plan"):
        collect_obrasgov_execution(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)


def test_import_writes_rows_and_one_success_ingestion(database, tmp_path):
    manifest = write_pages(tmp_path, [
        envelope([make_item(1), make_item(2, percentual_execucao_fisica=0.0)],
                 page=1, total_pages=2, total_items=3),
        envelope([make_item(3, percentual_execucao_fisica=100)], page=2, total_pages=2, total_items=3),
    ])
    result = import_obrasgov_execution(database, tmp_path)
    assert result["status"] == "imported"
    assert result["counts"] == {"read": 3, "created": 3, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "complete"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        rows = {row.execution_id: row for row in session.scalars(select(ObrasgovExecution))}
        assert set(rows) == {1, 2, 3}
        first = rows[1]
        assert first.key == digest([DATASET, 1])
        assert first.project_id == "107712.23-56"
        assert first.percentage == 42.5
        assert (first.starts_on, first.ends_on) == ("2024-01-10", "2025-06-30")
        assert (first.instrument_type, first.execution_form) == ("Contrato", "Execução direta")
        assert (first.created_at_upstream, first.registered_at, first.updated_at_upstream) == (
            "2023-12-01", "2024-02-15", "2024-08-01")
        assert first.indicatives == ["INDICATIVO"]
        assert first.reasons == []
        assert first.payload["id_projeto_investimento"] == "107712.23-56"
        assert first.source == {"url": manifest["pages"][0]["url"],
                                "sha256": manifest["pages"][0]["sha256"],
                                "collected_at": manifest["finished_at"],
                                "reference_date": "2024-02-15"}
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1
    assert loads[0].status == "success"
    assert loads[0].counts == {"read": 3, "created": 3, "unchanged": 0, "rejected": 0}
    assert loads[0].source["collection_status"] == "complete"
    assert loads[0].source["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()


def test_conflicting_row_rolls_back_the_whole_import(database, tmp_path):
    # Mesmo id de execução com percentual diferente: a segunda página conflita e
    # nenhuma linha pode ficar commitada, nem mesmo as da primeira página.
    write_pages(tmp_path, [
        envelope([make_item(1, percentual_execucao_fisica=10.0)], page=1, total_pages=2, total_items=2, page_size=1),
        envelope([make_item(1, percentual_execucao_fisica=20.0)], page=2, total_pages=2, total_items=2, page_size=1),
    ], plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0})
    with pytest.raises(ValueError, match="conflict"):
        import_obrasgov_execution(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert list(session.scalars(select(ObrasgovExecution))) == []
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1 and loads[0].status == "failed"
    assert loads[0].counts.get("rolled_back") is True


def test_accepts_published_timestamp_dates_and_text_indicatives(database, tmp_path):
    # Formas reais do endpoint: carimbos com hora/fração e indicativos/motivos como texto vazio.
    live = make_item(7, dt_inicial_execucao="2025-12-31T00:00:00",
                     dt_final_execucao="2026-12-31T00:00:00",
                     dt_criacao_instrumento="2026-07-28T09:09:39.700999",
                     dt_cadastro_execucao="2026-07-28T09:09:38.454000",
                     dt_atualizacao_execucao="2026-07-28", indicativos="", motivos="")
    write_pages(tmp_path, [envelope([live], page=1, total_pages=1, total_items=1)])
    result = import_obrasgov_execution(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        row = session.scalars(select(ObrasgovExecution)).one()
    assert row.starts_on == "2025-12-31T00:00:00"
    assert row.updated_at_upstream == "2026-07-28"
    assert row.payload["indicativos"] == "" and row.payload["motivos"] == ""


def test_invalid_rows_are_rejected_and_counted(database, tmp_path):
    missing_id = make_item(16)
    missing_id.pop("id_execucao_fisica")
    write_pages(tmp_path, [envelope([
        make_item(10),
        make_item(11, percentual_execucao_fisica=100.5),
        make_item(12, percentual_execucao_fisica=-1),
        make_item(13, percentual_execucao_fisica="42.5"),
        make_item(14, percentual_execucao_fisica=True),
        missing_id,
        make_item(17, id_projeto_investimento=""),
        make_item(18, dt_inicial_execucao="15/01/2024"),
    ], page_size=8)], plan={**PLAN, "page_size": 8})
    result = import_obrasgov_execution(database, tmp_path)
    assert result["counts"] == {"read": 8, "created": 1, "unchanged": 0, "rejected": 7}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["rejected"] == 7


def test_overlong_timestamp_is_rejected_and_counted(database, tmp_path):
    # Carimbo com 86 caracteres é aceito por datetime.fromisoformat, mas não cabe
    # em String(40); a linha é rejeitada e contabilizada sem derrubar o import.
    overlong = "2025-12-31T00:00:00." + "0" * 66
    assert len(overlong) == 86
    assert datetime.fromisoformat(overlong) == datetime(2025, 12, 31, 0, 0)
    write_pages(tmp_path, [envelope([
        make_item(1),
        make_item(2, dt_inicial_execucao=overlong),
    ], page_size=2)])
    result = import_obrasgov_execution(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 1, "unchanged": 0, "rejected": 1}
    with database.session() as session:
        stored = list(session.scalars(select(ObrasgovExecution)))
        assert [row.execution_id for row in stored] == [1]
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["rejected"] == 1


def test_reimport_is_idempotent(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item(1), make_item(2, percentual_execucao_fisica=0.0)])])
    first = import_obrasgov_execution(database, tmp_path)
    second = import_obrasgov_execution(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 2
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
        assert [load.status for load in loads] == ["success", "success"]


def test_tampered_page_is_refused_before_writing_rows(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([make_item(1)])])
    page = tmp_path / "execucao" / "page-1.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity"):
        import_obrasgov_execution(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["read"] == 0
    assert manifest["pages"][0]["sha256"] != hashlib.sha256(page.read_bytes()).hexdigest()


def test_same_length_page_tampering_fails_hash_integrity(database, tmp_path):
    # Um byte trocado mantém o tamanho e não é JSON válido: a falha de integridade
    # só pode vir da conferência de SHA-256, nunca da de tamanho.
    manifest = write_pages(tmp_path, [envelope([make_item(1)])])
    page = tmp_path / "execucao" / "page-1.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][0]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][0]["sha256"]
    with pytest.raises(ValueError, match="obrasgov_execution_page_integrity_failure"):
        import_obrasgov_execution(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["read"] == 0


def test_duplicate_manifest_page_is_refused(database, tmp_path):
    # O mesmo recibo duas vezes quebra a sequência exigida dos índices; todas as
    # páginas são conferidas antes de qualquer linha, então nada é lido nem gravado.
    write_pages(tmp_path, [envelope([make_item(1)])])
    checkpoint = tmp_path / "collection.json"
    manifest = json.loads(checkpoint.read_text(encoding="utf-8"))
    manifest["pages"].append(dict(manifest["pages"][0]))
    checkpoint.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="obrasgov_execution_page_manifest_invalid"):
        import_obrasgov_execution(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["read"] == 0
        assert load.counts["created"] == 0


def test_manifest_changed_during_import_rolls_back_flushed_rows(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_pages(tmp_path, [envelope([make_item(1)])])
    checkpoint = tmp_path / "collection.json"
    flush = og._flush_batch

    def flush_then_change_manifest(session, batch, counts):
        flush(session, batch, counts)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(og, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="obrasgov_execution_manifest_changed_during_import"):
        import_obrasgov_execution(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_complete_status_without_terminal_evidence_is_refused(database, tmp_path):
    # O rótulo complete sem evidência terminal declarada não pode ser aceito.
    write_pages(tmp_path, [envelope([make_item(1)])], status="complete", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="collection_manifest_complete_without_terminal_evidence"):
        import_obrasgov_execution(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovExecution)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 0


def test_bounded_collection_imports_with_partial_status(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item(1), make_item(2)], page=1, total_pages=3, total_items=4)],
                status="bounded", terminal="max_pages_bound")
    result = import_obrasgov_execution(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "bounded"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["collection_status"] == "bounded"
        assert load.source["terminal"] == "max_pages_bound"

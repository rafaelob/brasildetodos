"""Testes sintéticos do coletor/importador de empenhos especiais do Transferegov; nenhuma rede é usada."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

import bdt.transferegov_especiais as te
from bdt.domain import digest, now
from bdt.transferegov_especiais import (
    API_URL,
    DATASET,
    NOT_NATIONAL_COVERAGE,
    TransferegovEspeciaisEmpenho,
    collect_transferegov_especiais,
    import_transferegov_especiais,
    page_url,
)
from bdt.storage import Ingestion

PLAN = {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}


def make_item(empenho_id=1, **overrides):
    item = {
        "id_empenho": empenho_id,
        "id_minuta_empenho": f"minuta-{empenho_id}",
        "numero_empenho": f"2026NE{empenho_id:06d}",
        "situacao_empenho": 1,
        "descricao_situacao_empenho": "Empenhado",
        "tipo_documento_empenho": 1,
        "descricao_tipo_documento_empenho": "Empenho",
        "status_processamento_empenho": "PROCESSADO",
        "ug_responsavel_empenho": 200999,
        "ug_emitente_empenho": 200999,
        "descricao_ug_emitente_empenho": "MINISTERIO SINTETICO",
        "fonte_recurso_empenho": "1000000000",
        "plano_interno_empenho": "2026AA000001",
        "ptres_empenho": 123456,
        "grupo_natureza_despesa_empenho": 3,
        "natureza_despesa_empenho": 30,
        "subitem_empenho": 1,
        "categoria_despesa_empenho": "Custeio",
        "modalidade_despesa_empenho": 90,
        "numero_ro_empenho": None,
        "data_emissao_empenho": "2026-09-27",
        "prioridade_desbloqueio_empenho": 0,
        "valor_empenho": 1234.56,
        "id_plano_acao": 42,
    }
    item.update(overrides)
    return item


def envelope(rows, *, page=1, total_pages=1, total_items=None, page_size=2):
    return {"data": rows, "total_pages": total_pages,
            "total_items": len(rows) if total_items is None else total_items,
            "page_number": page, "page_size": page_size}


def write_pages(folder, pages, *, plan=None, status="complete", terminal="empty_page",
                finished_at=None):
    plan = dict(plan or PLAN)
    pages_dir = folder / "empenhos"
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
                "url": API_URL}
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

    monkeypatch.setattr(te, "safe_download", fake_download)
    monkeypatch.setattr(te.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def test_collect_complete_after_empty_data_page(tmp_path, monkeypatch):
    pages = [envelope([make_item(1), make_item(2)], page=1, total_pages=2, total_items=3),
             envelope([make_item(3)], page=2, total_pages=2, total_items=3),
             envelope([], page=3, total_pages=2, total_items=3, page_size=0)]
    calls, sleeps = install_api(monkeypatch, pages)
    result = collect_transferegov_especiais(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)
    assert result["status"] == "complete"
    assert result["terminal"] == "empty_page"
    assert [entry["index"] for entry in result["pages"]] == [1, 2, 3]
    assert calls == [page_url(1, 2), page_url(2, 2), page_url(3, 2)]
    assert sleeps == [1.0, 1.0]
    assert result["total_items"] == 3
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    stored = json.loads((tmp_path / "collection.json").read_text(encoding="utf-8"))
    assert stored["plan"] == {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}
    assert stored["pages"][0]["sha256"] == hashlib.sha256(
        (tmp_path / "empenhos" / "page-1.json").read_bytes()).hexdigest()


def test_collect_bounded_at_max_pages(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope([make_item(1)], page=1, total_pages=3, total_items=4)])
    result = collect_transferegov_especiais(tmp_path, page_size=2, max_pages=1, delay_seconds=1.0)
    assert result["status"] == "bounded"
    assert result["terminal"] == "max_pages_bound"
    assert len(result["pages"]) == 1
    assert len(calls) == 1


def test_collect_refuses_invalid_options_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    folder = tmp_path / "collect"
    for bad in (0, 201, True, "2"):
        with pytest.raises(ValueError, match="page_size"):
            collect_transferegov_especiais(folder, page_size=bad, max_pages=1, delay_seconds=1.0)
    with pytest.raises(ValueError, match="max_pages"):
        collect_transferegov_especiais(folder, page_size=2, max_pages=0, delay_seconds=1.0)
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_transferegov_especiais(folder, page_size=2, max_pages=1, delay_seconds=0.5)
    assert not folder.exists()


def test_collect_refuses_different_plan_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(json.dumps(
        {"dataset": DATASET, "plan": {"page_size": 100, "max_pages": 10, "delay_seconds": 1.0}}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="plan"):
        collect_transferegov_especiais(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)


def test_collect_unreadable_manifest_is_refused_without_network(tmp_path, monkeypatch):
    # Manifesto ilegível na reutilização da pasta vira erro nomeado, nunca JSONDecodeError cru.
    monkeypatch.setattr(te, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_bytes(b"{not valid json")
    with pytest.raises(ValueError, match="transferegov_especiais_collection_manifest_unreadable"):
        collect_transferegov_especiais(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)


def test_collect_http_error_is_translated_to_value_error(tmp_path, monkeypatch):
    # HTTP da origem vira erro de contrato nomeado, nunca "fim de paginação".
    request = httpx.Request("GET", page_url(1, 2))
    response = httpx.Response(404, request=request, json={"message": "Resource not found"})

    def fake_download(*args, **kwargs):
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(te, "safe_download", fake_download)
    with pytest.raises(ValueError, match="transferegov_especiais_http_error_404"):
        collect_transferegov_especiais(tmp_path, page_size=2, max_pages=5, delay_seconds=1.0)
    assert not (tmp_path / "collection.json").exists()
    assert not (tmp_path / "empenhos" / "page-1.json").exists()


def test_import_writes_rows_and_one_success_ingestion(database, tmp_path):
    manifest = write_pages(tmp_path, [
        envelope([make_item(1), make_item(2, valor_empenho=0.0)],
                 page=1, total_pages=2, total_items=2),
        envelope([], page=2, total_pages=2, total_items=2, page_size=0),
    ])
    result = import_transferegov_especiais(database, tmp_path)
    assert result["status"] == "imported"
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "complete"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        rows = {row.empenho_id: row for row in session.scalars(select(TransferegovEspeciaisEmpenho))}
        assert set(rows) == {1, 2}
        first = rows[1]
        assert first.key == digest([DATASET, 1])
        assert first.minuta_id == "minuta-1"
        assert first.numero_empenho == "2026NE000001"
        assert (first.situacao, first.descricao_situacao) == (1, "Empenhado")
        assert (first.ug_responsavel, first.ug_emitente) == (200999, 200999)
        assert (first.fonte_recurso, first.plano_interno) == ("1000000000", "2026AA000001")
        assert (first.ptres, first.grupo_natureza_despesa, first.natureza_despesa) == (123456, 3, 30)
        assert (first.categoria_despesa, first.modalidade_despesa) == ("Custeio", 90)
        assert (first.data_emissao, first.prioridade_desbloqueio) == ("2026-09-27", 0)
        assert first.valor_empenho == 1234.56
        assert first.id_plano_acao == 42
        assert first.payload["id_minuta_empenho"] == "minuta-1"
        assert first.source == {"url": manifest["pages"][0]["url"],
                                "sha256": manifest["pages"][0]["sha256"],
                                "collected_at": manifest["finished_at"],
                                "reference_date": "2026-09-27"}
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1
    assert loads[0].status == "success"
    assert loads[0].counts == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert loads[0].source["url"] == API_URL
    assert loads[0].source["collected_at"] == manifest["finished_at"]
    assert loads[0].source["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()
    assert loads[0].source["national_catalog_certified"] is False


def test_import_accepts_draft_without_numero_empenho(database, tmp_path):
    draft = make_item(7, numero_empenho=None, numero_ro_empenho=None)
    write_pages(tmp_path, [envelope([draft], page=1, total_pages=1, total_items=1, page_size=1)],
                plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0},
                status="bounded", terminal="max_pages_bound")
    result = import_transferegov_especiais(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        row = session.scalars(select(TransferegovEspeciaisEmpenho)).one()
    assert row.numero_empenho is None
    assert row.payload["numero_empenho"] is None and row.payload["numero_ro_empenho"] is None


def test_conflicting_row_rolls_back_the_whole_import(database, tmp_path):
    # Mesmo id de empenho com valor diferente: a segunda página conflita e nenhuma
    # linha pode ficar commitada, nem mesmo as da primeira página.
    write_pages(tmp_path, [
        envelope([make_item(1, valor_empenho=10.0)], page=1, total_pages=2, total_items=2, page_size=1),
        envelope([make_item(1, valor_empenho=20.0)], page=2, total_pages=2, total_items=2, page_size=1),
    ], plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0},
        status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="conflict"):
        import_transferegov_especiais(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert list(session.scalars(select(TransferegovEspeciaisEmpenho))) == []
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1 and loads[0].status == "failed"
    assert loads[0].counts.get("rolled_back") is True


def test_malformed_rows_are_rejected_and_counted(database, tmp_path):
    missing_id = make_item(16)
    missing_id.pop("id_empenho")
    write_pages(tmp_path, [envelope([
        make_item(10),
        make_item(11, valor_empenho="1234.56"),
        make_item(12, valor_empenho=True),
        make_item(13, data_emissao_empenho="27/09/2026"),
        make_item(14, situacao_empenho="1"),
        make_item(15, id_empenho=True),
        missing_id,
        make_item(17, numero_empenho=123),
        make_item(18, descricao_ug_emitente_empenho="   "),
        make_item(19, id_plano_acao=None),
        make_item(20, valor_empenho=None),
    ], page_size=11)], plan={**PLAN, "page_size": 11},
        status="bounded", terminal="max_pages_bound")
    result = import_transferegov_especiais(database, tmp_path)
    assert result["counts"] == {"read": 11, "created": 1, "unchanged": 0, "rejected": 10}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["rejected"] == 10


def test_reimport_is_idempotent(database, tmp_path):
    write_pages(tmp_path, [
        envelope([make_item(1), make_item(2, valor_empenho=0.0)], page=1, total_pages=2, total_items=2),
        envelope([], page=2, total_pages=2, total_items=2, page_size=0),
    ])
    first = import_transferegov_especiais(database, tmp_path)
    second = import_transferegov_especiais(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 2
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
        assert [load.status for load in loads] == ["success", "success"]


def test_tampered_page_is_refused_before_writing_rows(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([make_item(1)])],
                           status="bounded", terminal="max_pages_bound")
    page = tmp_path / "empenhos" / "page-1.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["read"] == 0
    assert manifest["pages"][0]["sha256"] != hashlib.sha256(page.read_bytes()).hexdigest()


@pytest.mark.parametrize("tampered_url", [page_url(999, 2), page_url(1, 2) + "&extra=1"])
def test_manifest_page_url_must_match_exactly(database, tmp_path, tampered_url):
    # Não basta começar com a URL da API: outra página ou parâmetro extra é recusado.
    write_pages(tmp_path, [envelope([make_item(1)])],
                status="bounded", terminal="max_pages_bound")
    checkpoint = tmp_path / "collection.json"
    manifest = json.loads(checkpoint.read_text(encoding="utf-8"))
    manifest["pages"][0]["url"] = tampered_url
    checkpoint.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="transferegov_especiais_page_url_invalid"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True
        assert load.counts["read"] == 0


def test_multi_page_tamper_is_refused_before_any_write(database, tmp_path):
    # Todas as páginas são conferidas antes de qualquer linha; a página 2 com um
    # byte trocado (mesmo tamanho) derruba o import sem nenhuma gravação parcial.
    manifest = write_pages(tmp_path, [
        envelope([make_item(1)], page=1, total_pages=2, total_items=2, page_size=1),
        envelope([make_item(2)], page=2, total_pages=2, total_items=2, page_size=1),
    ], plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0},
        status="bounded", terminal="max_pages_bound")
    page = tmp_path / "empenhos" / "page-2.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][1]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][1]["sha256"]
    with pytest.raises(ValueError, match="transferegov_especiais_page_integrity_failure"):
        import_transferegov_especiais(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["read"] == 0
        assert load.counts["created"] == 0


def test_manifest_changed_during_import_rolls_back_flushed_rows(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_pages(tmp_path, [envelope([make_item(1)])],
                status="bounded", terminal="max_pages_bound")
    checkpoint = tmp_path / "collection.json"
    flush = te._flush_batch

    def flush_then_change_manifest(session, batch, counts):
        flush(session, batch, counts)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(te, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="transferegov_especiais_manifest_changed_during_import"):
        import_transferegov_especiais(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_envelope_schema_change_is_refused(database, tmp_path):
    bad = envelope([make_item(1)], page=1, total_pages=1, total_items=1)
    bad["data"] = {"not": "a list"}
    write_pages(tmp_path, [bad], status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="schema_changed"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(TransferegovEspeciaisEmpenho)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_html_page_is_refused_before_parsing(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([make_item(1)])],
                           status="bounded", terminal="max_pages_bound")
    page = tmp_path / "empenhos" / "page-1.json"
    body = b"<!DOCTYPE html><html>404</html>"
    page.write_bytes(body)
    manifest["pages"][0]["sha256"] = hashlib.sha256(body).hexdigest()
    manifest["pages"][0]["bytes"] = len(body)
    (tmp_path / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="not_json"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_totals_change_across_pages_is_refused(database, tmp_path):
    write_pages(tmp_path, [
        envelope([make_item(1)], page=1, total_pages=2, total_items=2, page_size=1),
        envelope([make_item(2)], page=2, total_pages=3, total_items=3, page_size=1),
    ], plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0},
        status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="totals_changed"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        assert list(session.scalars(select(TransferegovEspeciaisEmpenho))) == []


def test_complete_manifest_without_empty_terminal_is_refused(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item(1)])])
    with pytest.raises(ValueError, match="terminal_evidence"):
        import_transferegov_especiais(database, tmp_path)
    with database.session() as session:
        assert list(session.scalars(select(TransferegovEspeciaisEmpenho))) == []
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_bounded_collection_imports_with_partial_status(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item(1), make_item(2)], page=1, total_pages=3, total_items=4)],
                status="bounded", terminal="max_pages_bound")
    result = import_transferegov_especiais(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "bounded"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["collection_status"] == "bounded"
        assert load.source["terminal"] == "max_pages_bound"

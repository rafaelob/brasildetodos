"""Testes sintéticos do coletor/importador de atas do PNCP; nenhuma rede é usada."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

import bdt.ingest
import bdt.pncp_atas as atas
from bdt.domain import now
from bdt.pncp_atas import (
    DATASET,
    LICENSE,
    NOT_NATIONAL_COVERAGE,
    PAGES_DIR,
    PncpAta,
    collect_pncp_atas,
    import_pncp_atas,
    page_url,
)
from bdt.storage import Ingestion, Municipality, Place

PLAN = {"window_from": "2023-07-07", "window_to": "2023-07-07", "cnpj": None,
        "page_size": 10, "max_pages": 5, "delay_seconds": 1.0}
CONTROL = "18457226000181-1-000015/2023-000001"


def make_item(control=CONTROL, **overrides):
    item = {
        "numeroControlePNCPAta": control,
        "numeroAtaRegistroPreco": "NPERP 003/2023",
        "anoAta": 2023,
        "numeroControlePNCPCompra": "18457226000181-1-000015/2023",
        "cancelado": False,
        "dataCancelamento": None,
        "dataAssinatura": "2023-06-16",
        "vigenciaInicio": "2023-07-07",
        "vigenciaFim": "2026-10-07",
        "dataPublicacaoPncp": "2023-07-06",
        "dataInclusao": "2023-07-06",
        "dataAtualizacao": "2023-07-06",
        "dataAtualizacaoGlobal": "2023-07-06",
        "usuario": "Licita + Brasil",
        "objetoContratacao": "Serviço de análises técnicas ambientais",
        "cnpjOrgao": "18457226000181",
        "nomeOrgao": "MUNICIPIO DE SANTA VITORIA",
        "cnpjOrgaoSubrogado": None,
        "nomeOrgaoSubrogado": None,
        "codigoUnidadeOrgao": "1",
        "nomeUnidadeOrgao": "MUNICIPIO DE SANTA VITORIA",
        "codigoUnidadeOrgaoSubrogado": None,
        "nomeUnidadeOrgaoSubrogado": None,
        "possibilidadeAdesao": None,
    }
    item.update(overrides)
    return item


def make_items(count, start=1, **overrides):
    return [make_item(f"18457226000181-1-000015/2023-{number:06d}", **overrides)
            for number in range(start, start + count)]


def envelope(rows, *, page=1, total_paginas=1, total_registros=None, page_size=10):
    registros = len(rows) if total_registros is None else total_registros
    return {"data": rows, "totalRegistros": registros, "totalPaginas": total_paginas,
            "numeroPagina": page, "paginasRestantes": total_paginas - page,
            "empty": registros == 0}


def write_pages(folder, pages, *, plan=None, status="complete", terminal="declared_total_pages",
                totals=None, finished_at=None):
    plan = dict(plan or PLAN)
    pages_dir = folder / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, payload in enumerate(pages, start=1):
        body = b"" if payload == "no_content" else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        (pages_dir / f"page-{index}.json").write_bytes(body)
        entries.append({"index": index,
                        "url": page_url(index, plan["window_from"], plan["window_to"],
                                        plan["page_size"], plan["cnpj"]),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    last = pages[-1] if pages else None
    if totals is not None:
        total_registros, total_paginas = totals
    elif isinstance(last, dict):
        total_registros, total_paginas = last["totalRegistros"], last["totalPaginas"]
    else:
        total_registros = total_paginas = 0
    manifest = {"dataset": DATASET, "url": atas.API_URL, "license": LICENSE, "plan": plan,
                "started_at": now(), "finished_at": finished_at or now(), "status": status,
                "terminal": terminal, "pages": entries, "total_registros": total_registros,
                "total_paginas": total_paginas, "not_national_coverage": NOT_NATIONAL_COVERAGE}
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def install_api(monkeypatch, pages):
    calls, sleeps = [], []

    def fake_download(url, target, max_bytes=256 * 1024 * 1024, allow_no_content=False):
        number = int(parse_qs(urlsplit(url).query)["pagina"][0])
        spec = pages[number - 1]
        if spec == "no_content":
            body, status_code = b"", 204
        else:
            body, status_code = json.dumps(spec, ensure_ascii=False).encode("utf-8"), 200
        target.write_bytes(body)
        calls.append(url)
        return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                "collected_at": now(), "status_code": status_code, "etag": None}

    monkeypatch.setattr(atas, "safe_download", fake_download)
    monkeypatch.setattr(atas.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def install_error(monkeypatch, status_code):
    calls = []
    request = httpx.Request("GET", atas.API_URL)

    def fake_download(url, target, max_bytes=256 * 1024 * 1024, allow_no_content=False):
        calls.append(url)
        # Sem corpo legível, como no stream real: só o código sobrevive à tradução.
        response = httpx.Response(status_code, request=request)
        raise httpx.HTTPStatusError("error", request=request, response=response)

    monkeypatch.setattr(atas, "safe_download", fake_download)
    return calls


def valid_plan(**overrides):
    return dict(PLAN) | overrides


def test_collect_complete_writes_pages_and_manifest(tmp_path, monkeypatch):
    pages = [envelope(make_items(10), page=1, total_paginas=2, total_registros=11),
             envelope(make_items(1, start=11), page=2, total_paginas=2, total_registros=11)]
    calls, sleeps = install_api(monkeypatch, pages)
    result = collect_pncp_atas(tmp_path, **valid_plan())
    assert result["status"] == "complete"
    assert result["terminal"] == "declared_total_pages"
    assert [entry["index"] for entry in result["pages"]] == [1, 2]
    assert calls == [page_url(1, "2023-07-07", "2023-07-07", 10),
                     page_url(2, "2023-07-07", "2023-07-07", 10)]
    assert sleeps == [1.0]
    assert (result["total_registros"], result["total_paginas"]) == (11, 2)
    assert result["license"] == LICENSE
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    stored = json.loads((tmp_path / "collection.json").read_text(encoding="utf-8"))
    assert stored["plan"] == PLAN
    assert stored["pages"][0]["sha256"] == hashlib.sha256(
        (tmp_path / PAGES_DIR / "page-1.json").read_bytes()).hexdigest()


def test_collect_never_requests_beyond_declared_total_pages(tmp_path, monkeypatch):
    pages = [envelope(make_items(10), page=1, total_paginas=2, total_registros=11),
             envelope(make_items(1, start=11), page=2, total_paginas=2, total_registros=11)]
    calls, _ = install_api(monkeypatch, pages)
    result = collect_pncp_atas(tmp_path, **valid_plan(max_pages=5))
    assert result["status"] == "complete"
    assert len(calls) == 2


def test_collect_bounded_at_max_pages(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope(make_items(10), total_paginas=3,
                                                   total_registros=21)])
    result = collect_pncp_atas(tmp_path, **valid_plan(max_pages=1))
    assert result["status"] == "bounded"
    assert result["terminal"] == "max_pages_bound"
    assert len(result["pages"]) == 1 and len(calls) == 1


def test_collect_204_is_a_valid_empty_terminal(tmp_path, monkeypatch):
    calls, sleeps = install_api(monkeypatch, ["no_content"])
    result = collect_pncp_atas(tmp_path, **valid_plan())
    assert result["status"] == "complete"
    assert result["terminal"] == "no_content"
    assert (result["total_registros"], result["total_paginas"]) == (0, 0)
    assert calls == [page_url(1, "2023-07-07", "2023-07-07", 10)]
    assert sleeps == []
    assert result["pages"][0]["bytes"] == 0
    assert (tmp_path / PAGES_DIR / "page-1.json").read_bytes() == b""


def test_collect_204_after_declared_totals_is_a_contract_error(tmp_path, monkeypatch):
    pages = [envelope(make_items(10), page=1, total_paginas=2, total_registros=11),
             "no_content"]
    calls, _ = install_api(monkeypatch, pages)
    with pytest.raises(ValueError, match="no_content_after_declared_totals"):
        collect_pncp_atas(tmp_path, **valid_plan())
    assert len(calls) == 2
    assert not (tmp_path / "collection.json").exists()


def test_collect_url_carries_compact_window_and_normalized_cnpj(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope([make_item()])])
    collect_pncp_atas(tmp_path, **valid_plan(window_to="2023-07-10",
                                             cnpj="18.457.226/0001-81", max_pages=1))
    assert calls == [page_url(1, "2023-07-07", "2023-07-10", 10, "18457226000181")]
    assert "dataInicial=20230707" in calls[0] and "cnpj=18457226000181" in calls[0]


def test_collect_refuses_invalid_plan_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(atas, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    with pytest.raises(ValueError, match="365"):
        collect_pncp_atas(tmp_path, **valid_plan(window_to="2024-07-07"))
    with pytest.raises(ValueError, match="10 and 500"):
        collect_pncp_atas(tmp_path, **valid_plan(page_size=9))
    with pytest.raises(ValueError, match="10 and 500"):
        collect_pncp_atas(tmp_path, **valid_plan(page_size=501))
    with pytest.raises(ValueError, match="--from"):
        collect_pncp_atas(tmp_path, **valid_plan(window_from="07/07/2023"))
    with pytest.raises(ValueError, match="after"):
        collect_pncp_atas(tmp_path, **valid_plan(window_from="2023-07-08", window_to="2023-07-07"))
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_pncp_atas(tmp_path, **valid_plan(delay_seconds=0.5))
    with pytest.raises(ValueError, match="max_pages"):
        collect_pncp_atas(tmp_path, **valid_plan(max_pages=0))
    with pytest.raises(ValueError, match="cnpj"):
        collect_pncp_atas(tmp_path, **valid_plan(cnpj="123"))


def test_collect_refuses_different_plan_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(atas, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(json.dumps(
        {"dataset": DATASET, "plan": PLAN | {"page_size": 500}}), encoding="utf-8")
    with pytest.raises(ValueError, match="plan"):
        collect_pncp_atas(tmp_path, **valid_plan())


def test_collect_rejects_envelope_schema_change(tmp_path, monkeypatch):
    missing = envelope([make_item()])
    missing.pop("paginasRestantes")
    install_api(monkeypatch, [missing])
    with pytest.raises(ValueError, match="schema"):
        collect_pncp_atas(tmp_path, **valid_plan(max_pages=1))
    wrong_type = envelope([make_item()], total_paginas=1, total_registros=1)
    wrong_type["empty"] = "false"
    install_api(monkeypatch, [wrong_type])
    with pytest.raises(ValueError, match="schema"):
        collect_pncp_atas(tmp_path / "typed", **valid_plan(max_pages=1))


def test_collect_rejects_inconsistent_envelope_arithmetic(tmp_path, monkeypatch):
    install_api(monkeypatch, [envelope([make_item()], total_paginas=2, total_registros=1)])
    with pytest.raises(ValueError, match="totals"):
        collect_pncp_atas(tmp_path, **valid_plan(max_pages=1))


def test_http_400_beyond_last_page_is_a_contract_error_never_retried(tmp_path, monkeypatch):
    calls = []
    request = httpx.Request("GET", atas.API_URL)
    page_one = json.dumps(envelope(make_items(10), total_paginas=2, total_registros=11),
                          ensure_ascii=False).encode("utf-8")

    def fake_download(url, target, max_bytes=256 * 1024 * 1024, allow_no_content=False):
        number = int(parse_qs(urlsplit(url).query)["pagina"][0])
        calls.append(url)
        if number == 1:
            target.write_bytes(page_one)
            return {"url": url, "sha256": hashlib.sha256(page_one).hexdigest(),
                    "bytes": len(page_one), "collected_at": now(), "status_code": 200,
                    "etag": None}
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("error", request=request, response=response)

    monkeypatch.setattr(atas, "safe_download", fake_download)
    monkeypatch.setattr(atas.time, "sleep", lambda seconds: None)
    with pytest.raises(ValueError) as error:
        collect_pncp_atas(tmp_path, **valid_plan())
    assert str(error.value) == "pncp_atas_contract_error_http_400"
    assert len(calls) == 2
    assert not (tmp_path / "collection.json").exists()
    assert not (tmp_path / PAGES_DIR / "page-2.json").exists()


def test_http_422_is_translated_to_a_contract_error(tmp_path, monkeypatch):
    calls = install_error(monkeypatch, 422)
    with pytest.raises(ValueError) as error:
        collect_pncp_atas(tmp_path, **valid_plan())
    assert str(error.value) == "pncp_atas_contract_error_http_422"
    assert len(calls) == 1


def test_import_writes_typed_rows_and_one_success_ingestion(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([
        make_item(),
        make_item("18457226000181-1-000015/2023-000002", cancelado=True,
                  dataCancelamento="2024-01-10", possibilidadeAdesao=True,
                  cnpjOrgaoSubrogado="00000000000191", nomeOrgaoSubrogado="ORGAO SUBROGADO",
                  codigoUnidadeOrgaoSubrogado="99", nomeUnidadeOrgaoSubrogado="UNIDADE SUBROGADA"),
    ], total_paginas=1, total_registros=2)])
    result = import_pncp_atas(database, tmp_path)
    assert result["status"] == "imported"
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "complete"
    assert result["collection_terminal"] == "declared_total_pages"
    assert result["window"] == {"from": "2023-07-07", "to": "2023-07-07"}
    assert result["cnpj"] is None
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        rows = {row.control: row for row in session.scalars(select(PncpAta))}
        assert set(rows) == {CONTROL, "18457226000181-1-000015/2023-000002"}
        first = rows[CONTROL]
        assert first.key == hashlib.sha256(CONTROL.encode("utf-8")).hexdigest()
        assert first.ata_number == "NPERP 003/2023"
        assert first.compra_control == "18457226000181-1-000015/2023"
        assert first.ano_ata == 2023
        assert first.orgao_cnpj == "18457226000181"
        assert first.orgao_nome == "MUNICIPIO DE SANTA VITORIA"
        assert (first.unit_code, first.unit_name) == ("1", "MUNICIPIO DE SANTA VITORIA")
        assert first.usuario == "Licita + Brasil"
        assert first.objeto_text == "Serviço de análises técnicas ambientais"
        assert first.cancelado is False
        assert first.data_cancelamento is None
        assert first.possibilidade_adesao is None
        assert (first.assinado_em, first.vigencia_inicio, first.vigencia_fim) == (
            "2023-06-16", "2023-07-07", "2026-10-07")
        assert (first.publicado_em, first.incluido_em, first.atualizado_em,
                first.atualizado_global_em) == ("2023-07-06", "2023-07-06", "2023-07-06", "2023-07-06")
        assert first.payload["numeroControlePNCPAta"] == CONTROL
        assert first.source == {"url": manifest["pages"][0]["url"],
                                "sha256": manifest["pages"][0]["sha256"],
                                "collected_at": manifest["finished_at"]}
        second = rows["18457226000181-1-000015/2023-000002"]
        assert second.cancelado is True and second.data_cancelamento == "2024-01-10"
        assert second.possibilidade_adesao is True
        assert second.orgao_cnpj_subrogado == "00000000000191"
        assert second.orgao_nome_subrogado == "ORGAO SUBROGADO"
        assert second.unit_code_subrogado == "99" and second.unit_name_subrogado == "UNIDADE SUBROGADA"
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1 and loads[0].status == "success"
    assert loads[0].counts == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert loads[0].source["collection_status"] == "complete"
    assert loads[0].source["terminal"] == "declared_total_pages"
    assert loads[0].source["collected_at"] == manifest["finished_at"]
    assert loads[0].source["window"] == {"from": "2023-07-07", "to": "2023-07-07"}
    assert loads[0].source["license"] == LICENSE
    assert loads[0].source["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()
    assert loads[0].source["national_catalog_certified"] is False


def test_import_is_idempotent(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item(), make_item("18457226000181-1-000015/2023-000002")])])
    first = import_pncp_atas(database, tmp_path)
    second = import_pncp_atas(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 2
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
        assert [load.status for load in loads] == ["success", "success"]


def test_import_rejects_rows_missing_ata_control_and_counts(database, tmp_path):
    write_pages(tmp_path, [envelope([
        make_item(),
        make_item(None),
        make_item("   "),
        make_item(123),
        make_item("18457226000181-1-000015/2023-000003", anoAta="2023"),
        make_item("18457226000181-1-000015/2023-000004", dataAssinatura="16/06/2023"),
        make_item("18457226000181-1-000015/2023-000005", possibilidadeAdesao="sim"),
        "não é objeto",
    ], total_registros=8)])
    result = import_pncp_atas(database, tmp_path)
    assert result["counts"] == {"read": 8, "created": 1, "unchanged": 0, "rejected": 7}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success" and load.counts["rejected"] == 7


def test_conflicting_row_rolls_back_the_whole_import(database, tmp_path):
    # Mesmo controle com objeto diferente: a segunda página conflita e nenhuma linha
    # pode ficar commitada, nem mesmo as da primeira página.
    write_pages(tmp_path, [
        envelope(make_items(9) + [make_item(CONTROL, objetoContratacao="PRIMEIRA DESCRIÇÃO")],
                 page=1, total_paginas=2, total_registros=11),
        envelope([make_item(CONTROL, objetoContratacao="DESCRIÇÃO CORRIGIDA")],
                 page=2, total_paginas=2, total_registros=11),
    ])
    with pytest.raises(ValueError, match="conflict"):
        import_pncp_atas(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert list(session.scalars(select(PncpAta))) == []
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1 and loads[0].status == "failed"
    assert loads[0].counts.get("rolled_back") is True


def test_manifest_changed_during_import_rolls_back_everything(database, tmp_path, monkeypatch):
    write_pages(tmp_path, [envelope(make_items(2))])
    original_flush = atas._flush_batch

    def tampering_flush(session, batch, counts):
        original_flush(session, batch, counts)
        (tmp_path / "collection.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(atas, "_flush_batch", tampering_flush)
    with pytest.raises(ValueError, match="manifest_changed_during_import"):
        import_pncp_atas(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True


def test_tampered_page_same_length_is_refused_before_writing_rows(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([make_item()])])
    page = tmp_path / PAGES_DIR / "page-1.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][0]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][0]["sha256"]
    with pytest.raises(ValueError, match="pncp_atas_page_integrity_failure"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True
        assert load.counts["read"] == 0 and load.counts["created"] == 0


def test_empty_204_collection_imports_as_zero_rows(database, tmp_path):
    write_pages(tmp_path, ["no_content"], terminal="no_content")
    result = import_pncp_atas(database, tmp_path)
    assert result["counts"] == {"read": 0, "created": 0, "unchanged": 0, "rejected": 0}
    assert result["collection_terminal"] == "no_content"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["terminal"] == "no_content"


def test_import_rejects_empty_terminal_after_declared_totals(database, tmp_path):
    # Página 1 declara 11 registros / 2 páginas; um 204 na página 2 não pode virar
    # manifesto completo e importar 10 linhas como sucesso.
    write_pages(tmp_path, [
        envelope(make_items(10), page=1, total_paginas=2, total_registros=11),
        "no_content",
    ], status="complete", terminal="no_content", totals=(11, 2))
    with pytest.raises(ValueError, match="no_content_after_declared_totals"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_import_rejects_empty_terminal_with_declared_manifest_totals(database, tmp_path):
    write_pages(tmp_path, ["no_content"], status="complete", terminal="no_content",
                totals=(11, 2))
    with pytest.raises(ValueError, match="no_content_after_declared_totals"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_import_rejects_empty_page_without_terminal_evidence(database, tmp_path):
    # Página de zero bytes só é aceita como terminal 204 completo; um manifesto bounded
    # com corpo vazio não pode virar import silencioso.
    write_pages(tmp_path, ["no_content"], status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="empty_page_without_terminal_evidence"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_complete_without_terminal_evidence_is_refused(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item()])], status="complete", terminal="empty_page")
    with pytest.raises(ValueError, match="complete_without_terminal_evidence"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 0


def test_complete_without_reached_last_page_is_refused(database, tmp_path):
    write_pages(tmp_path, [envelope(make_items(10), total_paginas=3, total_registros=21)],
                status="complete", terminal="declared_total_pages")
    with pytest.raises(ValueError, match="complete_without_terminal_evidence"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_bounded_collection_imports_with_partial_status(database, tmp_path):
    write_pages(tmp_path, [envelope(make_items(10), total_paginas=3, total_registros=21)],
                status="bounded", terminal="max_pages_bound")
    result = import_pncp_atas(database, tmp_path)
    assert result["counts"] == {"read": 10, "created": 10, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "bounded"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["collection_status"] == "bounded"
        assert load.source["terminal"] == "max_pages_bound"


def test_import_rejects_envelope_schema_change(database, tmp_path):
    bad = envelope([make_item()])
    bad.pop("empty")
    write_pages(tmp_path, [bad], status="bounded", terminal="max_pages_bound", totals=(1, 1))
    with pytest.raises(ValueError, match="schema"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_import_rejects_page_totals_changed_across_pages(database, tmp_path):
    write_pages(tmp_path, [
        envelope(make_items(10), page=1, total_paginas=2, total_registros=11),
        envelope(make_items(1, start=11), page=2, total_paginas=3, total_registros=21),
    ], status="bounded", terminal="max_pages_bound", totals=(11, 2))
    with pytest.raises(ValueError, match="totals_changed"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0


def test_duplicate_json_keys_in_page_are_refused(database, tmp_path):
    body = (b'{"data": [], "data": [], "totalRegistros": 0, "totalPaginas": 0, '
            b'"numeroPagina": 1, "paginasRestantes": 0, "empty": true}')
    pages_dir = tmp_path / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "page-1.json").write_bytes(body)
    manifest = {"dataset": DATASET, "url": atas.API_URL, "license": LICENSE, "plan": dict(PLAN),
                "started_at": now(), "finished_at": now(), "status": "bounded",
                "terminal": "max_pages_bound",
                "pages": [{"index": 1,
                           "url": page_url(1, "2023-07-07", "2023-07-07", 10),
                           "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}],
                "total_registros": 0, "total_paginas": 0,
                "not_national_coverage": NOT_NATIONAL_COVERAGE}
    (tmp_path / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_json_key"):
        import_pncp_atas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(PncpAta)) == 0


def test_no_place_or_municipality_link_is_created(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item()])])
    assert import_pncp_atas(database, tmp_path)["counts"]["created"] == 1
    columns = {column.name for column in PncpAta.__table__.columns}
    assert not columns & {"municipality_id", "place_id", "state", "ibge_code", "uf",
                          "supplier_id", "supplier_name", "value", "global_value"}
    assert not list(PncpAta.__table__.foreign_keys)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Place)) == 0
        assert session.scalar(select(func.count()).select_from(Municipality)) == 1


def test_pncp_host_is_in_the_download_allowlist():
    assert "pncp.gov.br" in bdt.ingest.HOSTS

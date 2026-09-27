"""Testes sintéticos do coletor/importador de contratos do Compras.gov.br; nenhuma rede é usada."""
import hashlib
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

import bdt.compras as compras
import bdt.ingest
from bdt.compras import (
    DATASET,
    LICENSE,
    NOT_NATIONAL_COVERAGE,
    PAGES_DIR,
    ComprasContract,
    collect_compras,
    import_compras,
    page_url,
)
from bdt.domain import digest, now
from bdt.storage import Ingestion, Municipality, Place

PLAN = {"orgao": "26000", "window_from": "2025-01-01", "window_to": "2025-12-31",
        "page_size": 10, "max_pages": 5, "delay_seconds": 1.0}


def make_item(numero="00036/2024", **overrides):
    item = {
        "codigoOrgao": "26000",
        "nomeOrgao": "MINISTERIO DA EDUCACAO",
        "codigoUnidadeGestora": "152005",
        "nomeUnidadeGestora": "INSTITUTO NACIONAL DE EDUCACAO DE SURDOS-RJ",
        "numeroContrato": numero,
        "niFornecedor": "88611835001877",
        "nomeRazaoSocialFornecedor": "MARCOPOLO SA",
        "objeto": "AQUISIÇÃO DE UM VEÍCULO TIPO ÔNIBUS TURISMO",
        "dataVigenciaInicial": "2025-01-03T00:00:00",
        "dataVigenciaFinal": "2025-06-01T00:00:00",
        "dataHoraInclusao": "2025-01-03T12:43:51",
        "valorGlobal": 673000.0,
        "numeroControlePncpContrato": "00394445000101-2-000086/2024",
        "contratoExcluido": False,
    }
    item.update(overrides)
    return item


def envelope(rows, *, total_paginas=1, total_registros=None, paginas_restantes=0):
    return {"resultado": rows,
            "totalRegistros": len(rows) if total_registros is None else total_registros,
            "totalPaginas": total_paginas, "paginasRestantes": paginas_restantes}


def write_pages(folder, pages, *, plan=None, status="complete", terminal="no_pages_remaining",
                finished_at=None):
    plan = dict(plan or PLAN)
    pages_dir = folder / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, payload in enumerate(pages, start=1):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        (pages_dir / f"page-{index}.json").write_bytes(body)
        entries.append({"index": index,
                        "url": page_url(index, plan["orgao"], plan["window_from"],
                                        plan["window_to"], plan["page_size"]),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    last = pages[-1] if pages else {"totalRegistros": 0, "totalPaginas": 0}
    manifest = {"dataset": DATASET, "url": compras.API_URL, "license": LICENSE, "plan": plan,
                "started_at": now(), "finished_at": finished_at or now(), "status": status,
                "terminal": terminal, "pages": entries,
                "total_registros": last["totalRegistros"], "total_paginas": last["totalPaginas"],
                "not_national_coverage": NOT_NATIONAL_COVERAGE}
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

    monkeypatch.setattr(compras, "safe_download", fake_download)
    monkeypatch.setattr(compras.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def valid_plan(**overrides):
    return {"orgao": "26000", "window_from": "2025-01-01", "window_to": "2025-12-31",
            "page_size": 10, "max_pages": 5, "delay_seconds": 1.0} | overrides


def test_collect_complete_writes_pages_and_manifest(tmp_path, monkeypatch):
    pages = [envelope([make_item("00036/2024"), make_item("00037/2024")],
                      total_paginas=2, total_registros=3, paginas_restantes=1),
             envelope([make_item("00038/2024")], total_paginas=2, total_registros=3,
                      paginas_restantes=0)]
    calls, sleeps = install_api(monkeypatch, pages)
    result = collect_compras(tmp_path, **valid_plan())
    assert result["status"] == "complete"
    assert result["terminal"] == "no_pages_remaining"
    assert [entry["index"] for entry in result["pages"]] == [1, 2]
    assert calls == [page_url(1, "26000", "2025-01-01", "2025-12-31", 10),
                     page_url(2, "26000", "2025-01-01", "2025-12-31", 10)]
    assert sleeps == [1.0]
    assert result["total_registros"] == 3 and result["total_paginas"] == 2
    assert result["license"] == LICENSE
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    stored = json.loads((tmp_path / "collection.json").read_text(encoding="utf-8"))
    assert stored["plan"] == PLAN
    assert stored["pages"][0]["sha256"] == hashlib.sha256(
        (tmp_path / PAGES_DIR / "page-1.json").read_bytes()).hexdigest()


def test_collect_bounded_at_max_pages_and_empty_page_terminal(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope([make_item("00001/2025")], total_paginas=3,
                                                  total_registros=4, paginas_restantes=2)])
    bounded = collect_compras(tmp_path, **valid_plan(max_pages=1))
    assert bounded["status"] == "bounded"
    assert bounded["terminal"] == "max_pages_bound"
    assert len(bounded["pages"]) == 1 and len(calls) == 1
    install_api(monkeypatch, [envelope([], total_paginas=3, total_registros=2, paginas_restantes=2)])
    empty = collect_compras(tmp_path / "empty", **valid_plan())
    assert empty["status"] == "complete"
    assert empty["terminal"] == "empty_page"


def test_collect_refuses_invalid_plan_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(compras, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    with pytest.raises(ValueError, match="365"):
        collect_compras(tmp_path, **valid_plan(window_to="2026-01-02"))
    with pytest.raises(ValueError, match="10 and 500"):
        collect_compras(tmp_path, **valid_plan(page_size=9))
    with pytest.raises(ValueError, match="10 and 500"):
        collect_compras(tmp_path, **valid_plan(page_size=501))
    with pytest.raises(ValueError, match="--from"):
        collect_compras(tmp_path, **valid_plan(window_from="01/01/2025"))
    with pytest.raises(ValueError, match="orgao"):
        collect_compras(tmp_path, **valid_plan(orgao="   "))
    with pytest.raises(ValueError, match="after"):
        collect_compras(tmp_path, **valid_plan(window_from="2025-12-31", window_to="2025-01-01"))
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_compras(tmp_path, **valid_plan(delay_seconds=0.5))


def test_collect_refuses_different_plan_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(compras, "safe_download",
                        lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(json.dumps(
        {"dataset": DATASET, "plan": PLAN | {"page_size": 500}}), encoding="utf-8")
    with pytest.raises(ValueError, match="plan"):
        collect_compras(tmp_path, **valid_plan())


def test_collect_rejects_envelope_schema_change(tmp_path, monkeypatch):
    install_api(monkeypatch, [{"resultado": [], "totalRegistros": 0, "totalPaginas": 0}])
    with pytest.raises(ValueError, match="schema"):
        collect_compras(tmp_path, **valid_plan(max_pages=1))


def test_http_404_is_a_contract_error_not_missing_page(tmp_path, monkeypatch):
    request = httpx.Request("GET", page_url(1, "26000", "2025-01-01", "2025-12-31", 10))
    response = httpx.Response(404, request=request,
                              json={"statusCode": 404, "message": "Resource not found"})

    def fake_download(*args, **kwargs):
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(compras, "safe_download", fake_download)
    with pytest.raises(ValueError, match="contract_error_http_404"):
        collect_compras(tmp_path, **valid_plan(max_pages=1))
    assert not (tmp_path / "collection.json").exists()
    assert not (tmp_path / PAGES_DIR / "page-1.json").exists()


def test_import_writes_rows_and_one_success_ingestion(database, tmp_path):
    manifest = write_pages(tmp_path, [
        envelope([make_item("00036/2024"), make_item("00037/2024")],
                 total_paginas=2, total_registros=3, paginas_restantes=1),
        envelope([make_item("00038/2024", valorGlobal=None)], total_paginas=2,
                 total_registros=3, paginas_restantes=0),
    ])
    result = import_compras(database, tmp_path)
    assert result["status"] == "imported"
    assert result["counts"] == {"read": 3, "created": 3, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "complete"
    assert result["collection_terminal"] == "no_pages_remaining"
    assert result["orgao"] == "26000"
    assert result["window"] == {"from": "2025-01-01", "to": "2025-12-31"}
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        rows = {row.contract_number: row for row in session.scalars(select(ComprasContract))}
        assert set(rows) == {"00036/2024", "00037/2024", "00038/2024"}
        first = rows["00036/2024"]
        assert first.key == digest([DATASET, "26000", "152005", "00036/2024", "88611835001877"])
        assert first.orgao_code == "26000" and first.unit_code == "152005"
        assert first.supplier_id == "88611835001877"
        assert first.supplier_name == "MARCOPOLO SA"
        assert first.organ_name == "MINISTERIO DA EDUCACAO"
        assert first.unit_name == "INSTITUTO NACIONAL DE EDUCACAO DE SURDOS-RJ"
        assert first.object_text == "AQUISIÇÃO DE UM VEÍCULO TIPO ÔNIBUS TURISMO"
        assert (first.starts_on, first.ends_on) == ("2025-01-03T00:00:00", "2025-06-01T00:00:00")
        assert first.published_at == "2025-01-03T12:43:51"
        assert first.pncp_contract_id == "00394445000101-2-000086/2024"
        assert first.global_value == 673000.0
        assert first.excluded is False
        assert first.payload["objeto"] == "AQUISIÇÃO DE UM VEÍCULO TIPO ÔNIBUS TURISMO"
        assert first.source == {"url": manifest["pages"][0]["url"],
                                "sha256": manifest["pages"][0]["sha256"],
                                "collected_at": manifest["finished_at"]}
        assert rows["00038/2024"].global_value is None
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1
    assert loads[0].status == "success"
    assert loads[0].counts == {"read": 3, "created": 3, "unchanged": 0, "rejected": 0}
    assert loads[0].source["collection_status"] == "complete"
    assert loads[0].source["collected_at"] == manifest["finished_at"]
    assert loads[0].source["window"] == {"from": "2025-01-01", "to": "2025-12-31"}
    assert loads[0].source["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()


def test_accepts_null_end_date_and_optional_payload_fields(database, tmp_path):
    live = make_item("00007/2025", dataVigenciaFinal=None, valorGlobal=None,
                     numeroControlePncpContrato=None, informacoesComplementares=None,
                     dataHoraExclusao=None, unidadesRequisitantes=None)
    write_pages(tmp_path, [envelope([live])])
    result = import_compras(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        row = session.scalars(select(ComprasContract)).one()
    assert row.ends_on is None and row.global_value is None
    assert row.payload["dataVigenciaFinal"] is None


def test_malformed_rows_are_rejected_and_counted(database, tmp_path):
    missing = make_item("00001/2025")
    missing.pop("numeroContrato")
    write_pages(tmp_path, [envelope([
        make_item("00002/2025"),
        missing,
        make_item("00003/2025", niFornecedor="123"),
        make_item("00004/2025", niFornecedor=None),
        make_item("00005/2025", contratoExcluido="sim"),
        make_item("00006/2025", valorGlobal="673000"),
        make_item("00007/2025", dataVigenciaInicial="03/01/2025"),
        "não é objeto",
    ])])
    result = import_compras(database, tmp_path)
    assert result["counts"] == {"read": 8, "created": 1, "unchanged": 0, "rejected": 7}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success" and load.counts["rejected"] == 7


def test_overlong_timestamp_is_rejected_and_counted(database, tmp_path):
    # Carimbo com 86 caracteres é aceito por datetime.fromisoformat, mas não cabe
    # em String(40); a linha é rejeitada e contabilizada sem derrubar o import.
    overlong = "2025-01-03T00:00:00." + "0" * 66
    assert len(overlong) == 86
    assert datetime.fromisoformat(overlong) == datetime(2025, 1, 3, 0, 0)
    write_pages(tmp_path, [envelope([
        make_item("00036/2024"),
        make_item("00037/2024", dataVigenciaInicial=overlong),
    ])])
    result = import_compras(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 1, "unchanged": 0, "rejected": 1}
    with database.session() as session:
        stored = list(session.scalars(select(ComprasContract)))
        assert [row.contract_number for row in stored] == ["00036/2024"]
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["rejected"] == 1


def test_reimport_is_idempotent(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item("00036/2024"), make_item("00037/2024")])])
    first = import_compras(database, tmp_path)
    second = import_compras(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 2
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
        assert [load.status for load in loads] == ["success", "success"]


def test_conflicting_row_rolls_back_the_whole_import(database, tmp_path):
    # Mesmo contrato com objeto diferente: a segunda página conflita e nenhuma linha
    # pode ficar commitada, nem mesmo as da primeira página.
    write_pages(tmp_path, [
        envelope([make_item("00036/2024", objeto="PRIMEIRA DESCRIÇÃO")],
                 total_paginas=2, total_registros=2, paginas_restantes=1),
        envelope([make_item("00036/2024", objeto="DESCRIÇÃO CORRIGIDA")],
                 total_paginas=2, total_registros=2, paginas_restantes=0),
    ])
    with pytest.raises(ValueError, match="conflict"):
        import_compras(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert list(session.scalars(select(ComprasContract))) == []
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert len(loads) == 1 and loads[0].status == "failed"
    assert loads[0].counts.get("rolled_back") is True


def test_tampered_page_is_refused_before_writing_rows(database, tmp_path):
    manifest = write_pages(tmp_path, [envelope([make_item("00036/2024")])])
    page = tmp_path / PAGES_DIR / "page-1.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity"):
        import_compras(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["read"] == 0 and load.counts["rolled_back"] is True
    assert manifest["pages"][0]["sha256"] != hashlib.sha256(page.read_bytes()).hexdigest()


def test_multi_page_tamper_is_refused_before_any_write(database, tmp_path):
    # Todas as páginas são conferidas antes de qualquer linha; a página 2 com um
    # byte trocado (mesmo tamanho) derruba o import sem nenhuma gravação parcial.
    manifest = write_pages(tmp_path, [
        envelope([make_item("00036/2024")], total_paginas=2, total_registros=2, paginas_restantes=1),
        envelope([make_item("00037/2024")], total_paginas=2, total_registros=2, paginas_restantes=0),
    ])
    page = tmp_path / PAGES_DIR / "page-2.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][1]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][1]["sha256"]
    with pytest.raises(ValueError, match="compras_page_integrity_failure"):
        import_compras(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["read"] == 0
        assert load.counts["created"] == 0


def test_manifest_changed_during_import_rolls_back_flushed_rows(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_pages(tmp_path, [envelope([make_item("00036/2024")])])
    checkpoint = tmp_path / "collection.json"
    flush = compras._flush_batch

    def flush_then_change_manifest(session, batch, counts):
        flush(session, batch, counts)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(compras, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="compras_manifest_changed_during_import"):
        import_compras(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_duplicate_json_keys_in_page_are_refused(database, tmp_path):
    body = (b'{"resultado": [], "resultado": [], "totalRegistros": 0, "totalPaginas": 0, '
            b'"paginasRestantes": 0}')
    pages_dir = tmp_path / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "page-1.json").write_bytes(body)
    manifest = {"dataset": DATASET, "url": compras.API_URL, "license": LICENSE, "plan": dict(PLAN),
                "started_at": now(), "finished_at": now(), "status": "complete",
                "terminal": "no_pages_remaining",
                "pages": [{"index": 1, "url": page_url(1, "26000", "2025-01-01", "2025-12-31", 10),
                           "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}],
                "total_registros": 0, "total_paginas": 0,
                "not_national_coverage": NOT_NATIONAL_COVERAGE}
    (tmp_path / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_json_key"):
        import_compras(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 0


def test_import_rejects_envelope_schema_change(database, tmp_path):
    bad = {"resultado": [make_item()], "totalRegistros": 1, "totalPaginas": 1}
    write_pages(tmp_path, [bad], status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="schema"):
        import_compras(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ComprasContract)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_complete_without_end_signal_is_refused(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item("00036/2024")], total_paginas=2,
                                    total_registros=3, paginas_restantes=1)],
                status="complete", terminal="no_pages_remaining")
    with pytest.raises(ValueError, match="terminal"):
        import_compras(database, tmp_path)


def test_bounded_collection_imports_with_partial_status(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item("00036/2024")], total_paginas=3,
                                    total_registros=4, paginas_restantes=2)],
                status="bounded", terminal="max_pages_bound")
    result = import_compras(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "bounded"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["collection_status"] == "bounded"
        assert load.source["terminal"] == "max_pages_bound"


def test_excluded_contracts_are_stored_with_flag(database, tmp_path):
    write_pages(tmp_path, [envelope([
        make_item("00036/2024", contratoExcluido=True, dataHoraExclusao="2025-03-01T10:00:00"),
        make_item("00037/2024"),
    ])])
    result = import_compras(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        excluded = session.scalars(
            select(ComprasContract).where(ComprasContract.excluded.is_(True))).one()
    assert excluded.contract_number == "00036/2024"
    assert excluded.payload["contratoExcluido"] is True
    assert excluded.payload["dataHoraExclusao"] == "2025-03-01T10:00:00"


def test_no_place_or_municipality_link_is_created(database, tmp_path):
    write_pages(tmp_path, [envelope([make_item("00036/2024")])])
    assert import_compras(database, tmp_path)["counts"]["created"] == 1
    columns = {column.name for column in ComprasContract.__table__.columns}
    assert not columns & {"municipality_id", "place_id", "state", "ibge_code", "uf"}
    assert not list(ComprasContract.__table__.foreign_keys)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Place)) == 0
        assert session.scalar(select(func.count()).select_from(Municipality)) == 1


def test_compras_host_is_in_the_download_allowlist():
    # O host do Compras.gov.br não pode desaparecer da allowlist de download.
    assert "dadosabertos.compras.gov.br" in bdt.ingest.HOSTS

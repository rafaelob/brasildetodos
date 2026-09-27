"""Testes sintéticos do coletor/importador do catálogo ObrasGov; nenhuma rede é usada."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

import bdt.obrasgov_catalog as oc
from bdt.domain import digest, now
from bdt.obrasgov_catalog import (
    DATASETS,
    FRESHNESS_URL,
    NOT_NATIONAL_COVERAGE,
    ObrasgovCatalog,
    api_url,
    collect_obrasgov_catalog,
    import_obrasgov_catalog,
    page_url,
)
from bdt.storage import Database, Ingestion, Municipality, Place

PLAN = {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}
FRESHNESS = {"data_ultima_atualizacao": "2026-09-27T00:00:00"}
ROWS = {
    "projeto-investimento": {
        "id_projeto_investimento": "151020.43-16",
        "desc_nome": "IMPLANTACAO UBS",
        "desc_projeto": "IMPLANTACAO UBS",
        "desc_funcao_social": "IMPLANTACAO UBS",
        "desc_meta_global": "IMPLANTACAO UBS",
        "dt_inicial_prevista": "2010-10-28",
        "dt_final_prevista": "2013-12-10",
        "dt_cadastro": "2026-09-17",
        "dt_inicial_efetiva": None,
        "dt_final_efetiva": None,
        "ano_cadastro": 2026,
        "natureza_intervencao": "Obra",
        "id_natureza_intervencao": 2,
        "especie_intervencao": "Construção",
        "id_especie_intervencao": 1,
        "situacao": "Cadastrada",
        "uf_principal": "RS",
        "organizacao_resp": "FUNDO NACIONAL DE SAUDE",
        "cnpj_organizacao_resp": "00530493000171",
        "populacao_beneficiada": None,
        "qtd_empregos_gerados": None,
        "possui_estudo_viabilidade": "NÃO",
        "repassadores": [{"organizacao_repassador": "FUNDO NACIONAL DE SAUDE"}],
        "tomadores": [],
        "executores": [],
        "investimentos_previstos": [],
        "ppas": [],
        "eixos_tipos": [],
        "fotos": [],
        "pins": [{"pin": "POINT (-51.2 -30.0)", "latitude": "-30.0", "longitude": "-51.2"}],
        "areas_restricao": [],
    },
    "geometria": {
        "id_projeto_investimento": "12771.50-00",
        "id_geometria": 1350328,
        "sg_uf": "MS",
        "no_municipio": "Ponta Porã",
        "cod_ibge": 5006606,
        "origem_geometria": "Par de Lat/Long",
    },
    "empenho": {
        "ug_emitente": 560018,
        "id_projeto_investimento": "106859.32-90",
        "programa_trabalho": "236749",
        "plano_interno": "MCID000PAC3",
        "fonte": "1000000000",
        "natureza_despesa": 444042,
        "valor_empenho": 560000.0,
        "nr_empenho": "2026NE000897",
        "credor": None,
        "data_emissao": None,
        "aliquidar": None,
        "liquidado": None,
        "pago": None,
        "rpinscrito": None,
        "rpaliquidar": None,
        "rpaliquidado": None,
        "rppago": None,
    },
    "contrato": {
        "id_projeto_investimento": "424.50-48",
        "id_contrato": 97960,
        "numero_contrato": "00698/2021",
        "vigencia_inicio_contrato": "2021-12-08",
        "vigencia_fim_contrato": "2023-05-31",
        "data_assinatura_contrato": "2021-12-07",
        "data_publicacao_contrato": "2021-12-09",
        "cnpj_fornecedor_contrato": "04.327.690/0001-49",
        "fornecedor_contrato": "CONCRETA CONSTRUCAO E INCORPORACAO LTDA",
        "objeto_contrato": "CONTRATAÇÃO DE SERVIÇO DE TRATAMENTO DE EROSÕES",
        "valor_global_contrato": 123456.78,
        "valor_acumulado_contrato": None,
        "valor_utilizado_pi_contrato": None,
        "valor_incluido_contrato": None,
        "situacao_contrato": None,
        "modalidade_contrato": None,
        "link_transparencia": "https://transparencia.gov.br/contrato/97960",
    },
}


def make_row(dataset, **overrides):
    return dict(ROWS[dataset], **overrides)


def without(row, *keys):
    return {key: value for key, value in row.items() if key not in keys}


def envelope(rows, *, page=1, total_pages=1, total_items=None, page_size=2):
    return {"data": rows, "total_pages": total_pages,
            "total_items": len(rows) if total_items is None else total_items,
            "page_number": page, "page_size": page_size}


def write_pages(folder, dataset, pages, *, plan=None, status="complete",
                terminal="declared_total_pages", finished_at=None, freshness=None):
    plan = dict(plan or PLAN)
    freshness = dict(freshness or FRESHNESS)
    pages_dir = folder / dataset
    pages_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, payload in enumerate(pages, start=1):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        (pages_dir / f"page-{index}.json").write_bytes(body)
        entries.append({"index": index, "url": page_url(dataset, index, plan["page_size"]),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    last = pages[-1] if pages else {"total_pages": 0, "total_items": 0}
    fresh_body = json.dumps(freshness, ensure_ascii=False).encode("utf-8")
    (folder / "freshness.json").write_bytes(fresh_body)
    manifest = {
        "collector": "obrasgov_catalog",
        "dataset": dataset,
        "url": api_url(dataset),
        "plan": plan,
        "started_at": now(),
        "finished_at": finished_at or now(),
        "status": status,
        "terminal": terminal,
        "pages": entries,
        "total_pages": last["total_pages"],
        "total_items": last["total_items"],
        "freshness": {"url": FRESHNESS_URL, "sha256": hashlib.sha256(fresh_body).hexdigest(),
                      "bytes": len(fresh_body),
                      "data_ultima_atualizacao": freshness["data_ultima_atualizacao"]},
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def install_api(monkeypatch, pages, *, freshness=None):
    calls, sleeps = [], []
    freshness = dict(freshness or FRESHNESS)

    def fake_download(url, target, max_bytes=256 * 1024 * 1024, **kwargs):
        path = urlsplit(url).path
        if path.endswith("/data-atualizacao"):
            body = json.dumps(freshness, ensure_ascii=False).encode("utf-8")
        else:
            dataset = path.rsplit("/", 1)[-1]
            number = int(parse_qs(urlsplit(url).query)["pagina"][0])
            body = json.dumps(pages[number - 1], ensure_ascii=False).encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        calls.append(url)
        return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                "collected_at": now(), "status_code": 200, "etag": None}

    monkeypatch.setattr(oc, "safe_download", fake_download)
    monkeypatch.setattr(oc.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def test_urls_stay_on_the_reviewed_host_and_path():
    # A URL absoluta é contrato: /obras duplicado ou host trocado deixa de ser a fonte revisada.
    assert api_url("geometria") == "https://api-publica.obrasgov.gestao.gov.br/obras/geometria"
    assert page_url("contrato", 1, 5) == (
        "https://api-publica.obrasgov.gestao.gov.br/obras/contrato?pagina=1&tamanho_da_pagina=5")
    assert FRESHNESS_URL == "https://api-publica.obrasgov.gestao.gov.br/obras/data-atualizacao"


def test_collect_complete_writes_pages_manifest_and_freshness(tmp_path, monkeypatch):
    pages = [envelope([make_row("geometria"), make_row("geometria", id_geometria=2)],
                      page=1, total_pages=2, total_items=3),
             envelope([make_row("geometria", id_geometria=3)], page=2, total_pages=2, total_items=3)]
    calls, sleeps = install_api(monkeypatch, pages)
    result = collect_obrasgov_catalog(tmp_path, dataset="geometria", page_size=2,
                                      max_pages=5, delay_seconds=1.0)
    assert result["status"] == "complete"
    assert result["terminal"] == "declared_total_pages"
    assert [entry["index"] for entry in result["pages"]] == [1, 2]
    assert calls == [FRESHNESS_URL, page_url("geometria", 1, 2), page_url("geometria", 2, 2)]
    assert sleeps == [1.0]
    assert result["total_pages"] == 2 and result["total_items"] == 3
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    stored = json.loads((tmp_path / "collection.json").read_text(encoding="utf-8"))
    assert stored["dataset"] == "geometria"
    assert stored["plan"] == {"page_size": 2, "max_pages": 5, "delay_seconds": 1.0}
    assert stored["url"] == api_url("geometria")
    assert stored["pages"][0]["sha256"] == hashlib.sha256(
        (tmp_path / "geometria" / "page-1.json").read_bytes()).hexdigest()
    assert stored["freshness"]["data_ultima_atualizacao"] == FRESHNESS["data_ultima_atualizacao"]
    assert stored["freshness"]["sha256"] == hashlib.sha256(
        (tmp_path / "freshness.json").read_bytes()).hexdigest()


def test_collect_empty_page_is_a_complete_terminal(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [envelope([], page=1, total_pages=5, total_items=0)])
    result = collect_obrasgov_catalog(tmp_path, dataset="empenho", page_size=2,
                                      max_pages=5, delay_seconds=1.0)
    assert result["status"] == "complete"
    assert result["terminal"] == "empty_page"
    assert len(result["pages"]) == 1
    assert calls == [FRESHNESS_URL, page_url("empenho", 1, 2)]


def test_collect_empty_page_after_all_declared_items_served_is_complete(tmp_path, monkeypatch):
    # Terminal legítimo: o total declarado (1) já foi servido pela página 1.
    pages = [envelope([make_row("empenho")], page=1, total_pages=2, total_items=1),
             envelope([], page=2, total_pages=2, total_items=1)]
    install_api(monkeypatch, pages)
    result = collect_obrasgov_catalog(tmp_path, dataset="empenho", page_size=2,
                                      max_pages=5, delay_seconds=1.0)
    assert result["status"] == "complete"
    assert result["terminal"] == "empty_page"
    assert [entry["index"] for entry in result["pages"]] == [1, 2]


def test_collect_empty_page_contradicting_declared_totals_is_refused(tmp_path, monkeypatch):
    # Página 2 vazia, mas total_items=2 declara 2 linhas e só 1 foi lida: não é terminal.
    pages = [envelope([make_row("empenho")], page=1, total_pages=2, total_items=2),
             envelope([], page=2, total_pages=2, total_items=2)]
    calls, _ = install_api(monkeypatch, pages)
    with pytest.raises(ValueError, match="obrasgov_catalog_empty_page_contradicts_totals"):
        collect_obrasgov_catalog(tmp_path, dataset="empenho", page_size=2,
                                 max_pages=5, delay_seconds=1.0)
    assert len(calls) == 3
    assert not (tmp_path / "collection.json").exists()


def test_collect_declared_totals_changed_between_pages_is_refused(tmp_path, monkeypatch):
    pages = [envelope([make_row("empenho")], page=1, total_pages=2, total_items=2),
             envelope([make_row("empenho", nr_empenho="2026NE000898")], page=2,
                      total_pages=3, total_items=2)]
    install_api(monkeypatch, pages)
    with pytest.raises(ValueError, match="obrasgov_catalog_page_totals_changed"):
        collect_obrasgov_catalog(tmp_path, dataset="empenho", page_size=2,
                                 max_pages=5, delay_seconds=1.0)
    assert not (tmp_path / "collection.json").exists()


def test_collect_bounded_at_max_pages_and_short_delay_refused(tmp_path, monkeypatch):
    calls, _ = install_api(monkeypatch, [
        envelope([make_row("contrato")], page=1, total_pages=3, total_items=4)])
    result = collect_obrasgov_catalog(tmp_path, dataset="contrato", page_size=2,
                                      max_pages=1, delay_seconds=1.0)
    assert result["status"] == "bounded"
    assert result["terminal"] == "max_pages_bound"
    assert len(result["pages"]) == 1
    assert len(calls) == 2
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_obrasgov_catalog(tmp_path / "other", dataset="contrato", page_size=2,
                                 max_pages=1, delay_seconds=0.5)


def test_collect_refuses_dataset_and_page_size_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="page_size"):
        collect_obrasgov_catalog(tmp_path / "a", dataset="geometria", page_size=201)
    with pytest.raises(ValueError, match="page_size"):
        collect_obrasgov_catalog(tmp_path / "a", dataset="geometria", page_size=0)
    with pytest.raises(ValueError, match="dataset"):
        collect_obrasgov_catalog(tmp_path / "a", dataset="geometrias", page_size=5)
    assert not (tmp_path / "a").exists()


def test_collect_refuses_folder_reuse_with_different_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    existing_plan = {"page_size": 100, "max_pages": 5, "delay_seconds": 1.0}
    write_pages(tmp_path, "geometria", [envelope([make_row("geometria")], page_size=100)],
                plan=existing_plan)
    with pytest.raises(ValueError, match="plan"):
        collect_obrasgov_catalog(tmp_path, dataset="geometria", page_size=2,
                                 max_pages=5, delay_seconds=1.0)
    with pytest.raises(ValueError, match="plan"):
        collect_obrasgov_catalog(tmp_path, dataset="contrato", page_size=100,
                                 max_pages=5, delay_seconds=1.0)


def test_collect_rejects_envelope_schema_change(tmp_path, monkeypatch):
    install_api(monkeypatch, [{"data": {}, "total_pages": 1, "total_items": 0,
                               "page_number": 1, "page_size": 2}])
    with pytest.raises(ValueError, match="obrasgov_catalog_page_(schema_changed|totals_invalid)"):
        collect_obrasgov_catalog(tmp_path, dataset="projeto-investimento", page_size=2,
                                 max_pages=1, delay_seconds=1.0)


def test_import_writes_rows_for_all_datasets_with_deterministic_keys(database, tmp_path):
    rows = {
        "projeto-investimento": [
            make_row("projeto-investimento"),
            make_row("projeto-investimento", id_projeto_investimento="151020.43-17")],
        "geometria": [
            make_row("geometria"), make_row("geometria", id_geometria=1350329)],
        "empenho": [
            make_row("empenho"), make_row("empenho", nr_empenho="2026NE000898")],
        "contrato": [
            make_row("contrato"), make_row("contrato", id_contrato=97961, numero_contrato="00699/2021")],
    }
    for dataset, dataset_rows in rows.items():
        folder = tmp_path / dataset
        write_pages(folder, dataset, [envelope(dataset_rows, page=1, total_pages=1, total_items=2)])
        result = import_obrasgov_catalog(database, folder)
        assert result["dataset"] == dataset
        assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
        assert result["national_catalog_certified"] is False
        assert result["collection_status"] == "complete"
    with database.session() as session:
        stored = {row.key: row for row in session.scalars(select(ObrasgovCatalog))}
        assert len(stored) == 8
        assert stored[digest(["projeto-investimento", "151020.43-16"])].project_id == "151020.43-16"
        assert stored[digest(["projeto-investimento", "151020.43-16"])].ibge_code is None
        geometry = stored[digest(["geometria", "12771.50-00", 1350328])]
        assert geometry.project_id == "12771.50-00"
        assert geometry.ibge_code == "5006606"
        assert geometry.payload["origem_geometria"] == "Par de Lat/Long"
        assert "reference_date" not in geometry.source
        empenho = stored[digest(["empenho", "106859.32-90", 560018, "2026NE000897"])]
        assert empenho.project_id == "106859.32-90"
        assert empenho.payload["valor_empenho"] == 560000.0
        contract = stored[digest(["contrato", 97960])]
        assert contract.project_id == "424.50-48"
        assert contract.payload["cnpj_fornecedor_contrato"] == "04.327.690/0001-49"
        assert contract.payload["valor_global_contrato"] == 123456.78
        loads = {load.dataset: load for load in session.scalars(select(Ingestion))}
        assert set(loads) == {f"obrasgov_catalog_{dataset}" for dataset in DATASETS}
        assert all(load.status == "success" for load in loads.values())
        assert loads["obrasgov_catalog_geometria"].source["freshness"]["data_ultima_atualizacao"] == (
            FRESHNESS["data_ultima_atualizacao"])


def test_geometry_id_repeated_across_projects_keeps_both_rows(database, tmp_path):
    write_pages(tmp_path, "geometria", [envelope([
        make_row("geometria", id_projeto_investimento="12771.50-00"),
        make_row("geometria", id_projeto_investimento="12772.50-00"),
    ])])
    result = import_obrasgov_catalog(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    with database.session() as session:
        keys = {row.key for row in session.scalars(select(ObrasgovCatalog))}
    assert keys == {digest(["geometria", "12771.50-00", 1350328]),
                    digest(["geometria", "12772.50-00", 1350328])}


def test_geometria_rows_missing_natural_id_are_rejected_and_counted(database, tmp_path):
    valid = make_row("geometria")
    write_pages(tmp_path, "geometria", [envelope([
        valid,
        without(valid, "id_geometria"),
        make_row("geometria", id_geometria="1350328"),
        make_row("geometria", id_projeto_investimento=""),
        make_row("geometria", cod_ibge=123),
        make_row("geometria", id_geometria=1350330, cod_ibge=None),
    ], page_size=6)], plan={**PLAN, "page_size": 6})
    result = import_obrasgov_catalog(database, tmp_path)
    assert result["counts"] == {"read": 6, "created": 2, "unchanged": 0, "rejected": 4}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 2
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_geometria"))
        assert load.status == "success"
        assert load.counts["rejected"] == 4


def test_empenho_rows_missing_emitente_or_number_are_rejected(database, tmp_path):
    valid = make_row("empenho")
    write_pages(tmp_path, "empenho", [envelope([
        valid,
        without(valid, "ug_emitente"),
        make_row("empenho", ug_emitente="560018"),
        without(valid, "nr_empenho"),
        make_row("empenho", nr_empenho="   "),
    ], page_size=5)], plan={**PLAN, "page_size": 5})
    result = import_obrasgov_catalog(database, tmp_path)
    assert result["counts"] == {"read": 5, "created": 1, "unchanged": 0, "rejected": 4}


def test_reimport_is_idempotent(database, tmp_path):
    write_pages(tmp_path, "contrato", [envelope([
        make_row("contrato"),
        make_row("contrato", id_contrato=97961, numero_contrato="00699/2021"),
    ])])
    first = import_obrasgov_catalog(database, tmp_path)
    second = import_obrasgov_catalog(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 2
        loads = list(session.scalars(select(Ingestion).where(
            Ingestion.dataset == "obrasgov_catalog_contrato")))
    assert [load.status for load in loads] == ["success", "success"]


def test_conflicting_row_rolls_back_the_whole_import(database, tmp_path):
    # Mesma identidade publicada com cod_ibge diferente: a segunda página conflita e
    # nenhuma linha pode ficar commitada, nem mesmo as da primeira página.
    write_pages(tmp_path, "geometria", [
        envelope([make_row("geometria", cod_ibge=5006606)], page=1, total_pages=2,
                 total_items=2, page_size=1),
        envelope([make_row("geometria", cod_ibge=5006607)], page=2, total_pages=2,
                 total_items=2, page_size=1),
    ], plan={"page_size": 1, "max_pages": 5, "delay_seconds": 1.0})
    with pytest.raises(ValueError, match="conflict"):
        import_obrasgov_catalog(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_geometria"))
    assert load.status == "failed"
    assert load.counts["rolled_back"] is True
    assert load.counts["read"] == 2 and load.counts["created"] == 1


def test_import_accepts_empty_page_after_all_declared_items_served(database, tmp_path):
    # A guarda compara com o que foi lido: total_items=1 servido pela página 1.
    write_pages(tmp_path, "empenho", [
        envelope([make_row("empenho")], page=1, total_pages=2, total_items=1),
        envelope([], page=2, total_pages=2, total_items=1),
    ], terminal="empty_page")
    result = import_obrasgov_catalog(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    assert result["collection_terminal"] == "empty_page"


def test_import_refuses_empty_page_contradicting_declared_totals(database, tmp_path):
    write_pages(tmp_path, "empenho", [
        envelope([make_row("empenho")], page=1, total_pages=2, total_items=2),
        envelope([], page=2, total_pages=2, total_items=2),
    ], terminal="empty_page")
    with pytest.raises(ValueError, match="obrasgov_catalog_empty_page_contradicts_totals"):
        import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_empenho"))
    assert load.status == "failed"
    assert load.counts["rolled_back"] is True


def test_import_refuses_pages_with_changed_declared_totals(database, tmp_path):
    write_pages(tmp_path, "empenho", [
        envelope([make_row("empenho")], page=1, total_pages=2, total_items=2),
        envelope([make_row("empenho", nr_empenho="2026NE000898")], page=2,
                 total_pages=3, total_items=2),
    ], status="bounded", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="obrasgov_catalog_page_totals_changed"):
        import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0


def test_same_length_tamper_fails_hash_integrity(database, tmp_path):
    # Um byte trocado mantém o tamanho e não é JSON válido: a falha de integridade
    # só pode vir da conferência de SHA-256, nunca da de tamanho.
    manifest = write_pages(tmp_path, "contrato", [envelope([make_row("contrato")])])
    page = tmp_path / "contrato" / "page-1.json"
    raw = page.read_bytes()
    page.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert page.stat().st_size == manifest["pages"][0]["bytes"]
    assert hashlib.sha256(page.read_bytes()).hexdigest() != manifest["pages"][0]["sha256"]
    with pytest.raises(ValueError, match="obrasgov_catalog_page_integrity_failure"):
        import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_contrato"))
    assert load.status == "failed"
    assert load.counts["read"] == 0


def test_manifest_changed_during_import_rolls_back_flushed_rows(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_pages(tmp_path, "empenho", [envelope([make_row("empenho")])])
    checkpoint = tmp_path / "collection.json"
    flush = oc._flush_batch

    def flush_then_change_manifest(session, batch, counts):
        flush(session, batch, counts)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(oc, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="obrasgov_catalog_manifest_changed_during_import"):
        import_obrasgov_catalog(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_empenho"))
    assert load.status == "failed"
    assert load.counts["rolled_back"] is True
    assert load.counts["created"] == 1


def test_complete_status_without_terminal_evidence_is_refused(database, tmp_path):
    write_pages(tmp_path, "projeto-investimento", [envelope([make_row("projeto-investimento")])],
                status="complete", terminal="max_pages_bound")
    with pytest.raises(ValueError, match="complete_without_terminal_evidence"):
        import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)) == 0


def test_bounded_collection_imports_with_partial_status(database, tmp_path):
    write_pages(tmp_path, "empenho", [envelope([make_row("empenho")], page=1,
                                               total_pages=3, total_items=4)],
                status="bounded", terminal="max_pages_bound")
    result = import_obrasgov_catalog(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    assert result["collection_status"] == "bounded"
    assert result["collection_terminal"] == "max_pages_bound"
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == "obrasgov_catalog_empenho"))
        assert load.status == "success"
        assert load.source["collection_status"] == "bounded"
        assert load.source["national_catalog_certified"] is False


def test_import_creates_no_municipality_or_place_link(database, tmp_path):
    write_pages(tmp_path, "geometria", [envelope([make_row("geometria")])])
    import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Municipality)) == 1
        assert session.scalar(select(func.count()).select_from(Place)) == 0
        row = session.scalars(select(ObrasgovCatalog)).one()
        assert row.ibge_code == "5006606"
        assert row.payload["cod_ibge"] == 5006606
        assert row.payload["no_municipio"] == "Ponta Porã"
        assert row.project_id == "12771.50-00"


def test_tampered_freshness_receipt_is_refused(database, tmp_path):
    write_pages(tmp_path, "contrato", [envelope([make_row("contrato")])])
    freshness = tmp_path / "freshness.json"
    freshness.write_bytes(freshness.read_bytes() + b" ")
    with pytest.raises(ValueError, match="freshness_integrity_failure"):
        import_obrasgov_catalog(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)) == 0


def test_manifest_with_unknown_dataset_is_refused(database, tmp_path):
    manifest = write_pages(tmp_path, "geometria", [envelope([make_row("geometria")])])
    manifest["dataset"] = "geometrias"
    (tmp_path / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="obrasgov_catalog_manifest_dataset_invalid"):
        import_obrasgov_catalog(database, tmp_path)


def test_cli_collect_and_import_end_to_end(tmp_path, monkeypatch, capsys):
    install_api(monkeypatch, [envelope([make_row("contrato")], page=1,
                                       total_pages=1, total_items=1)])
    folder = tmp_path / "collect"
    oc.main(["collect", "--folder", str(folder), "--dataset", "contrato",
             "--page-size", "2", "--max-pages", "1"])
    collected = json.loads(capsys.readouterr().out.strip())
    assert collected["status"] == "complete"
    assert collected["dataset"] == "contrato"
    oc.main(["import", "--database", f"sqlite:///{tmp_path / 'cli.db'}",
             "--folder", str(folder), "--batch-size", "1"])
    imported = json.loads(capsys.readouterr().out.strip())
    assert imported["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0}
    check = Database(f"sqlite:///{tmp_path / 'cli.db'}")
    try:
        with check.session() as session:
            assert session.scalar(select(func.count()).select_from(ObrasgovCatalog)) == 1
    finally:
        check.engine.dispose()

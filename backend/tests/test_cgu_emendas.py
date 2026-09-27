"""Testes sintéticos do coletor/importador CGU Emendas Parlamentares; nenhuma rede é usada."""
import csv
import hashlib
import io
import json
import zipfile

import pytest
from sqlalchemy import func, select

import bdt.cgu_emendas as cgu
from bdt.cgu_emendas import (
    ARTIFACT_NAME,
    CONVENIO_HEADER,
    DATASET,
    DEFAULT_CDN_URL,
    DOWNLOAD_MAX_BYTES,
    EMENDA_HEADER,
    FAVORECIDO_HEADER,
    LICENSE_NOTE,
    NOT_NATIONAL_COVERAGE,
    CguEmenda,
    collect_cgu_emendas,
    import_cgu_emendas,
    main,
)
from bdt.domain import digest, now
from bdt.storage import Database, Ingestion


def emenda(**overrides):
    row = dict.fromkeys(EMENDA_HEADER, "")
    row.update({
        "Código da Emenda": "202638050004",
        "Ano da Emenda": "2026",
        "Tipo de Emenda": "Emenda Individual - Transferências com Finalidade Definida",
        "Código do Autor da Emenda": "3805",
        "Nome do Autor da Emenda": "Wellington Fagundes",
        "Número da emenda": "0004",
        "Localidade de aplicação do recurso": "Cuiabá - MT",
        "Código Município IBGE": "5103403",
        "Município": "Cuiabá",
        "Código UF IBGE": "5100000",
        "UF": "MATO GROSSO",
        "Região": "Centro-Oeste",
        "Código Função": "12",
        "Nome Função": "Educação",
        "Código Subfunção": "368",
        "Nome Subfunção": "Educação básica",
        "Código Programa": "2030",
        "Nome Programa": "EDUCACAO BASICA",
        "Código Ação": "20RP",
        "Nome Ação": "APOIO A INFRAESTRUTURA PARA A EDUCACAO BASICA",
        "Código Plano Orçamentário": "0000",
        "Nome Plano Orçamentário": "INFRAESTRUTURA PARA A EDUCACAO BASICA - DESPESAS DIVERSAS",
        "Valor Empenhado": "343000,00",
        "Valor Liquidado": "0,00",
        "Valor Pago": "0,00",
        "Valor Restos A Pagar Inscritos": "0,00",
        "Valor Restos A Pagar Cancelados": "343000,00",
        "Valor Restos A Pagar Pagos": "0,00",
    })
    row.update(overrides)
    return row


def convenio(**overrides):
    row = dict.fromkeys(CONVENIO_HEADER, "")
    row.update({
        "Código da Emenda": "201510480009",
        "Código Função": "10",
        "Nome Função": "Saúde",
        "Código Subfunção": "302",
        "Nome Subfunção": "Assistência hospitalar e ambulatorial",
        "Localidade do gasto": "SÃO PAULO (UF)",
        "Tipo de Emenda": "Emenda Individual - Transferências com Finalidade Definida",
        "Data Publicação Convênio": "06/01/2016",
        "Convenente": "FUNDACAO OSWALDO RAMOS",
        "Objeto Convênio": "AQUISICAO DE EQUIPAMENTO E MATERIAL PERMANENTE",
        "Número Convênio": "825378",
        "Valor Convênio": "1450000,00",
    })
    row.update(overrides)
    return row


def favorecido(**overrides):
    row = dict.fromkeys(FAVORECIDO_HEADER, "")
    row.update({
        "Código da Emenda": "202638050004",
        "Código do Autor da Emenda": "3805",
        "Nome do Autor da Emenda": "Wellington Fagundes",
        "Número da emenda": "0004",
        "Tipo de Emenda": "Emenda Individual - Transferências com Finalidade Definida",
        "Ano/Mês": "202609",
        "Código do Favorecido": "25995281000190",
        "Favorecido": "25.995.281 TATIANE GONCALVES NETO",
        "Natureza Jurídica": "Empresário (Individual)",
        "Tipo Favorecido": "Pessoa Jurídica",
        "UF Favorecido": "MG",
        "Município Favorecido": "JUIZ DE FORA",
        "Valor Recebido": "6986,00",
    })
    row.update(overrides)
    return row


def csv_bytes(rows, columns, *, encoding="cp1252"):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue().encode(encoding)


def archive_bytes(*, emendas=None, convenios=None, favorecidos=None, headers=None,
                  extra_members=None, raw_members=None):
    emendas = [emenda()] if emendas is None else emendas
    convenios = [convenio()] if convenios is None else convenios
    favorecidos = [favorecido()] if favorecidos is None else favorecidos
    headers = headers or {"emenda": EMENDA_HEADER, "convenio": CONVENIO_HEADER,
                          "favorecido": FAVORECIDO_HEADER}
    raw_members = raw_members or {}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for block, rows in (("emenda", emendas), ("convenio", convenios),
                            ("favorecido", favorecidos)):
            payload = raw_members.get(block)
            if payload is None:
                payload = csv_bytes(rows, headers[block])
            archive.writestr(cgu.BLOCK_MEMBERS[block], payload)
        for name, payload in (extra_members or {}).items():
            archive.writestr(name, payload)
    return stream.getvalue()


def write_manifest(folder, content, **overrides):
    manifest = {
        "dataset": DATASET,
        "url": DEFAULT_CDN_URL,
        "final_url": DEFAULT_CDN_URL,
        "redirects": [],
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "collected_at": now(),
        "status_code": 200,
        "etag": None,
        "artifact": ARTIFACT_NAME,
        "format": "zip",
        "request_delay_seconds": 1.0,
        "license_note": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    manifest.update(overrides)
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                            encoding="utf-8")
    return manifest


def write_artifact(folder, content=None, **manifest_overrides):
    content = archive_bytes() if content is None else content
    (folder / ARTIFACT_NAME).write_bytes(content)
    return write_manifest(folder, content, **manifest_overrides)


def install_download(monkeypatch, content, *, final_url=None, redirects=None):
    calls, sleeps = [], []

    def fake_download(url, target, max_bytes=DOWNLOAD_MAX_BYTES):
        target.write_bytes(content)
        calls.append(url)
        return {"url": url, "final_url": final_url or url,
                "redirects": redirects if redirects is not None else [],
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                "collected_at": now(), "status_code": 200, "etag": '"synthetic"'}

    monkeypatch.setattr(cgu, "safe_download", fake_download)
    monkeypatch.setattr(cgu.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def store_counts(result):
    return {key: value for key, value in result["counts"].items() if key != "blocks"}


def test_collect_records_manifest_and_empty_redirect_chain(tmp_path, monkeypatch):
    content = archive_bytes()
    calls, sleeps = install_download(monkeypatch, content)
    folder = tmp_path / "coleta"
    result = collect_cgu_emendas(folder)
    assert calls == [DEFAULT_CDN_URL]
    assert sleeps == [1.0]
    assert result["dataset"] == DATASET and result["format"] == "zip"
    assert result["url"] == result["final_url"] == DEFAULT_CDN_URL
    assert result["redirects"] == []
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["bytes"] == len(content)
    assert result["artifact"] == ARTIFACT_NAME
    assert "Decreto 8.777, atribuição; sem espelho derivado" in result["license_note"]
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    assert result["national_catalog_certified"] is False
    assert (folder / ARTIFACT_NAME).read_bytes() == content
    assert json.loads((folder / "collection.json").read_text(encoding="utf-8")) == result


def test_collect_honours_requested_delay(tmp_path, monkeypatch):
    _, sleeps = install_download(monkeypatch, archive_bytes())
    collect_cgu_emendas(tmp_path / "coleta", delay_seconds=2.5)
    assert sleeps == [2.5]


def test_collect_refuses_folder_of_another_url_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    folder = tmp_path / "coleta"
    folder.mkdir()
    (folder / "collection.json").write_text(
        json.dumps({"dataset": DATASET, "url": "https://example.org/other.zip"}), encoding="utf-8")
    with pytest.raises(ValueError, match="another_url"):
        collect_cgu_emendas(folder)


def test_collect_refuses_non_zip_download(tmp_path, monkeypatch):
    install_download(monkeypatch, b"not a zip at all")
    folder = tmp_path / "coleta"
    with pytest.raises(ValueError, match="not_zip"):
        collect_cgu_emendas(folder)
    assert not (folder / "collection.json").exists()
    assert not (folder / ARTIFACT_NAME).exists()


def test_collect_validates_delay(tmp_path, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_cgu_emendas(tmp_path / "coleta", delay_seconds=0.5)


def test_collect_refuses_inconsistent_redirect_chain(tmp_path, monkeypatch):
    install_download(monkeypatch, archive_bytes(), final_url=DEFAULT_CDN_URL,
                     redirects=[{"status": 302, "url": DEFAULT_CDN_URL,
                                 "location": "https://example.org/x.zip"}])
    folder = tmp_path / "coleta"
    with pytest.raises(ValueError, match="redirect_chain_incomplete"):
        collect_cgu_emendas(folder)
    assert not (folder / "collection.json").exists()


def test_collect_records_portal_to_cdn_redirect_chain(tmp_path, monkeypatch, database):
    portal_url = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares"
    redirects = [{"status": 302, "url": portal_url, "location": DEFAULT_CDN_URL}]
    calls, _ = install_download(monkeypatch, archive_bytes(), final_url=DEFAULT_CDN_URL,
                                redirects=redirects)
    folder = tmp_path / "coleta"
    result = collect_cgu_emendas(folder, url=portal_url)
    assert calls == [portal_url]
    assert result["url"] == portal_url
    assert result["final_url"] == DEFAULT_CDN_URL
    assert result["redirects"] == redirects
    imported = import_cgu_emendas(database, folder)
    assert imported["redirects"] == redirects
    with database.session() as session:
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.source["redirects"] == redirects
        assert load.source["final_url"] == DEFAULT_CDN_URL


def test_import_round_trip_preserves_blocks_values_and_key(database, tmp_path):
    manifest = write_artifact(tmp_path)
    result = import_cgu_emendas(database, tmp_path)
    assert store_counts(result) == {"read": 3, "created": 3, "unchanged": 0, "rejected": 0,
                                    "pessoa_fisica_rejected": 0}
    assert result["counts"]["blocks"]["emenda"] == {
        "read": 1, "created": 1, "unchanged": 0, "rejected": 0, "pessoa_fisica_rejected": 0}
    assert result["counts"]["blocks"]["convenio"]["created"] == 1
    assert result["counts"]["blocks"]["favorecido"]["created"] == 1
    assert result["encoding"] == "cp1252"
    assert result["artifact_sha256"] == manifest["sha256"]
    assert result["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        stored = {row.block: row for row in session.scalars(select(CguEmenda))}
        assert set(stored) == {"emenda", "convenio", "favorecido"}
        item = stored["emenda"]
        assert item.key == digest(["emenda"] + [emenda()[name] for name in EMENDA_HEADER])
        assert item.values == {"Valor Empenhado": "343000,00", "Valor Liquidado": "0,00",
                               "Valor Pago": "0,00", "Valor Restos A Pagar Inscritos": "0,00",
                               "Valor Restos A Pagar Cancelados": "343000,00",
                               "Valor Restos A Pagar Pagos": "0,00"}
        assert item.payload["Município"] == "Cuiabá"
        assert item.payload["Localidade de aplicação do recurso"] == "Cuiabá - MT"
        assert item.emenda_code == "202638050004" and item.reference_year == "2026"
        assert item.author_name == "Wellington Fagundes"
        assert item.emenda_type == "Emenda Individual - Transferências com Finalidade Definida"
        assert item.state_name == "MATO GROSSO" and item.state is None
        assert item.year_month is None
        assert item.ibge_code == "5103403" and item.municipality_id is None
        assert item.source["block"] == "emenda"
        assert item.source["member"] == cgu.BLOCK_MEMBERS["emenda"]
        assert item.source["sha256"] == manifest["sha256"]
        assert stored["convenio"].values == {"Valor Convênio": "1450000,00"}
        assert stored["convenio"].payload["Localidade do gasto"] == "SÃO PAULO (UF)"
        assert stored["favorecido"].values == {"Valor Recebido": "6986,00"}
        assert stored["favorecido"].state == "MG" and stored["favorecido"].state_name is None
        assert stored["favorecido"].year_month == "202609"
        assert stored["favorecido"].payload["Natureza Jurídica"] == "Empresário (Individual)"
        for row in stored.values():
            assert row.municipality_id is None
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["blocks"]["favorecido"]["created"] == 1
        assert load.source["members"] == cgu.BLOCK_MEMBERS
        assert load.source["encoding"] == "cp1252"
        assert load.source["national_catalog_certified"] is False


@pytest.mark.parametrize("block,index", [("emenda", 2), ("convenio", 6), ("favorecido", 9)])
def test_changed_header_is_refused_per_member(database, tmp_path, block, index):
    headers = {"emenda": list(EMENDA_HEADER), "convenio": list(CONVENIO_HEADER),
               "favorecido": list(FAVORECIDO_HEADER)}
    headers[block][index] = "Coluna Renomeada"
    write_artifact(tmp_path, archive_bytes(headers=headers))
    with pytest.raises(ValueError, match=f"header_unexpected:{block}"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_permuted_member_header_is_refused(database, tmp_path):
    columns = list(EMENDA_HEADER)
    columns[0], columns[1] = columns[1], columns[0]
    write_artifact(tmp_path, archive_bytes(
        headers={"emenda": columns, "convenio": list(CONVENIO_HEADER),
                 "favorecido": list(FAVORECIDO_HEADER)}))
    with pytest.raises(ValueError, match="header_unexpected:emenda"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_overlong_published_text_is_rejected_and_counted(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(
        emendas=[emenda(), emenda(**{"Código da Emenda": "LONGA",
                                     "Nome do Autor da Emenda": "N" * 301})],
        convenios=[], favorecidos=[]))
    result = import_cgu_emendas(database, tmp_path)
    assert result["counts"]["blocks"]["emenda"] == {
        "read": 2, "created": 1, "unchanged": 0, "rejected": 1, "pessoa_fisica_rejected": 0}
    with database.session() as session:
        row = session.scalar(select(CguEmenda).where(CguEmenda.block == "emenda"))
        assert row.author_name == "Wellington Fagundes"


def test_ragged_data_rows_are_rejected_and_counted(database, tmp_path):
    good = ";".join(emenda()[column] for column in EMENDA_HEADER)
    text = "\r\n".join([";".join(EMENDA_HEADER), good, "202638050004;x", good + ";extra"]) + "\r\n"
    write_artifact(tmp_path, archive_bytes(raw_members={"emenda": text.encode("cp1252")}))
    result = import_cgu_emendas(database, tmp_path)
    assert result["counts"]["blocks"]["emenda"] == {
        "read": 3, "created": 1, "unchanged": 0, "rejected": 2, "pessoa_fisica_rejected": 0}
    assert store_counts(result) == {"read": 5, "created": 3, "unchanged": 0, "rejected": 2,
                                    "pessoa_fisica_rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 3


def test_cp1252_decoding_preserves_accented_text(database, tmp_path):
    content = archive_bytes(emendas=[emenda(**{
        "Localidade de aplicação do recurso": "Vitória da Conquista - BA"})])
    write_artifact(tmp_path, content)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert b"Vit\xf3ria da Conquista" in archive.read(cgu.BLOCK_MEMBERS["emenda"])
    import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        row = session.scalar(select(CguEmenda).where(CguEmenda.block == "emenda"))
        assert row.payload["Localidade de aplicação do recurso"] == "Vitória da Conquista - BA"


def test_pessoa_fisica_is_rejected_while_other_types_are_kept(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(favorecidos=[
        favorecido(),
        favorecido(**{"Tipo Favorecido": "Pessoa Física", "Código do Favorecido": "111",
                      "Favorecido": "Fulano de Tal"}),
        favorecido(**{"Tipo Favorecido": "PESSOA FISICA", "Código do Favorecido": "222",
                      "Favorecido": "Beltrano de Tal"}),
        favorecido(**{"Tipo Favorecido": "Pessoa  Física", "Código do Favorecido": "333",
                      "Favorecido": "Espaço Duplo"}),
        favorecido(**{"Tipo Favorecido": "Pessoa\tFísica", "Código do Favorecido": "444",
                      "Favorecido": "Tabulação"}),
        favorecido(**{"Tipo Favorecido": "Pessoa-Física", "Código do Favorecido": "555",
                      "Favorecido": "Hífen"}),
        favorecido(**{"Tipo Favorecido": "Pessoa\nFísica", "Código do Favorecido": "666",
                      "Favorecido": "Quebra de Linha"}),
        favorecido(**{"Tipo Favorecido": "Pessoa Jurídica", "Código do Favorecido": "777",
                      "Favorecido": "Segunda Empresa LTDA"}),
        favorecido(**{"Tipo Favorecido": "Inscrição Genérica", "Código do Favorecido": "-1",
                      "Favorecido": "Sem informação"}),
        favorecido(**{"Tipo Favorecido": "Unidade Gestora", "Código do Favorecido": "888",
                      "Favorecido": "Unidade Gestora Sintética"}),
        favorecido(**{"Tipo Favorecido": "Sem informação", "Código do Favorecido": "-2",
                      "Favorecido": "Não informado"}),
        favorecido(**{"Tipo Favorecido": "Inválido", "Código do Favorecido": "-3",
                      "Favorecido": "Inválido"}),
    ]))
    result = import_cgu_emendas(database, tmp_path)
    assert result["counts"]["rejected"] == 6
    assert result["counts"]["pessoa_fisica_rejected"] == 6
    assert result["counts"]["blocks"]["favorecido"] == {
        "read": 12, "created": 6, "unchanged": 0, "rejected": 6, "pessoa_fisica_rejected": 6}
    with database.session() as session:
        types = sorted(row.payload["Tipo Favorecido"] for row in session.scalars(
            select(CguEmenda).where(CguEmenda.block == "favorecido")))
        assert types == ["Inscrição Genérica", "Inválido", "Pessoa Jurídica",
                         "Pessoa Jurídica", "Sem informação", "Unidade Gestora"]


def test_monetary_values_stay_exact_published_text(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(emendas=[emenda(**{
        "Valor Empenhado": "1.234.567,89", "Valor Liquidado": "1.000,00", "Valor Pago": "0,00",
        "Valor Restos A Pagar Inscritos": "0,00",
        "Valor Restos A Pagar Cancelados": "34.567,89", "Valor Restos A Pagar Pagos": "0,00"})]))
    import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        row = session.scalar(select(CguEmenda).where(CguEmenda.block == "emenda"))
        assert row.values == {"Valor Empenhado": "1.234.567,89", "Valor Liquidado": "1.000,00",
                              "Valor Pago": "0,00", "Valor Restos A Pagar Inscritos": "0,00",
                              "Valor Restos A Pagar Cancelados": "34.567,89",
                              "Valor Restos A Pagar Pagos": "0,00"}
        assert row.payload["Valor Empenhado"] == "1.234.567,89"
        assert row.payload["Valor Restos A Pagar Cancelados"] == "34.567,89"


def test_reimport_reports_unchanged_and_keeps_one_ingestion_per_run(database, tmp_path):
    write_artifact(tmp_path)
    first = import_cgu_emendas(database, tmp_path)
    second = import_cgu_emendas(database, tmp_path)
    assert first["counts"]["created"] == 3
    assert second["counts"]["created"] == 0 and second["counts"]["unchanged"] == 3
    assert second["counts"]["blocks"]["emenda"]["unchanged"] == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 3
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 2


def test_row_budget_failure_rolls_back_flushed_rows(database, tmp_path):
    write_artifact(tmp_path)
    with pytest.raises(ValueError, match="row_budget_exceeded"):
        import_cgu_emendas(database, tmp_path, batch_size=1, max_rows=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_same_length_tampering_is_refused_by_sha256(database, tmp_path):
    manifest = write_artifact(tmp_path)
    artifact = tmp_path / ARTIFACT_NAME
    raw = artifact.read_bytes()
    artifact.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert artifact.stat().st_size == manifest["bytes"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["sha256"]
    with pytest.raises(ValueError, match="hash_mismatch"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_declared_sha256_mismatch_records_failed_ingestion(database, tmp_path):
    write_artifact(tmp_path, sha256="0" * 64)
    with pytest.raises(ValueError, match="hash_mismatch"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_municipality_links_by_exact_seven_and_derived_six_digit_keys(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(emendas=[
        emenda(**{"Código da Emenda": "A2", "Código Município IBGE": "1234567",
                  "Município": "Município Sintético", "Valor Empenhado": "1,00"}),
        emenda(**{"Código da Emenda": "A6", "Código Município IBGE": "123456",
                  "Município": "Município Sintético", "Valor Empenhado": "6,00"}),
    ]))
    result = import_cgu_emendas(database, tmp_path)
    assert result["counts"]["blocks"]["emenda"]["created"] == 2
    with database.session() as session:
        rows = {row.emenda_code: row for row in session.scalars(
            select(CguEmenda).where(CguEmenda.block == "emenda"))}
        assert rows["A2"].municipality_id == "1234567"  # chave exata de 7 dígitos
        assert rows["A6"].municipality_id == "1234567"  # chave derivada de 6 dígitos
        assert rows["A6"].ibge_code == "123456"         # texto publicado, sem preenchimento


def test_no_municipality_link_without_exact_crosswalk_key(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(emendas=[
        emenda(**{"Código da Emenda": "A1", "Código Município IBGE": "5103403",
                  "Município": "Cuiabá", "Valor Empenhado": "1,00"}),
        emenda(**{"Código da Emenda": "A2", "Código Município IBGE": "510340",
                  "Município": "Cuiabá", "Valor Empenhado": "2,00"}),
        emenda(**{"Código da Emenda": "A3", "Código Município IBGE": "51034031",
                  "Município": "Cuiabá", "Valor Empenhado": "3,00"}),
        emenda(**{"Código da Emenda": "A4", "Código Município IBGE": "Sem informação",
                  "Município": "Cuiabá", "Valor Empenhado": "4,00"}),
        emenda(**{"Código da Emenda": "A5", "Código Município IBGE": "9999999",
                  "Município": "Município Sintético", "Valor Empenhado": "5,00"}),
    ]))
    result = import_cgu_emendas(database, tmp_path)
    assert result["counts"]["blocks"]["emenda"]["created"] == 5
    with database.session() as session:
        rows = {row.emenda_code: row for row in session.scalars(
            select(CguEmenda).where(CguEmenda.block == "emenda"))}
        for row in rows.values():
            assert row.municipality_id is None
        assert rows["A3"].ibge_code == "51034031"  # 8 dígitos: nunca truncado para 7
        assert rows["A5"].ibge_code == "9999999"   # nome igual não vincula


def test_archive_member_ambiguity_is_refused(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(
        extra_members={"EmendasParlamentares_Extra.csv": b"a;b\r\n"}))
    with pytest.raises(ValueError, match="member_ambiguous"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_archive_member_case_duplicate_is_refused(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(
        extra_members={"emendasparlamentares.csv": b"a;b\r\n"}))
    with pytest.raises(ValueError, match="member_ambiguous"):
        import_cgu_emendas(database, tmp_path)


def test_archive_without_reviewed_member_is_refused(database, tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(cgu.BLOCK_MEMBERS["emenda"], csv_bytes([emenda()], EMENDA_HEADER))
        archive.writestr(cgu.BLOCK_MEMBERS["favorecido"],
                         csv_bytes([favorecido()], FAVORECIDO_HEADER))
    write_artifact(tmp_path, stream.getvalue())
    with pytest.raises(ValueError, match="member_missing"):
        import_cgu_emendas(database, tmp_path)


def test_undecodable_cp1252_artifact_is_refused_and_rolled_back(database, tmp_path):
    payload = csv_bytes([emenda()], EMENDA_HEADER).replace(b"Cuiab", b"Cuiab\x81")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(cgu.BLOCK_MEMBERS["emenda"], payload)
        archive.writestr(cgu.BLOCK_MEMBERS["convenio"],
                         csv_bytes([convenio()], CONVENIO_HEADER))
        archive.writestr(cgu.BLOCK_MEMBERS["favorecido"],
                         csv_bytes([favorecido()], FAVORECIDO_HEADER))
    write_artifact(tmp_path, stream.getvalue())
    with pytest.raises(UnicodeDecodeError):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_all_rows_rejected_aborts_and_rolls_back(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(
        emendas=[], convenios=[],
        favorecidos=[favorecido(**{"Tipo Favorecido": "Pessoa Física"})]))
    with pytest.raises(ValueError, match="no_accepted_rows"):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True
        assert load.counts["pessoa_fisica_rejected"] == 1


def test_header_only_artifact_is_refused(database, tmp_path):
    write_artifact(tmp_path, archive_bytes(emendas=[], convenios=[], favorecidos=[]))
    with pytest.raises(ValueError, match="no_data_rows"):
        import_cgu_emendas(database, tmp_path)


@pytest.mark.parametrize("mutation", [
    {"dataset": "other"},
    {"url": "https://example.org/other.zip"},
    {"final_url": "https://example.org/other.zip"},
    {"redirects": [{"status": 302, "url": DEFAULT_CDN_URL,
                    "location": "https://example.org/x.zip"}]},
    {"artifact": "Other.zip"},
    {"format": "csv"},
])
def test_tampered_manifest_is_refused(database, tmp_path, mutation):
    write_artifact(tmp_path, **mutation)
    with pytest.raises(ValueError):
        import_cgu_emendas(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguEmenda)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 0


def test_cli_collect_and_import(tmp_path, monkeypatch, capsys):
    content = archive_bytes()
    calls, _ = install_download(monkeypatch, content)
    folder = tmp_path / "coleta"
    main(["collect", "--folder", str(folder), "--delay-seconds", "1.5"])
    collected = json.loads(capsys.readouterr().out)
    assert collected["url"] == DEFAULT_CDN_URL and calls == [DEFAULT_CDN_URL]
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    main(["import", "--database", url, "--folder", str(folder), "--batch-size", "1"])
    imported = json.loads(capsys.readouterr().out)
    assert imported["counts"]["created"] == 3
    assert imported["counts"]["blocks"]["convenio"]["created"] == 1
    database = Database(url)
    try:
        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(CguEmenda)) == 3
    finally:
        database.engine.dispose()

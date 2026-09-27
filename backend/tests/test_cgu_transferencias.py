"""Testes sintéticos do coletor/importador CGU Transferências; nenhuma rede é usada."""
import csv
import hashlib
import io
import json
import zipfile

import pytest
from sqlalchemy import func, select

import bdt.cgu_transferencias as cgu
from bdt.cgu_transferencias import (
    DATASET,
    DOWNLOAD_MAX_BYTES,
    LICENSE_NOTE,
    NOT_NATIONAL_COVERAGE,
    REQUIRED_COLUMNS,
    CguTransfer,
    collect_cgu_transferencias,
    import_cgu_transferencias,
    main,
)
from bdt.domain import digest, now
from bdt.storage import Database, Ingestion


def transfer(**overrides):
    row = dict.fromkeys(REQUIRED_COLUMNS, "")
    row.update({
        "ANO / MÊS": "202608",
        "TIPO TRANSFERÊNCIA": "Constitucionais e Royalties",
        "TIPO FAVORECIDO": "Administração Pública Municipal",
        "UF": "BA",
        "CÓDIGO MUNICÍPIO SIAFI": "1234",
        "NOME MUNICÍPIO": "São Gonçalo",
        "CÓDIGO ÓRGÃO SIAFI": "26000",
        "NOME ÓRGÃO": "Ministério da Educação",
        "CÓDIGO UNIDADE GESTORA": "152005",
        "NOME UNIDADE GESTORA": "Fundo Nacional de Desenvolvimento da Educação",
        "CÓDIGO FUNÇÃO": "12",
        "NOME FUNÇÃO": "Educação",
        "CÓDIGO SUBFUNÇÃO": "306",
        "NOME SUBFUNÇÃO": "Alimentação e Nutrição",
        "CÓDIGO PROGRAMA": "0903",
        "NOME PROGRAMA": "Operações Especiais",
        "AÇÃO": "0044",
        "NOME AÇÃO": "Transferência ao Fundo de Participação",
        "LINGUAGEM CIDADÃ": "Repasse à educação",
        "CÓDIGO GRUPO DESPESA": "3",
        "NOME GRUPO DESPESA": "Outras Despesas Correntes",
        "CÓDIGO MODALIDADE APLICAÇÃO DESPESA": "30",
        "NOME MODALIDADE APLICAÇÃO DESPESA": "Transferências a Municípios",
        "CÓDIGO ELEMENTO DESPESA": "41",
        "NOME ELEMENTO DESPESA": "Contribuições",
        "CÓDIGO PLANO ORÇAMENTÁRIO": "0000",
        "NOME PLANO ORÇAMENTÁRIO": "Sem informação",
        "CÓDIGO SUBTÍTULO": "0001",
        "NOME SUBTÍTULO": "Transferência constitucional",
        "CÓDIGO LOCALIZADOR": "0001",
        "NOME LOCALIZADOR": "Município de São Gonçalo",
        "SIGLA LOCALIZADOR": "SG",
        "DESCRIÇÃO COMPLEMENTAR LOCALIZADOR": "Sede",
        "CÓDIGO FAVORECIDO": "12345678000199",
        "NOME FAVORECIDO": "Prefeitura Municipal de São Gonçalo",
        "VALOR TRANSFERIDO": "1.234,56",
    })
    row.update(overrides)
    return row


def csv_bytes(rows, *, columns=None, encoding="cp1252"):
    columns = list(columns if columns is not None else REQUIRED_COLUMNS)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue().encode(encoding)


def zip_bytes(payload, *, member):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, payload)
    return stream.getvalue()


def archive_bytes(rows, *, columns=None, month="202608", member=None, encoding="cp1252"):
    return zip_bytes(csv_bytes(rows, columns=columns, encoding=encoding),
                     member=member or cgu.member_name(month))


def write_manifest(folder, content, *, month="202608", **overrides):
    manifest = {
        "dataset": DATASET,
        "month": month,
        "url": cgu.transferencias_url(month),
        "final_url": cgu.transferencias_cdn_url(month),
        "redirects": [{"status": 302, "url": cgu.transferencias_url(month),
                       "location": cgu.transferencias_cdn_url(month)}],
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "collected_at": now(),
        "status_code": 200,
        "etag": None,
        "artifact": cgu.archive_name(month),
        "request_delay_seconds": 1.0,
        "license_note": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    manifest.update(overrides)
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                            encoding="utf-8")
    return manifest


def write_artifact(folder, rows, *, columns=None, month="202608", member=None, encoding="cp1252",
                   **manifest_overrides):
    content = archive_bytes(rows, columns=columns, month=month, member=member, encoding=encoding)
    (folder / cgu.archive_name(month)).write_bytes(content)
    return write_manifest(folder, content, month=month, **manifest_overrides)


def write_raw_artifact(folder, payload, *, month="202608", member=None):
    content = zip_bytes(payload, member=member or cgu.member_name(month))
    (folder / cgu.archive_name(month)).write_bytes(content)
    return write_manifest(folder, content, month=month)


def install_download(monkeypatch, content, *, month="202608", final_url=None, redirects=None):
    calls, sleeps = [], []

    def fake_download(url, target, max_bytes=DOWNLOAD_MAX_BYTES):
        target.write_bytes(content)
        calls.append(url)
        return {"url": url, "final_url": final_url or cgu.transferencias_cdn_url(month),
                "redirects": redirects if redirects is not None else [
                    {"status": 302, "url": url, "location": cgu.transferencias_cdn_url(month)}],
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                "collected_at": now(), "status_code": 200, "etag": '"synthetic"'}

    monkeypatch.setattr(cgu, "safe_download", fake_download)
    monkeypatch.setattr(cgu.time, "sleep", lambda seconds: sleeps.append(seconds))
    return calls, sleeps


def test_collect_records_manifest_and_redirect_chain(tmp_path, monkeypatch):
    content = archive_bytes([transfer()])
    calls, sleeps = install_download(monkeypatch, content)
    folder = tmp_path / "coleta"
    result = collect_cgu_transferencias(folder, month="202608")
    assert calls == [cgu.transferencias_url("202608")]
    assert sleeps == [1.0]
    assert result["dataset"] == DATASET and result["month"] == "202608"
    assert result["url"] == cgu.transferencias_url("202608")
    assert result["final_url"] == cgu.transferencias_cdn_url("202608")
    assert result["redirects"] == [{"status": 302, "url": cgu.transferencias_url("202608"),
                                    "location": cgu.transferencias_cdn_url("202608")}]
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["bytes"] == len(content)
    assert result["artifact"] == "202608_Transferencias.zip"
    assert result["license_note"] == LICENSE_NOTE
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    assert result["national_catalog_certified"] is False
    assert (folder / "202608_Transferencias.zip").read_bytes() == content
    assert json.loads((folder / "collection.json").read_text(encoding="utf-8")) == result


def test_collect_honours_requested_delay(tmp_path, monkeypatch):
    content = archive_bytes([transfer()])
    _, sleeps = install_download(monkeypatch, content)
    collect_cgu_transferencias(tmp_path / "coleta", month="202608", delay_seconds=2.5)
    assert sleeps == [2.5]


def test_collect_refuses_folder_of_another_month_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    folder = tmp_path / "coleta"
    folder.mkdir()
    (folder / "collection.json").write_text(
        json.dumps({"dataset": DATASET, "month": "202607"}), encoding="utf-8")
    with pytest.raises(ValueError, match="another_month"):
        collect_cgu_transferencias(folder, month="202608")


def test_collect_refuses_unreadable_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    folder = tmp_path / "coleta"
    folder.mkdir()
    (folder / "collection.json").write_bytes(b"{not json")
    with pytest.raises(ValueError, match="unreadable"):
        collect_cgu_transferencias(folder, month="202608")


@pytest.mark.parametrize("month", ["2026-08", "202613", "20260", "2026080", "2026ab", None, 202608])
def test_collect_validates_month(tmp_path, month, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="month"):
        collect_cgu_transferencias(tmp_path / "coleta", month=month)


def test_collect_validates_delay(tmp_path, monkeypatch):
    monkeypatch.setattr(cgu, "safe_download", lambda *args, **kwargs: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_cgu_transferencias(tmp_path / "coleta", month="202608", delay_seconds=0.5)


def test_collect_refuses_unexpected_final_url(tmp_path, monkeypatch):
    content = archive_bytes([transfer()])
    portal = cgu.transferencias_url("202608")
    install_download(monkeypatch, content, final_url=portal,
                     redirects=[{"status": 302, "url": portal, "location": portal}])
    folder = tmp_path / "coleta"
    with pytest.raises(ValueError, match="final_url"):
        collect_cgu_transferencias(folder, month="202608")
    assert not (folder / "collection.json").exists()


def test_import_round_trip_preserves_cp1252_text_and_exact_value(database, tmp_path):
    manifest = write_artifact(tmp_path, [
        transfer(),
        transfer(**{"TIPO FAVORECIDO": "Entidades Sem Fins Lucrativos",
                    "CÓDIGO FAVORECIDO": "98765432000188",
                    "NOME FAVORECIDO": "Associação São João",
                    "VALOR TRANSFERIDO": "987.654,32"}),
    ])
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0,
                                "pessoa_fisica_rejected": 0}
    assert result["month"] == "202608"
    assert result["encoding"] == "cp1252"
    assert result["artifact_sha256"] == manifest["sha256"]
    assert result["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "collection.json").read_bytes()).hexdigest()
    assert result["national_catalog_certified"] is False
    with database.session() as session:
        stored = {row.beneficiary_code: row for row in session.scalars(select(CguTransfer))}
        assert set(stored) == {"12345678000199", "98765432000188"}
        first, second = stored["12345678000199"], stored["98765432000188"]
        assert first.value_text == "1.234,56"
        assert first.key == digest(["202608", "Constitucionais e Royalties",
                                    "Administração Pública Municipal", "1234", "26000", "152005",
                                    "12", "306", "0903", "0044", "3", "30", "41", "0000", "0001",
                                    "0001", "12345678000199", "1.234,56"])
        assert first.payload["NOME MUNICÍPIO"] == "São Gonçalo"
        assert first.payload["VALOR TRANSFERIDO"] == "1.234,56"
        assert first.state == "BA" and first.siafi_municipality_code == "1234"
        assert first.municipality_name == "São Gonçalo"
        assert first.municipality_id is None
        assert (first.reference_month, first.year, first.month_number) == ("202608", "2026", "08")
        assert second.payload["NOME FAVORECIDO"] == "Associação São João"
        assert second.payload["NOME FUNÇÃO"] == "Educação"
        assert second.value_text == "987.654,32"
        assert second.municipality_id is None
        assert first.source["sha256"] == manifest["sha256"]
        assert first.source["final_url"] == manifest["final_url"]
        assert first.source["reference_date"] == "202608"
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts == result["counts"]
        assert load.source["redirects"] == manifest["redirects"]
        assert load.source["encoding"] == "cp1252"
        assert load.source["national_catalog_certified"] is False


def test_pessoa_fisica_rows_are_rejected_and_counted(database, tmp_path):
    write_artifact(tmp_path, [
        transfer(),
        transfer(**{"TIPO FAVORECIDO": "Pessoa Física", "CÓDIGO FAVORECIDO": "11111111111",
                    "NOME FAVORECIDO": "Fulano de Tal", "VALOR TRANSFERIDO": "10,00"}),
        transfer(**{"TIPO FAVORECIDO": "PESSOA FISICA", "CÓDIGO FAVORECIDO": "22222222222",
                    "NOME FAVORECIDO": "Beltrano de Tal", "VALOR TRANSFERIDO": "20,00"}),
    ])
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"] == {"read": 3, "created": 1, "unchanged": 0, "rejected": 2,
                                "pessoa_fisica_rejected": 2}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "success"
        assert load.counts["pessoa_fisica_rejected"] == 2


def test_reimport_reports_unchanged_and_keeps_one_ingestion_per_run(database, tmp_path):
    write_artifact(tmp_path, [transfer(), transfer(**{"CÓDIGO FAVORECIDO": "98765432000188"})])
    first = import_cgu_transferencias(database, tmp_path)
    second = import_cgu_transferencias(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0,
                               "pessoa_fisica_rejected": 0}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0,
                                "pessoa_fisica_rejected": 0}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 2
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 2


def test_same_identity_different_name_keeps_both_rows(database, tmp_path):
    write_artifact(tmp_path, [transfer(**{"NOME FAVORECIDO": "Primeiro Nome Publicado"}),
                              transfer(**{"NOME FAVORECIDO": "Segundo Nome Publicado"})])
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"]["created"] == 2
    with database.session() as session:
        stored = list(session.scalars(select(CguTransfer)))
        assert len({row.key for row in stored}) == 2
        assert sorted(row.payload["NOME FAVORECIDO"] for row in stored) == [
            "Primeiro Nome Publicado", "Segundo Nome Publicado"]
    again = import_cgu_transferencias(database, tmp_path)
    assert again["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0,
                               "pessoa_fisica_rejected": 0}


def test_row_budget_failure_rolls_back_flushed_rows(database, tmp_path):
    write_artifact(tmp_path, [transfer(), transfer(**{"CÓDIGO FAVORECIDO": "98765432000188"})])
    with pytest.raises(ValueError, match="row_budget_exceeded"):
        import_cgu_transferencias(database, tmp_path, batch_size=1, max_rows=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_all_rows_rejected_aborts_and_rolls_back(database, tmp_path):
    write_artifact(tmp_path, [transfer(**{"TIPO FAVORECIDO": "Pessoa Física"}),
                              transfer(**{"VALOR TRANSFERIDO": "valor invalido"})])
    with pytest.raises(ValueError, match="no_accepted_rows"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True
        assert load.counts["rejected"] == 2 and load.counts["pessoa_fisica_rejected"] == 1


def test_malformed_rows_are_rejected_and_counted(database, tmp_path):
    write_artifact(tmp_path, [
        transfer(),
        transfer(**{"ANO / MÊS": "2026-08"}),
        transfer(**{"ANO / MÊS": "202613"}),
        transfer(**{"ANO / MÊS": "202607"}),
        transfer(**{"VALOR TRANSFERIDO": "1.234"}),
        transfer(**{"VALOR TRANSFERIDO": ""}),
        transfer(**{"UF": "bahia"}),
        transfer(**{"CÓDIGO MUNICÍPIO SIAFI": "12345"}),
        transfer(**{"NOME FAVORECIDO": "N" * 301}),
    ])
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"] == {"read": 9, "created": 1, "unchanged": 0, "rejected": 8,
                                "pessoa_fisica_rejected": 0}
    with database.session() as session:
        stored = session.scalar(select(CguTransfer))
        assert stored.value_text == "1.234,56"


def test_row_with_unexpected_column_count_is_rejected(database, tmp_path):
    good = ";".join(transfer()[column] for column in REQUIRED_COLUMNS)
    text = "\r\n".join([";".join(REQUIRED_COLUMNS), good, "202608;x", good + ";extra"]) + "\r\n"
    write_raw_artifact(tmp_path, text.encode("cp1252"))
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"] == {"read": 3, "created": 1, "unchanged": 0, "rejected": 2,
                                "pessoa_fisica_rejected": 0}


def test_state_level_row_keeps_municipality_fields_null(database, tmp_path):
    write_artifact(tmp_path, [transfer(**{"UF": "", "CÓDIGO MUNICÍPIO SIAFI": "",
                                          "NOME MUNICÍPIO": ""})])
    result = import_cgu_transferencias(database, tmp_path)
    assert result["counts"]["created"] == 1
    with database.session() as session:
        row = session.scalar(select(CguTransfer))
        assert row.state is None and row.siafi_municipality_code is None
        assert row.municipality_name is None and row.municipality_id is None


def test_same_length_tampering_is_refused_by_sha256(database, tmp_path):
    manifest = write_artifact(tmp_path, [transfer()])
    artifact = tmp_path / "202608_Transferencias.zip"
    raw = artifact.read_bytes()
    artifact.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert artifact.stat().st_size == manifest["bytes"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["sha256"]
    with pytest.raises(ValueError, match="hash_mismatch"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_size_tampering_is_refused(database, tmp_path):
    write_artifact(tmp_path, [transfer()])
    artifact = tmp_path / "202608_Transferencias.zip"
    artifact.write_bytes(artifact.read_bytes() + b"x")
    with pytest.raises(ValueError, match="size_mismatch"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_unexpected_header_is_refused(database, tmp_path):
    columns = [column for column in REQUIRED_COLUMNS if column != "VALOR TRANSFERIDO"]
    write_artifact(tmp_path, [transfer()], columns=columns)
    with pytest.raises(ValueError, match="header_unexpected"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_archive_with_two_csv_members_is_refused(database, tmp_path):
    payload = csv_bytes([transfer()])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(cgu.member_name("202608"), payload)
        archive.writestr("202608_Transferencias_extra.csv", payload)
    content = stream.getvalue()
    (tmp_path / "202608_Transferencias.zip").write_bytes(content)
    write_manifest(tmp_path, content)
    with pytest.raises(ValueError, match="member_mismatch"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_header_only_artifact_is_refused(database, tmp_path):
    write_artifact(tmp_path, [])
    with pytest.raises(ValueError, match="no_data_rows"):
        import_cgu_transferencias(database, tmp_path)


def test_undecodable_cp1252_artifact_is_refused_and_rolled_back(database, tmp_path):
    payload = csv_bytes([transfer()]).replace(b"Prefeitura", b"Prefeitura\x81")
    write_raw_artifact(tmp_path, payload)
    with pytest.raises(UnicodeDecodeError):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


@pytest.mark.parametrize("mutation", [
    {"redirects": []},
    {"redirects": [{"status": 302, "url": cgu.transferencias_url("202608"),
                    "location": cgu.transferencias_cdn_url("202607")}]},
    {"final_url": cgu.transferencias_cdn_url("202607")},
    {"month": "202607"},
    {"artifact": "202607_Transferencias.zip"},
])
def test_tampered_manifest_is_refused(database, tmp_path, mutation):
    write_artifact(tmp_path, [transfer()], **mutation)
    with pytest.raises(ValueError):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0


def test_manifest_declared_sha256_mismatch_records_failed_ingestion(database, tmp_path):
    write_artifact(tmp_path, [transfer()], sha256="0" * 64)
    with pytest.raises(ValueError, match="hash_mismatch"):
        import_cgu_transferencias(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(CguTransfer)) == 0
        assert session.scalar(select(func.count()).select_from(Ingestion)
                              .where(Ingestion.dataset == DATASET)) == 1
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed" and load.counts["rolled_back"] is True


def test_cli_collect_and_import(tmp_path, monkeypatch, capsys):
    content = archive_bytes([transfer()])
    calls, _ = install_download(monkeypatch, content)
    folder = tmp_path / "coleta"
    main(["collect", "--folder", str(folder), "--month", "202608", "--delay-seconds", "1.5"])
    collected = json.loads(capsys.readouterr().out)
    assert collected["month"] == "202608" and calls == [cgu.transferencias_url("202608")]
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    main(["import", "--database", url, "--folder", str(folder), "--batch-size", "1"])
    imported = json.loads(capsys.readouterr().out)
    assert imported["counts"]["created"] == 1
    database = Database(url)
    try:
        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(CguTransfer)) == 1
    finally:
        database.engine.dispose()

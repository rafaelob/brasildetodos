"""Testes sintéticos do coletor/importador do Repasse FAF com População; nenhuma rede é usada."""
import csv
import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from sqlalchemy import func, select

import bdt.fns as fns
from bdt.domain import now
from bdt.fns import (
    DATASET,
    LICENSE_NOTE,
    NOT_NATIONAL_COVERAGE,
    FnsFafPayment,
    collect_fns,
    import_fns,
)
from bdt.storage import Database, Ingestion, Municipality

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
HEADER = [
    "BLOCO", "GRUPO", "ESTRATEGIA", "UF", "MUNICIPIO", "CO_MUNICIPIO_IBGE", "QT_POPULACAO",
    "NU_ANO_REFERENCIA_IBGE", "CNPJ", "ENTIDADE", "BANCO", "AGENCIA", "CONTA", "TP_REPASSE",
    "TP_REPASSE_ESTADO", "ST_FAF", "ST_HU", "DT_ULTIMA_LIBERACAO", "VL_BRUTO", "VL_LIQUIDO",
    "VL_SALDO_CONTA", "DT_SALDO_CONTA",
]
XLSX_HEADER = ["ESTRATÉGIA" if name == "ESTRATEGIA" else name for name in HEADER]
XLSX_URL = "https://portalfns.saude.gov.br/idg_download/repasse-faf-com-populacao-2026-acumulado-ate-julho/"
XLSX_FINAL = ("https://portalfns.saude.gov.br/wp-content/uploads/2026/08/"
              "Repasse-FAF-com-POPULACAO-2026-acumulado-ate-julho.xlsx")
CSV_URL = ("https://portalfns.saude.gov.br/wp-content/uploads/2026/08/"
           "REPASSE-FAF-COM-POPULACAO-2026-sintetico.csv")
ARTIFACT_CSV = "REPASSE-FAF-COM-POPULACAO-2026-sintetico.csv"


def payment(**overrides):
    row = {
        "BLOCO": "ATENÇÃO BÁSICA",
        "GRUPO": "PISO DE ATENÇÃO BÁSICA",
        "ESTRATEGIA": "ESF",
        "UF": "BA",
        "MUNICIPIO": "Município Sintético",
        "CO_MUNICIPIO_IBGE": "123456",
        "QT_POPULACAO": "12345",
        "NU_ANO_REFERENCIA_IBGE": "2026",
        "CNPJ": "12345678000199",
        "ENTIDADE": "Fundo Municipal de Saúde de Teste",
        "BANCO": "001",
        "AGENCIA": "1234",
        "CONTA": "00012345",
        "TP_REPASSE": "PISO",
        "TP_REPASSE_ESTADO": "NAO",
        "ST_FAF": "ATIVO",
        "ST_HU": "NAO",
        "DT_ULTIMA_LIBERACAO": "46203",
        "VL_BRUTO": "1.234,56",
        "VL_LIQUIDO": "1.200,00",
        "VL_SALDO_CONTA": "34,56",
        "DT_SALDO_CONTA": "46203",
    }
    row.update(overrides)
    return row


def column_letter(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def header_row(header=XLSX_HEADER):
    return {column: ("s", column) for column in header}


def xlsx_cell_row(**overrides):
    values = payment(**overrides)
    row = {}
    for column in XLSX_HEADER:
        source = "ESTRATEGIA" if column == "ESTRATÉGIA" else column
        row[column] = ("s", values[source])
    for column in ("QT_POPULACAO", "DT_ULTIMA_LIBERACAO", "DT_SALDO_CONTA"):
        row[column] = ("n", values[column])
    return row


def xlsx_bytes(rows, *, header=XLSX_HEADER, run_strings=None):
    """Constrói um XLSX mínimo com sharedStrings (inclusive runs) e sheet1.xml."""
    run_strings = run_strings or {}
    shared, index = [], {}

    def shared_id(text):
        if text not in index:
            index[text] = len(shared)
            shared.append(text)
        return index[text]

    def render_sheet():
        lines = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for position, column in enumerate(header, start=1):
                cell = row.get(column)
                if cell is None:
                    continue
                kind, value = cell
                reference = f"{column_letter(position)}{row_index}"
                if kind == "s":
                    cells.append(f'<c r="{reference}" t="s"><v>{shared_id(value)}</v></c>')
                elif kind == "inline":
                    cells.append(f'<c r="{reference}" t="inlineStr"><is>'
                                 f'<t xml:space="preserve">{escape(value)}</t></is></c>')
                else:
                    cells.append(f'<c r="{reference}"><v>{escape(str(value))}</v></c>')
            lines.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<worksheet xmlns="{XLSX_NS}"><sheetData>' + "".join(lines)
                + "</sheetData></worksheet>")

    def render_strings():
        items = []
        for text in shared:
            parts = run_strings.get(text)
            if parts:
                runs = "".join('<r><rPr><b/></rPr>'
                               f'<t xml:space="preserve">{escape(part)}</t></r>' for part in parts)
                items.append(f"<si>{runs}</si>")
            else:
                items.append(f'<si><t xml:space="preserve">{escape(text)}</t></si>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<sst xmlns="{XLSX_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">'
                + "".join(items) + "</sst>")

    sheet = render_sheet()
    strings = render_strings()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", strings)
    return buffer.getvalue()


def csv_bytes(rows, *, header=HEADER, encoding="cp1252"):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=",", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(column, "") for column in header])
    return buffer.getvalue().encode(encoding)


def write_manifest(folder, body, *, format_name, artifact, url, reference_year=2026):
    manifest = {
        "dataset": DATASET,
        "url": url,
        "final_url": url,
        "redirects": [],
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "collected_at": now(),
        "reference_year": reference_year,
        "format": format_name,
        "artifact": artifact,
        "license": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    (folder / "collection.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


def write_csv(folder, rows, *, header=HEADER, encoding="cp1252", name=ARTIFACT_CSV):
    body = csv_bytes(rows, header=header, encoding=encoding)
    (folder / name).write_bytes(body)
    return write_manifest(folder, body, format_name="csv", artifact=name, url=CSV_URL)


def write_xlsx(folder, rows, *, name="Repasse-FAF-com-POPULACAO-2026-acumulado-ate-julho.xlsx",
               run_strings=None):
    body = xlsx_bytes(rows, run_strings=run_strings)
    (folder / name).write_bytes(body)
    return write_manifest(folder, body, format_name="xlsx", artifact=name, url=XLSX_URL)


def test_xlsx_streaming_shared_runs_missing_cells_and_serial_dates(database, tmp_path):
    run_text = "Fundo Municipal de Saúde"
    first = xlsx_cell_row(ENTIDADE=run_text)
    first["AGENCIA"] = None  # célula ausente permanece vazia
    second = xlsx_cell_row(MUNICIPIO="São Gonçalo", CO_MUNICIPIO_IBGE="999999")
    second["ENTIDADE"] = ("inline", "Fundo Estadual de Saúde")
    write_xlsx(tmp_path, [header_row(), first, second], run_strings={run_text: ["Fundo ", "Municipal de Saúde"]})
    result = import_fns(database, tmp_path)
    assert result["format"] == "xlsx"
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 1}
    assert result["national_catalog_certified"] is False
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    with database.session() as session:
        stored = {row.entity: row for row in session.scalars(select(FnsFafPayment))}
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
    assert set(stored) == {run_text, "Fundo Estadual de Saúde"}
    linked = stored[run_text]
    assert linked.municipality_id == "1234567"
    assert linked.payload["AGENCIA"] == ""
    assert linked.payload["ENTIDADE"] == run_text
    assert linked.payload["DT_SALDO_CONTA"] == "46203"
    assert linked.last_release_on == "2026-06-30"
    assert linked.balance_on == "2026-06-30"
    assert linked.values == {"VL_BRUTO": "1.234,56", "VL_LIQUIDO": "1.200,00", "VL_SALDO_CONTA": "34,56"}
    assert linked.source["url"] == XLSX_URL
    assert linked.source["reference_year"] == "2026"
    assert stored["Fundo Estadual de Saúde"].municipality_id is None
    assert stored["Fundo Estadual de Saúde"].municipality_name == "São Gonçalo"
    assert load.status == "success"
    assert load.source["format"] == "xlsx"
    assert load.source["license"] == LICENSE_NOTE


def test_csv_cp1252_comma_with_serial_and_iso_dates(database, tmp_path):
    write_csv(tmp_path, [
        payment(ENTIDADE="Ação Municipal de Saúde", MUNICIPIO="São Gonçalo"),
        payment(ENTIDADE="Fundação Estadual", CO_MUNICIPIO_IBGE="999999",
                DT_ULTIMA_LIBERACAO="2026-06-30", DT_SALDO_CONTA="2026-06-30"),
    ])
    result = import_fns(database, tmp_path)
    assert result["format"] == "csv"
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 1}
    with database.session() as session:
        stored = {row.entity: row for row in session.scalars(select(FnsFafPayment))}
    first = stored["Ação Municipal de Saúde"]
    assert first.municipality_name == "São Gonçalo"
    assert first.payload["DT_ULTIMA_LIBERACAO"] == "46203"
    assert first.last_release_on == "2026-06-30"
    second = stored["Fundação Estadual"]
    assert second.payload["DT_ULTIMA_LIBERACAO"] == "2026-06-30"
    assert second.last_release_on == "2026-06-30"
    assert second.balance_on == "2026-06-30"


def test_six_digit_linkage_never_pads_and_rejects_non_six_digit_codes(database, source, tmp_path):
    with database.session() as session:
        session.delete(session.get(Municipality, "1234567"))
        session.add(Municipality(id="0123456", name="Município Zero", state="BA", source=source.model_dump()))
    write_csv(tmp_path, [
        payment(CO_MUNICIPIO_IBGE="012345", ENTIDADE="Entidade Prefixo"),
        payment(CO_MUNICIPIO_IBGE="123456", ENTIDADE="Entidade Sem Prefixo"),
        payment(CO_MUNICIPIO_IBGE="1234567", ENTIDADE="Entidade Sete"),
        payment(CO_MUNICIPIO_IBGE="12345", ENTIDADE="Entidade Cinco"),
    ])
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 4, "created": 2, "unchanged": 0, "rejected": 2, "unlinked": 1}
    with database.session() as session:
        stored = {row.entity: row for row in session.scalars(select(FnsFafPayment))}
    assert set(stored) == {"Entidade Prefixo", "Entidade Sem Prefixo"}
    assert stored["Entidade Prefixo"].municipality_id == "0123456"
    # "123456" preenchido para "0123456" associaria errado; a chave de 6 dígitos é usada como publicada.
    assert stored["Entidade Sem Prefixo"].municipality_id is None


def test_reimport_is_idempotent(database, tmp_path):
    write_csv(tmp_path, [payment(), payment(ENTIDADE="Outra Entidade", CO_MUNICIPIO_IBGE="999999")])
    first = import_fns(database, tmp_path)
    second = import_fns(database, tmp_path)
    assert first["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 1}
    assert second["counts"] == {"read": 2, "created": 0, "unchanged": 2, "rejected": 0, "unlinked": 1}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 2
        loads = list(session.scalars(select(Ingestion).where(Ingestion.dataset == DATASET)))
    assert [load.status for load in loads] == ["success", "success"]


def test_extra_header_column_distinguishes_rows_in_the_key(database, tmp_path):
    # Superset de cabeçalho: a identidade cobre todas as colunas publicadas, então
    # duas linhas idênticas nas 22 colunas canônicas mas distintas na extra ficam.
    header = HEADER + ["OBSERVACAO"]
    write_csv(tmp_path, [
        {**payment(), "OBSERVACAO": "primeira"},
        {**payment(), "OBSERVACAO": "segunda"},
    ], header=header)
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 0}
    with database.session() as session:
        stored = list(session.scalars(select(FnsFafPayment)))
    assert sorted(row.payload["OBSERVACAO"] for row in stored) == ["primeira", "segunda"]


def test_changed_values_are_preserved_never_overwritten(database, tmp_path):
    write_csv(tmp_path, [payment()])
    first = import_fns(database, tmp_path)
    write_csv(tmp_path, [payment(VL_LIQUIDO="1.250,00")])
    second = import_fns(database, tmp_path)
    assert first["counts"]["created"] == 1
    assert second["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0, "unlinked": 0}
    with database.session() as session:
        stored = list(session.scalars(select(FnsFafPayment)))
    assert sorted(row.values["VL_LIQUIDO"] for row in stored) == ["1.200,00", "1.250,00"]


def test_required_field_failures_are_rejected_and_counted(database, tmp_path):
    write_csv(tmp_path, [
        payment(),
        payment(NU_ANO_REFERENCIA_IBGE="20X6"),
        payment(CO_MUNICIPIO_IBGE="12345"),
        payment(CNPJ="123"),
        payment(UF="BAB"),
        payment(ENTIDADE=""),
        payment(CNPJ="98765432000188", ENTIDADE="Válida Dois"),
    ])
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 7, "created": 2, "unchanged": 0, "rejected": 5, "unlinked": 0}
    with database.session() as session:
        stored = {row.entity for row in session.scalars(select(FnsFafPayment))}
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
    assert stored == {"Fundo Municipal de Saúde de Teste", "Válida Dois"}
    assert load.status == "success"
    assert load.counts["rejected"] == 5


def test_all_rows_invalid_rolls_back_with_zero_accepted(database, tmp_path):
    # Nenhuma linha aceita: a carga não pode virar sucesso nem deixar linhas
    # parciais; o importador irmão de CGU recusa pelo mesmo motivo.
    write_csv(tmp_path, [
        payment(CNPJ="1234567800019"),  # 13 dígitos
        payment(CNPJ="98765432000188", DT_SALDO_CONTA="30.06.2026"),
    ])
    with pytest.raises(ValueError, match="fns_import_has_no_accepted_rows"):
        import_fns(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["read"] == 2
        assert load.counts["created"] == 0
        assert load.counts["unchanged"] == 0
        assert load.counts["rejected"] == 2


def test_overlong_text_is_rejected_without_aborting(database, tmp_path):
    write_csv(tmp_path, [
        payment(ENTIDADE="E" * 301),
        payment(ENTIDADE="Entidade Ok", MUNICIPIO="M" * 201),
        payment(ENTIDADE="Válida"),
    ])
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 3, "created": 1, "unchanged": 0, "rejected": 2, "unlinked": 0}
    with database.session() as session:
        stored = list(session.scalars(select(FnsFafPayment)))
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
    assert [row.entity for row in stored] == ["Válida"]
    assert load.status == "success"


def test_published_dash_placeholder_means_absent_date(database, tmp_path):
    # O XLSX real de 2026 publica "-" em DT_SALDO_CONTA/VL_SALDO_CONTA para
    # 33.526 linhas sem saldo; é ausência publicada, não linha malformada.
    write_xlsx(tmp_path, [
        header_row(),
        xlsx_cell_row(DT_SALDO_CONTA="-", VL_SALDO_CONTA="-"),
    ])
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0, "unlinked": 0}
    with database.session() as session:
        stored = session.scalars(select(FnsFafPayment)).one()
    assert stored.balance_on is None
    assert stored.payload["DT_SALDO_CONTA"] == "-"
    assert stored.values["VL_SALDO_CONTA"] == "-"
    assert stored.last_release_on == "2026-06-30"


def test_implausible_excel_serial_keeps_raw_text_and_does_not_convert(database, tmp_path):
    # "2026" publicado numa coluna de data não é serial Excel: fica como texto no
    # payload e a data derivada permanece vazia, nunca 1905-07-17.
    write_csv(tmp_path, [
        payment(DT_ULTIMA_LIBERACAO="2026", DT_SALDO_CONTA="2026"),
        payment(ENTIDADE="Serial Plausível", CNPJ="98765432000188", DT_SALDO_CONTA="46203"),
    ])
    result = import_fns(database, tmp_path)
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 0}
    with database.session() as session:
        stored = {row.entity: row for row in session.scalars(select(FnsFafPayment))}
    implausible = stored["Fundo Municipal de Saúde de Teste"]
    assert implausible.payload["DT_ULTIMA_LIBERACAO"] == "2026"
    assert implausible.payload["DT_SALDO_CONTA"] == "2026"
    assert implausible.last_release_on is None
    assert implausible.balance_on is None
    assert implausible.balance_on != "1905-07-17"
    assert stored["Serial Plausível"].balance_on == "2026-06-30"


def test_header_without_required_columns_is_refused(database, tmp_path):
    columns = [name for name in HEADER if name != "ENTIDADE"]
    write_csv(tmp_path, [payment()], header=columns)
    with pytest.raises(ValueError, match="fns_header_schema_changed"):
        import_fns(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True


def test_size_tampering_is_refused_before_parsing(database, tmp_path):
    manifest = write_csv(tmp_path, [payment()])
    artifact = tmp_path / manifest["artifact"]
    artifact.write_bytes(artifact.read_bytes() + b"x")
    with pytest.raises(ValueError, match="fns_artifact_size_mismatch"):
        import_fns(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_same_length_tampering_is_refused_by_hash(database, tmp_path):
    manifest = write_csv(tmp_path, [payment()])
    artifact = tmp_path / manifest["artifact"]
    raw = artifact.read_bytes()
    artifact.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
    assert artifact.stat().st_size == manifest["bytes"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["sha256"]
    with pytest.raises(ValueError, match="fns_artifact_hash_mismatch"):
        import_fns(database, tmp_path)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"


def test_row_budget_failure_rolls_back_flushed_rows(database, tmp_path):
    # A primeira linha entra em lote (batch_size=1) e o teto de linhas aborta na
    # segunda; nada pode ficar commitado e a ingestão registra o retrocesso.
    write_csv(tmp_path, [payment(), payment(ENTIDADE="Outra Entidade")])
    with pytest.raises(ValueError, match="fns_row_budget_exceeded"):
        import_fns(database, tmp_path, batch_size=1, max_rows=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_manifest_changed_during_import_rolls_back(database, tmp_path, monkeypatch):
    # Simula outro escritor alterando collection.json entre a leitura inicial e a
    # conferência final; o retrocesso precisa desfazer as linhas já em lote.
    write_csv(tmp_path, [payment()])
    checkpoint = tmp_path / "collection.json"
    flush = fns._flush_batch

    def flush_then_change_manifest(session, batch, counts):
        flush(session, batch, counts)
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")

    monkeypatch.setattr(fns, "_flush_batch", flush_then_change_manifest)
    with pytest.raises(ValueError, match="fns_manifest_changed_during_import"):
        import_fns(database, tmp_path, batch_size=1)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 0
        load = session.scalar(select(Ingestion).where(Ingestion.dataset == DATASET))
        assert load.status == "failed"
        assert load.counts["rolled_back"] is True
        assert load.counts["created"] == 1


def test_manifest_format_mismatch_is_refused(database, tmp_path):
    body = xlsx_bytes([header_row(), xlsx_cell_row()])
    (tmp_path / "repasse.xlsx").write_bytes(body)
    write_manifest(tmp_path, body, format_name="csv", artifact="repasse.xlsx", url=XLSX_URL)
    with pytest.raises(ValueError, match="fns_artifact_format_mismatch"):
        import_fns(database, tmp_path)


def test_import_without_municipalities_reports_unlinked(tmp_path):
    write_csv(tmp_path, [payment(), payment(ENTIDADE="Outra Entidade", CO_MUNICIPIO_IBGE="999999")])
    database = Database(f"sqlite:///{tmp_path / 'empty.db'}")
    database.initialize()
    try:
        result = import_fns(database, tmp_path)
    finally:
        database.engine.dispose()
    assert result["counts"] == {"read": 2, "created": 2, "unchanged": 0, "rejected": 0, "unlinked": 2}
    assert result["national_catalog_certified"] is False
    assert result["not_national_coverage"] == NOT_NATIONAL_COVERAGE


def test_initialize_fns_is_additive(database, tmp_path):
    write_csv(tmp_path, [payment()])
    import_fns(database, tmp_path)
    fns.initialize_fns(database)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FnsFafPayment)) == 1


def test_cli_import_prints_json(tmp_path, capsys):
    write_csv(tmp_path, [payment(CO_MUNICIPIO_IBGE="999999")])
    fns.main(["import", "--database", f"sqlite:///{tmp_path / 'cli.db'}", "--folder", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "imported"
    assert output["counts"] == {"read": 1, "created": 1, "unchanged": 0, "rejected": 0, "unlinked": 1}


def test_collect_writes_manifest_and_round_trips(database, tmp_path, monkeypatch):
    body = xlsx_bytes([header_row(), xlsx_cell_row()])

    def fake_download(url, target, max_bytes):
        target.write_bytes(body)
        return {"url": url, "final_url": XLSX_FINAL,
                "redirects": [{"status": 302, "url": url, "location": XLSX_FINAL}],
                "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                "collected_at": now(), "status_code": 200, "etag": None}

    monkeypatch.setattr(fns, "safe_download", fake_download)
    monkeypatch.setattr(fns.time, "sleep", lambda seconds: None)
    folder = tmp_path / "collection"
    collected = collect_fns(folder, url=XLSX_URL, year=2026)
    assert collected["format"] == "xlsx"
    assert collected["artifact"] == "Repasse-FAF-com-POPULACAO-2026-acumulado-ate-julho.xlsx"
    assert collected["final_url"] == XLSX_FINAL
    assert collected["redirects"] == [{"status": 302, "url": XLSX_URL, "location": XLSX_FINAL}]
    assert collected["license"] == LICENSE_NOTE
    assert collected["not_national_coverage"] == NOT_NATIONAL_COVERAGE
    assert collected["sha256"] == hashlib.sha256(body).hexdigest()
    assert (folder / collected["artifact"]).read_bytes() == body
    assert not (folder / "fns-faf-2026.download").exists()
    assert not (folder / "fns-faf-2026.download.manifest.json").exists()
    stored = json.loads((folder / "collection.json").read_text(encoding="utf-8"))
    assert stored == collected
    result = import_fns(database, folder)
    assert result["counts"]["created"] == 1
    assert result["reference_year"] == 2026


def test_collect_sleeps_before_the_single_request(tmp_path, monkeypatch):
    body = xlsx_bytes([header_row(), xlsx_cell_row()])
    events = []

    def fake_download(url, target, max_bytes):
        events.append(("download", url))
        target.write_bytes(body)
        return {"url": url, "final_url": XLSX_FINAL, "redirects": [],
                "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                "collected_at": now(), "status_code": 200, "etag": None}

    monkeypatch.setattr(fns, "safe_download", fake_download)
    monkeypatch.setattr(fns.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    collected = collect_fns(tmp_path / "collection", url=XLSX_URL, year=2026, delay_seconds=2.5)
    assert events == [("sleep", 2.5), ("download", XLSX_URL)]
    assert collected["delay_seconds"] == 2.5


def test_collect_refuses_folder_bound_to_another_url_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(fns, "safe_download", lambda *args, **kwargs: pytest.fail("network download attempted"))
    (tmp_path / "collection.json").write_text(
        json.dumps({"dataset": DATASET, "url": CSV_URL, "reference_year": 2026}), encoding="utf-8")
    with pytest.raises(ValueError, match="another url"):
        collect_fns(tmp_path, url=XLSX_URL, year=2026)


def test_collect_validates_url_year_and_delay_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(fns, "safe_download", lambda *args, **kwargs: pytest.fail("network download attempted"))
    with pytest.raises(ValueError, match="url"):
        collect_fns(tmp_path, url="http://portalfns.saude.gov.br/x.csv", year=2026)
    with pytest.raises(ValueError, match="year"):
        collect_fns(tmp_path, url=XLSX_URL, year=26)
    with pytest.raises(ValueError, match="delay_seconds"):
        collect_fns(tmp_path, url=XLSX_URL, year=2026, delay_seconds=0.25)

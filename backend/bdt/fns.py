"""Coletor operacional do Repasse FAF com População publicado pelo FNS.

Pode afirmar: as linhas publicadas do Repasse FAF com População para um
município (``CO_MUNICIPIO_IBGE`` de 6 dígitos, sem dígito verificador), uma
entidade recebedora (``CNPJ``), a classificação publicada (``BLOCO``,
``GRUPO``, ``ESTRATEGIA``, ``TP_REPASSE``) e os valores e datas exatamente
como publicados, sempre com URL, SHA-256 do artefato e data de coleta.

Nunca pode afirmar: total pago por município, programa ou entidade
(``VL_BRUTO``, ``VL_LIQUIDO`` e ``VL_SALDO_CONTA`` nunca são somados,
subtraídos ou convertidos em float); vínculo do pagamento com unidade,
escola ou posto de saúde; cobertura nacional ou exaustão de repasses;
licença para redistribuir ou espelhar o arquivo — o portal publica
CC BY-ND 3.0 no rodapé, e a nota de licença acompanha o manifesto e cada
linha para que qualquer reuso seja reavaliado. A associação municipal usa
exclusivamente o prefixo de 6 dígitos contra ``municipality_lookup``,
derivado apenas das identidades IBGE carregadas: nunca há preenchimento de
zero à esquerda, truncamento ou associação por nome.

O parser XLSX usa somente a biblioteca padrão (``zipfile`` e
``xml.etree.ElementTree.iterparse``), sem carregar os ~95 MB do
``sheet1.xml`` em memória: as strings compartilhadas viram uma lista e cada
linha é liberada depois de lida. Datas em serial Excel plausível viram ISO,
mantendo o serial publicado no payload; fora da faixa moderna plausível não
há conversão e o texto publicado permanece no payload. A chave de
``fns_faf_payments`` é o SHA-256 de todas as colunas publicadas, na ordem do
cabeçalho, independente da grafia; uma linha com valores diferentes gera uma
nova linha preservada, nunca uma sobrescrita silenciosa. O importador confere
tamanho e SHA-256 antes de parsear, grava tudo em uma única transação, recusa
uma carga sem nenhuma linha aceita e registra ``counts.rolled_back`` quando
qualquer linha falha.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import JSON, Column, ForeignKey, String, select

from .domain import digest, fold, now
from .ingest import municipality_lookup, safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "fns_faf"
DEFAULT_BATCH_SIZE = 500
MAX_ROWS = 5_000_000
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 500
MIN_DELAY_SECONDS = 1.0
XLSX_SHEET = "xl/worksheets/sheet1.xml"
XLSX_SHARED_STRINGS = "xl/sharedStrings.xml"
EXPECTED_COLUMNS = (
    "BLOCO", "GRUPO", "ESTRATEGIA", "UF", "MUNICIPIO", "CO_MUNICIPIO_IBGE",
    "QT_POPULACAO", "NU_ANO_REFERENCIA_IBGE", "CNPJ", "ENTIDADE", "BANCO",
    "AGENCIA", "CONTA", "TP_REPASSE", "TP_REPASSE_ESTADO", "ST_FAF", "ST_HU",
    "DT_ULTIMA_LIBERACAO", "VL_BRUTO", "VL_LIQUIDO", "VL_SALDO_CONTA",
    "DT_SALDO_CONTA",
)
MONETARY_COLUMNS = ("VL_BRUTO", "VL_LIQUIDO", "VL_SALDO_CONTA")
_TEXT_COLUMNS = (
    ("block", "BLOCO", 100),
    ("group", "GRUPO", 100),
    ("strategy", "ESTRATEGIA", 200),
    ("municipality_name", "MUNICIPIO", 200),
    ("population", "QT_POPULACAO", 20),
    ("entity", "ENTIDADE", 300),
    ("bank", "BANCO", 200),
    ("agency", "AGENCIA", 100),
    ("account", "CONTA", 100),
    ("repasse_type", "TP_REPASSE", 100),
    ("repasse_state", "TP_REPASSE_ESTADO", 100),
    ("st_faf", "ST_FAF", 20),
    ("st_hu", "ST_HU", 20),
)
LICENSE_NOTE = (
    "Portal FNS publica licença CC BY-ND 3.0 no rodapé do site; este uso é "
    "operacional e local, sem publicação, espelhamento ou redistribuição do "
    "arquivo. A nota acompanha manifesto e linhas para reavaliação de reuso."
)
NOT_NATIONAL_COVERAGE = (
    "A coleta cobre apenas o arquivo publicado solicitado, no recorte temporal "
    "do seu nome; a presença de um município não certifica cobertura nacional, "
    "exaustão de repasses nem totais."
)
_CANONICAL_COLUMNS = tuple(fold(column) for column in EXPECTED_COLUMNS)
_QUERY_CHUNK = 500
_READ_BLOCK = 1024 * 1024
_COLUMN_REFERENCE = re.compile(r"([A-Z]+)[0-9]+\Z")
_EXCEL_SERIAL = re.compile(r"([0-9]{1,7})(?:\.0+)?\Z")
_EXCEL_EPOCH = date(1899, 12, 30)
_MIN_EXCEL_SERIAL = 20000
_MAX_EXCEL_SERIAL = 80000
_ZIP_MAGIC = frozenset({b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"})


class FnsFafPayment(Base):
    """Uma linha publicada do Repasse FAF com População."""
    __tablename__ = "fns_faf_payments"
    key = Column(String(64), primary_key=True)
    reference_year = Column(String(4), nullable=False, index=True)
    state = Column(String(2), index=True)
    municipality_name = Column(String(200))
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), index=True)
    block = Column(String(100))
    group = Column(String(100))
    strategy = Column(String(200))
    population = Column(String(20))
    cnpj = Column(String(20), index=True)
    entity = Column(String(300))
    bank = Column(String(200))
    agency = Column(String(100))
    account = Column(String(100))
    repasse_type = Column(String(100))
    repasse_state = Column(String(100))
    st_faf = Column(String(20))
    st_hu = Column(String(20))
    last_release_on = Column(String(10))
    balance_on = Column(String(10))
    values = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_fns(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    FnsFafPayment.__table__.create(database.engine, checkfirst=True)


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_name(final_url: str, year: int, format_name: str) -> str:
    name = Path(unquote(urlsplit(final_url).path)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    stem = os.path.splitext(name)[0] if name else ""
    if not stem:
        stem = f"repasse-faf-com-populacao-{year}"
    return f"{stem}.{format_name}"


def _detect_format(path: Path) -> str:
    """Detecta o formato pelo magic number (ZIP/OOXML) antes da extensão."""
    with path.open("rb") as stream:
        magic = stream.read(4)
    return "xlsx" if magic in _ZIP_MAGIC else "csv"


def collect_fns(folder: Path, *, url: str, year: int, delay_seconds: float = 1.0) -> dict:
    """Baixa o arquivo com o baixador allowlisted e grava artefato + collection.json.

    Reutilizar a pasta para outra URL ou outro ano de referência é recusado
    antes de qualquer rede. ``delay_seconds`` é o intervalo de cortesia antes
    da requisição única, obrigatório e nunca inferior a 1s. A cadeia de
    redirecionamentos e a URL final ficam no manifesto, junto da licença e da
    nota de não cobertura nacional.
    """
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("url must be an https URL")
    if type(year) is not int or not 1900 <= year <= 2999:
        raise ValueError("year must be a four-digit integer")
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError(f"delay_seconds must be at least {MIN_DELAY_SECONDS} second")
    delay = float(delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        existing = decode(checkpoint.read_bytes())
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET:
            raise ValueError("collection.json belongs to another dataset; use a different folder")
        if existing.get("url") != url:
            raise ValueError("collection.json belongs to another url; use a different folder")
        if existing.get("reference_year") != year:
            raise ValueError("collection.json belongs to another reference_year; use a different folder")
    download = folder / f"fns-faf-{year}.download"
    time.sleep(delay)
    metadata = safe_download(url, download, MAX_ARTIFACT_BYTES)
    format_name = _detect_format(download)
    artifact_name = _artifact_name(metadata.get("final_url") or url, year, format_name)
    os.replace(download, folder / artifact_name)
    download.with_suffix(download.suffix + ".manifest.json").unlink(missing_ok=True)
    collection = {
        "dataset": DATASET,
        "url": metadata["url"],
        "final_url": metadata.get("final_url") or url,
        "redirects": metadata.get("redirects") or [],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "reference_year": year,
        "format": format_name,
        "artifact": artifact_name,
        "delay_seconds": delay,
        "license": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    _write_json(checkpoint, collection)
    return collection


def _manifest_metadata(manifest) -> dict:
    """Valida o manifesto local antes de qualquer leitura de linha."""
    if not isinstance(manifest, dict) or manifest.get("dataset") != DATASET:
        raise ValueError("collection_manifest_dataset_mismatch")
    url = manifest.get("url")
    final_url = manifest.get("final_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("collection_manifest_url_invalid")
    if not isinstance(final_url, str) or not final_url.startswith("https://"):
        raise ValueError("collection_manifest_final_url_invalid")
    redirects = manifest.get("redirects")
    if not isinstance(redirects, list) or any(not isinstance(entry, dict) for entry in redirects):
        raise ValueError("collection_manifest_redirects_invalid")
    sha256 = manifest.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("collection_manifest_sha256_invalid")
    size = manifest.get("bytes")
    if type(size) is not int or size < 1:
        raise ValueError("collection_manifest_bytes_invalid")
    collected_at = manifest.get("collected_at")
    if not isinstance(collected_at, str) or not collected_at:
        raise ValueError("collection_manifest_collected_at_invalid")
    year = manifest.get("reference_year")
    if type(year) is not int or not 1900 <= year <= 2999:
        raise ValueError("collection_manifest_reference_year_invalid")
    format_name = manifest.get("format")
    if format_name not in {"csv", "xlsx"}:
        raise ValueError("collection_manifest_format_invalid")
    artifact = manifest.get("artifact")
    if (not isinstance(artifact, str) or not artifact or Path(artifact).name != artifact
            or "/" in artifact or "\\" in artifact):
        raise ValueError("collection_manifest_artifact_invalid")
    license_note = manifest.get("license") or LICENSE_NOTE
    if not isinstance(license_note, str) or not license_note:
        raise ValueError("collection_manifest_license_invalid")
    coverage_note = manifest.get("not_national_coverage") or NOT_NATIONAL_COVERAGE
    if not isinstance(coverage_note, str) or not coverage_note:
        raise ValueError("collection_manifest_not_national_coverage_invalid")
    return {"url": url, "final_url": final_url, "redirects": redirects, "sha256": sha256,
            "bytes": size, "collected_at": collected_at, "reference_year": year,
            "format": format_name, "artifact": artifact, "license": license_note,
            "not_national_coverage": coverage_note}


def _verify_artifact(artifact: Path, metadata: dict) -> None:
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("fns_artifact_missing_or_not_regular")
    if artifact.stat().st_size != metadata["bytes"]:
        raise ValueError("fns_artifact_size_mismatch")
    sha = hashlib.sha256()
    with artifact.open("rb") as stream:
        for block in iter(lambda: stream.read(_READ_BLOCK), b""):
            sha.update(block)
    if sha.hexdigest() != metadata["sha256"]:
        raise ValueError("fns_artifact_hash_mismatch")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _guard_member(info: zipfile.ZipInfo) -> None:
    if info.is_dir():
        raise ValueError("fns_xlsx_member_is_directory")
    if info.file_size > MAX_MEMBER_BYTES or info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
        raise ValueError("fns_xlsx_member_exceeds_safe_limits")


def _string_text(element) -> str:
    """Resolve ``<si>``/``<is>`` com ``<t>`` direto ou em runs ``<r><t>``."""
    parts = []
    for child in element:
        name = _local(child.tag)
        if name == "t":
            parts.append(child.text or "")
        elif name == "r":
            for node in child:
                if _local(node.tag) == "t":
                    parts.append(node.text or "")
    return "".join(parts)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        info = archive.getinfo(XLSX_SHARED_STRINGS)
    except KeyError:
        return []
    _guard_member(info)
    strings: list[str] = []
    parent = None
    with archive.open(info) as stream:
        for event, element in ET.iterparse(stream, events=("start", "end")):
            name = _local(element.tag)
            if event == "start":
                if name == "sst":
                    parent = element
                continue
            if name != "si":
                continue
            strings.append(_string_text(element))
            element.clear()
            if parent is not None:
                try:
                    parent.remove(element)
                except ValueError:
                    pass
    return strings


def _column_index(letters: str) -> int:
    index = 0
    for character in letters:
        index = index * 26 + ord(character) - 64
    return index


def _cell_text(cell, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        for child in cell:
            if _local(child.tag) == "is":
                return _string_text(child)
        return ""
    value = ""
    for child in cell:
        if _local(child.tag) == "v":
            value = child.text or ""
            break
    if kind == "s":
        if not value.isdigit():
            raise ValueError("fns_xlsx_shared_string_index_invalid")
        index = int(value)
        if index >= len(shared):
            raise ValueError("fns_xlsx_shared_string_index_out_of_range")
        return shared[index]
    return value


def _row_cells(element, shared: list[str]) -> dict[int, str]:
    cells: dict[int, str] = {}
    for cell in element:
        if _local(cell.tag) != "c":
            continue
        reference = cell.get("r") or ""
        match = _COLUMN_REFERENCE.fullmatch(reference)
        if match is None:
            raise ValueError("fns_xlsx_cell_reference_invalid")
        index = _column_index(match.group(1))
        if index in cells:
            raise ValueError("fns_xlsx_duplicate_cell")
        cells[index] = _cell_text(cell, shared)
    return cells


def _validated_header(names) -> list[str]:
    """Confere o esquema publicado das 22 colunas; aceita ESTRATEGIA/ESTRATÉGIA."""
    if not names:
        raise ValueError("fns_header_absent")
    cleaned = []
    for name in names:
        if not isinstance(name, str):
            raise ValueError("fns_header_invalid")
        text = name.strip().lstrip("\ufeff")
        if not text:
            raise ValueError("fns_header_invalid")
        cleaned.append(text)
    canonical = [fold(name) for name in cleaned]
    if len(set(canonical)) != len(canonical):
        raise ValueError("fns_header_invalid")
    if not set(_CANONICAL_COLUMNS).issubset(canonical):
        raise ValueError("fns_header_schema_changed")
    return cleaned


def _iter_xlsx_records(path: Path):
    """Percorre o sheet1.xml em streaming; devolve (header, canônico, células por coluna)."""
    try:
        with zipfile.ZipFile(path) as archive:
            if XLSX_SHEET not in set(archive.namelist()):
                raise ValueError("fns_xlsx_sheet_missing")
            shared = _shared_strings(archive)
            info = archive.getinfo(XLSX_SHEET)
            _guard_member(info)
            header = canonical = None
            parent = None
            with archive.open(info) as stream:
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    name = _local(element.tag)
                    if event == "start":
                        if name == "sheetData":
                            parent = element
                        continue
                    if name != "row":
                        continue
                    cells = _row_cells(element, shared)
                    element.clear()
                    if parent is not None:
                        try:
                            parent.remove(element)
                        except ValueError:
                            pass
                    if header is None:
                        width = max(cells, default=0)
                        header = _validated_header([cells.get(index, "") for index in range(1, width + 1)])
                        canonical = tuple(fold(column) for column in header)
                        continue
                    if not cells or all(text == "" for text in cells.values()):
                        continue
                    if any(text for index, text in cells.items() if index > len(header)):
                        raise ValueError("fns_row_column_count_mismatch")
                    yield header, canonical, {index: text for index, text in cells.items() if index <= len(header)}
    except ET.ParseError as error:
        raise ValueError("fns_xlsx_parse_error") from error
    except zipfile.BadZipFile as error:
        raise ValueError("fns_xlsx_bad_zip") from error


def _iter_csv_records(path: Path):
    """Lê o CSV cp1252 com vírgula publicado pelo portal, em streaming."""
    try:
        with path.open("rb") as raw, io.TextIOWrapper(raw, encoding="cp1252", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=",")
            header = _validated_header(reader.fieldnames)
            canonical = tuple(fold(column) for column in header)
            for row in reader:
                extras = row.get(None)
                if extras is not None and any(value not in (None, "") for value in extras):
                    raise ValueError("fns_row_column_count_mismatch")
                cells = {position + 1: (row.get(column) or "") for position, column in enumerate(header)}
                yield header, canonical, cells
    except UnicodeDecodeError as error:
        raise ValueError("fns_csv_encoding_unsupported") from error


def _records(artifact: Path, format_name: str):
    if format_name == "xlsx":
        yield from _iter_xlsx_records(artifact)
    else:
        yield from _iter_csv_records(artifact)


def _sanitize(value: str) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(character for character in text if character >= " " or character == "\t").strip()


def _text(value: str, field: str, limit: int):
    """Recusa a linha cujo texto publicado não cabe na coluna; nunca trunca."""
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"fns_row_malformed_{field}")
    return value


def _iso_date(text: str, field: str):
    """Converte serial Excel plausível para ISO; aceita ISO e dd/mm/aaaa publicados.

    O travessão publicado (``-``) é o placeholder do portal para "sem data de
    saldo/liberação": vira ``None`` e o texto original permanece no payload.
    Um número fora da faixa moderna plausível de serial Excel não é convertido
    em data: vira ``None`` e o texto publicado permanece no payload.
    """
    if not text or text == "-":
        return None
    match = _EXCEL_SERIAL.fullmatch(text)
    if match:
        days = int(match.group(1))
        if _MIN_EXCEL_SERIAL <= days <= _MAX_EXCEL_SERIAL:
            return (_EXCEL_EPOCH + timedelta(days=days)).isoformat()
        return None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        try:
            date.fromisoformat(text)
        except ValueError:
            raise ValueError(f"fns_row_malformed_{field}") from None
        return text
    match = re.fullmatch(r"([0-9]{2})/([0-9]{2})/([0-9]{4})", text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
        except ValueError:
            raise ValueError(f"fns_row_malformed_{field}") from None
    raise ValueError(f"fns_row_malformed_{field}")


def _payment_row(header, canonical, cells, lookup, source) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca valor inventado."""
    payload, values = {}, {}
    for position, name in enumerate(header):
        text = _sanitize(cells.get(position + 1, ""))
        payload[name] = text
        values[canonical[position]] = text
    year = values.get("nu_ano_referencia_ibge", "")
    if not re.fullmatch(r"[0-9]{4}", year):
        raise ValueError("fns_row_malformed_reference_year")
    code = values.get("co_municipio_ibge", "")
    if not re.fullmatch(r"[0-9]{6}", code):
        raise ValueError("fns_row_malformed_municipality_code")
    cnpj = re.sub(r"[./\s-]", "", values.get("cnpj", ""))
    if not re.fullmatch(r"[0-9]{14}", cnpj):
        raise ValueError("fns_row_malformed_cnpj")
    state = values.get("uf", "").upper()
    if not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError("fns_row_malformed_state")
    entity = values.get("entidade", "")
    if not entity:
        raise ValueError("fns_row_missing_entity")
    entry = lookup.get(code)
    row = {
        # A identidade cobre todas as colunas do cabeçalho publicado, na ordem
        # em que aparecem: uma coluna extra que distinga linhas não colapsa.
        "key": digest([DATASET] + [values.get(column, "") for column in canonical]),
        "reference_year": year,
        "state": state,
        "municipality_id": entry[0] if entry else None,
        "cnpj": cnpj,
        "last_release_on": _iso_date(values.get("dt_ultima_liberacao", ""), "last_release"),
        "balance_on": _iso_date(values.get("dt_saldo_conta", ""), "balance_date"),
        "values": {column: values.get(fold(column), "") for column in MONETARY_COLUMNS},
        "payload": payload,
        "source": dict(source) | {"reference_year": year},
    }
    for attribute, column, limit in _TEXT_COLUMNS:
        row[attribute] = _text(values.get(fold(column), ""), attribute, limit)
    return row


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    if not batch:
        return
    keys = [item["key"] for item in batch]
    existing = set()
    for chunk in _chunks(keys, _QUERY_CHUNK):
        existing.update(session.scalars(select(FnsFafPayment.key).where(FnsFafPayment.key.in_(chunk))))
    pending: set[str] = set()
    for item in batch:
        key = item["key"]
        if key in pending or key in existing:
            counts["unchanged"] += 1
        else:
            session.add(FnsFafPayment(
                key=key, reference_year=item["reference_year"], state=item["state"],
                municipality_name=item["municipality_name"], municipality_id=item["municipality_id"],
                block=item["block"], group=item["group"], strategy=item["strategy"],
                population=item["population"], cnpj=item["cnpj"], entity=item["entity"],
                bank=item["bank"], agency=item["agency"], account=item["account"],
                repasse_type=item["repasse_type"], repasse_state=item["repasse_state"],
                st_faf=item["st_faf"], st_hu=item["st_hu"],
                last_release_on=item["last_release_on"], balance_on=item["balance_on"],
                values=item["values"], payload=item["payload"], source=item["source"]))
            pending.add(key)
            counts["created"] += 1
        if item["municipality_id"] is None:
            counts["unlinked"] += 1
    session.flush()
    batch.clear()


def import_fns(database: Database, folder: Path, *, batch_size: int = DEFAULT_BATCH_SIZE,
               max_rows: int = MAX_ROWS) -> dict:
    """Importa o artefato local; nunca baixa, nunca soma e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("max_rows must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    manifest = _manifest_metadata(decode(raw_manifest))
    initialize_fns(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0, "unlinked": 0})
    source_json = {
        "dataset": DATASET,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "url": manifest["url"],
        "final_url": manifest["final_url"],
        "redirects": manifest["redirects"],
        "sha256": manifest["sha256"],
        "bytes": manifest["bytes"],
        "collected_at": manifest["collected_at"],
        "reference_year": manifest["reference_year"],
        "format": manifest["format"],
        "artifact": manifest["artifact"],
        "license": manifest["license"],
        "not_national_coverage": manifest["not_national_coverage"],
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json, counts=dict(counts))
        session.add(load)
        session.flush()
        load_id = load.id
    row_source = {"url": manifest["url"], "sha256": manifest["sha256"],
                  "collected_at": manifest["collected_at"], "license": manifest["license"]}
    try:
        # Uma única transação para as linhas: qualquer falha volta com o lote
        # inteiro, sem deixar registros parciais commitados.
        artifact = folder / manifest["artifact"]
        _verify_artifact(artifact, manifest)
        if _detect_format(artifact) != manifest["format"]:
            raise ValueError("fns_artifact_format_mismatch")
        lookup = municipality_lookup(database)
        batch: list[dict] = []
        with database.session() as session:
            for header, canonical, cells in _records(artifact, manifest["format"]):
                counts["read"] += 1
                if counts["read"] > max_rows:
                    raise ValueError("fns_row_budget_exceeded")
                try:
                    item = _payment_row(header, canonical, cells, lookup, row_source)
                except ValueError:
                    counts["rejected"] += 1
                    continue
                batch.append(item)
                if len(batch) >= batch_size:
                    _flush_batch(session, batch, counts)
            _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("fns_artifact_has_no_data_rows")
            if counts["created"] + counts["unchanged"] == 0:
                raise ValueError("fns_import_has_no_accepted_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("fns_manifest_changed_during_import")
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at, load.counts = "success", now(), dict(counts)
    except Exception as error:
        with database.session() as session:
            load = session.get(Ingestion, load_id)
            if load is not None:
                load.status, load.finished_at = "failed", now()
                load.counts = dict(counts) | {"rolled_back": True}
                load.error = str(error)[:160] if isinstance(error, ValueError) else type(error).__name__
        raise
    return {
        "status": "imported",
        "dataset": DATASET,
        "ingestion_id": load_id,
        "reference_year": manifest["reference_year"],
        "format": manifest["format"],
        "counts": dict(counts),
        "manifest_sha256": source_json["manifest_sha256"],
        "not_national_coverage": manifest["not_national_coverage"],
        "national_catalog_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect", help="Baixa o arquivo do Repasse FAF e grava artefato + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--url", required=True)
    collector.add_argument("--year", required=True, type=int)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa o artefato local para o banco operacional")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_fns(args.folder, url=args.url, year=args.year, delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_fns(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

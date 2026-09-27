"""Coletor operacional do dump mensal de transferências do Portal da Transparência (CGU).

Pode afirmar: as linhas publicadas no CSV mensal de "Recursos transferidos" para
o mês solicitado, com o mês de referência (``ANO / MÊS``), o tipo de
transferência, o tipo e o código do favorecido, o órgão e a unidade gestora, a
função/subfunção/programa/ação, o localizador e o valor exatamente como
publicado (texto, nunca float), sempre com URL do portal, URL final do CDN,
cadeia de redirecionamento, SHA-256, tamanho em bytes e data de coleta.

Nunca pode afirmar: vínculo do favorecido, do localizador ou do código SIAFI de
município com um município IBGE (o código SIAFI de 4 caracteres não é IBGE, e
``municipality_id`` permanece nulo em toda linha); soma ou total de valores;
completude nacional, do exercício ou de todos os favorecidos; certificação
nacional (``national_catalog_certified`` é sempre falso). O dump não é
publicado nem espelhado: a coleta é operacional e local ao operador.

O layout verificado em 2026-09-27 (meses 202607 e 202608) tem 36 colunas
separadas por ``;``, todas entre aspas, em cp1252 estrito, e a primeira coluna
é ``ANO / MÊS`` com ``YYYYMM`` — não existem colunas ``ANO`` e ``MÊS``
separadas; a validação exige ano de 4 dígitos e mês de 2 dígitos nessa coluna
combinada. Linhas cujo ``TIPO FAVORECIDO`` indique pessoa física (por exemplo
"Pessoa Física") são recusadas e contadas por precaução, para que um mês
futuro não introduza PF em silêncio; o censo de 202608 não tem nenhuma.

O arquivo não traz texto de licença; o contexto é a política de dados abertos
do Decreto 8.777/2016 com atribuição, registrada no manifesto sem certificar
redistribuição.

A importação usa apenas arquivo e manifesto locais. O manifesto é validado
antes de a ingestão ser aberta; a conferência de tamanho e SHA-256 do artefato
e as linhas rodam em UMA transação, e qualquer erro a partir da abertura da
ingestão desfaz o lote inteiro e marca a ingestão como falha com
``counts.rolled_back``. A chave é o SHA-256 de uma identidade estável (mês +
códigos + valor); quando a mesma identidade já pertence a outra linha publicada,
a linha é preservada com uma chave alternativa do hash completo, nunca
sobrescrita em silêncio.
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
from collections import Counter
from pathlib import Path

from sqlalchemy import JSON, Column, Integer, String, select

from .domain import digest, fold, now
from .ingest import MAX_REDIRECTS, csv_records, safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "cgu_transferencias"
PORTAL_URL = "https://portaldatransparencia.gov.br/download-de-dados/transferencias/{month}"
CDN_URL = ("https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/"
           "transferencias/{month}_Transferencias.zip")
ARCHIVE_NAME = "{month}_Transferencias.zip"
MEMBER_NAME = "{month}_Transferencias.csv"
CHECKPOINT_NAME = "collection.json"
DOWNLOAD_MAX_BYTES = 256 * 1024 * 1024
MIN_DELAY_SECONDS = 1.0
DEFAULT_BATCH_SIZE = 1000
DEFAULT_MAX_ROWS = 5_000_000
LICENSE_NOTE = ("O arquivo não traz texto de licença; o Portal da Transparência publica sob a "
                "política de dados abertos do Decreto 8.777/2016, com atribuição. Uso operacional "
                "local: nunca publicar nem espelhar o dump.")
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre um único mês do recorte federal de recursos transferidos. O mês presente "
    "não prova cobertura nacional, do exercício, de todos os órgãos ou de todos os favorecidos."
)
REQUIRED_COLUMNS = (
    "ANO / MÊS", "TIPO TRANSFERÊNCIA", "TIPO FAVORECIDO", "UF", "CÓDIGO MUNICÍPIO SIAFI",
    "NOME MUNICÍPIO", "CÓDIGO ÓRGÃO SIAFI", "NOME ÓRGÃO", "CÓDIGO UNIDADE GESTORA",
    "NOME UNIDADE GESTORA", "CÓDIGO FUNÇÃO", "NOME FUNÇÃO", "CÓDIGO SUBFUNÇÃO", "NOME SUBFUNÇÃO",
    "CÓDIGO PROGRAMA", "NOME PROGRAMA", "AÇÃO", "NOME AÇÃO", "LINGUAGEM CIDADÃ",
    "CÓDIGO GRUPO DESPESA", "NOME GRUPO DESPESA", "CÓDIGO MODALIDADE APLICAÇÃO DESPESA",
    "NOME MODALIDADE APLICAÇÃO DESPESA", "CÓDIGO ELEMENTO DESPESA", "NOME ELEMENTO DESPESA",
    "CÓDIGO PLANO ORÇAMENTÁRIO", "NOME PLANO ORÇAMENTÁRIO", "CÓDIGO SUBTÍTULO", "NOME SUBTÍTULO",
    "CÓDIGO LOCALIZADOR", "NOME LOCALIZADOR", "SIGLA LOCALIZADOR",
    "DESCRIÇÃO COMPLEMENTAR LOCALIZADOR", "CÓDIGO FAVORECIDO", "NOME FAVORECIDO",
    "VALOR TRANSFERIDO",
)
# Identidade estável da linha publicada: mês + códigos + valor exatamente como publicado.
IDENTITY_COLUMNS = (
    "ANO / MÊS", "TIPO TRANSFERÊNCIA", "TIPO FAVORECIDO", "CÓDIGO MUNICÍPIO SIAFI",
    "CÓDIGO ÓRGÃO SIAFI", "CÓDIGO UNIDADE GESTORA", "CÓDIGO FUNÇÃO", "CÓDIGO SUBFUNÇÃO",
    "CÓDIGO PROGRAMA", "AÇÃO", "CÓDIGO GRUPO DESPESA", "CÓDIGO MODALIDADE APLICAÇÃO DESPESA",
    "CÓDIGO ELEMENTO DESPESA", "CÓDIGO PLANO ORÇAMENTÁRIO", "CÓDIGO SUBTÍTULO",
    "CÓDIGO LOCALIZADOR", "CÓDIGO FAVORECIDO", "VALOR TRANSFERIDO",
)
# Colunas tipadas; o limite recusa a linha em vez de truncar texto publicado.
TYPED_FIELDS = (
    ("transfer_type", "TIPO TRANSFERÊNCIA", 200),
    ("beneficiary_type", "TIPO FAVORECIDO", 200),
    ("state", "UF", 2),
    ("siafi_municipality_code", "CÓDIGO MUNICÍPIO SIAFI", 4),
    ("municipality_name", "NOME MUNICÍPIO", 300),
    ("organ_code", "CÓDIGO ÓRGÃO SIAFI", 20),
    ("organ_name", "NOME ÓRGÃO", 300),
    ("management_unit_code", "CÓDIGO UNIDADE GESTORA", 20),
    ("management_unit_name", "NOME UNIDADE GESTORA", 300),
    ("function_code", "CÓDIGO FUNÇÃO", 20),
    ("function_name", "NOME FUNÇÃO", 300),
    ("subfunction_code", "CÓDIGO SUBFUNÇÃO", 20),
    ("subfunction_name", "NOME SUBFUNÇÃO", 300),
    ("program_code", "CÓDIGO PROGRAMA", 20),
    ("program_name", "NOME PROGRAMA", 300),
    ("action_code", "AÇÃO", 20),
    ("action_name", "NOME AÇÃO", 300),
    ("citizen_language", "LINGUAGEM CIDADÃ", 300),
    ("expense_group_code", "CÓDIGO GRUPO DESPESA", 20),
    ("expense_group_name", "NOME GRUPO DESPESA", 300),
    ("expense_modality_code", "CÓDIGO MODALIDADE APLICAÇÃO DESPESA", 20),
    ("expense_modality_name", "NOME MODALIDADE APLICAÇÃO DESPESA", 300),
    ("expense_element_code", "CÓDIGO ELEMENTO DESPESA", 20),
    ("expense_element_name", "NOME ELEMENTO DESPESA", 300),
    ("budget_plan_code", "CÓDIGO PLANO ORÇAMENTÁRIO", 20),
    ("budget_plan_name", "NOME PLANO ORÇAMENTÁRIO", 300),
    ("subtitle_code", "CÓDIGO SUBTÍTULO", 20),
    ("subtitle_name", "NOME SUBTÍTULO", 300),
    ("locator_code", "CÓDIGO LOCALIZADOR", 20),
    ("locator_name", "NOME LOCALIZADOR", 300),
    ("locator_acronym", "SIGLA LOCALIZADOR", 60),
    ("locator_complement", "DESCRIÇÃO COMPLEMENTAR LOCALIZADOR", 200),
    ("beneficiary_code", "CÓDIGO FAVORECIDO", 40),
    ("beneficiary_name", "NOME FAVORECIDO", 300),
)
_MONTH = re.compile(r"[0-9]{6}\Z")
_VALUE = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_PESSOA_FISICA = "pessoa f"
_QUERY_CHUNK = 500
_READ_BLOCK = 1024 * 1024


class _PessoaFisicaRow(ValueError):
    """Linha recusada por precaução porque o tipo de favorecido é pessoa física."""


class CguTransfer(Base):
    """Uma linha publicada de transferência; nenhum vínculo municipal é criado."""
    __tablename__ = "cgu_transfers"
    key = Column(String(64), primary_key=True)
    reference_month = Column(String(6), nullable=False, index=True)
    year = Column(String(4), nullable=False, index=True)
    month_number = Column(String(2), nullable=False, index=True)
    transfer_type = Column(String(200))
    beneficiary_type = Column(String(200))
    state = Column(String(2), index=True)
    siafi_municipality_code = Column(String(4), index=True)
    municipality_name = Column(String(300))
    municipality_id = Column(String(7), index=True)  # SIAFI não é IBGE: permanece nulo sempre
    organ_code = Column(String(20), index=True)
    organ_name = Column(String(300))
    management_unit_code = Column(String(20), index=True)
    management_unit_name = Column(String(300))
    function_code = Column(String(20))
    function_name = Column(String(300))
    subfunction_code = Column(String(20))
    subfunction_name = Column(String(300))
    program_code = Column(String(20))
    program_name = Column(String(300))
    action_code = Column(String(20))
    action_name = Column(String(300))
    citizen_language = Column(String(300))
    expense_group_code = Column(String(20))
    expense_group_name = Column(String(300))
    expense_modality_code = Column(String(20))
    expense_modality_name = Column(String(300))
    expense_element_code = Column(String(20))
    expense_element_name = Column(String(300))
    budget_plan_code = Column(String(20))
    budget_plan_name = Column(String(300))
    subtitle_code = Column(String(20))
    subtitle_name = Column(String(300))
    locator_code = Column(String(20))
    locator_name = Column(String(300))
    locator_acronym = Column(String(60))
    locator_complement = Column(String(200))
    beneficiary_code = Column(String(40), index=True)
    beneficiary_name = Column(String(300), index=True)
    value_text = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_cgu_transferencias(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    CguTransfer.__table__.create(database.engine, checkfirst=True)


def transferencias_url(month: str) -> str:
    return PORTAL_URL.format(month=month)


def transferencias_cdn_url(month: str) -> str:
    return CDN_URL.format(month=month)


def archive_name(month: str) -> str:
    return ARCHIVE_NAME.format(month=month)


def member_name(month: str) -> str:
    return MEMBER_NAME.format(month=month)


def _validated_month(value) -> str:
    if not isinstance(value, str) or not _MONTH.fullmatch(value) or not 1 <= int(value[4:]) <= 12:
        raise ValueError("month must be a YYYYMM string")
    return value


def _validated_delay(delay_seconds) -> float:
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError("delay_seconds must be at least 1.0 second")
    return float(delay_seconds)


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _reviewed_redirects(url: str, final_url, redirects) -> list[dict]:
    """Valida a cadeia registrada: cada salto liga ao anterior e termina na URL final."""
    if not isinstance(final_url, str) or not final_url:
        raise ValueError("cgu_transferencias_final_url_invalid")
    if not isinstance(redirects, list) or not redirects or len(redirects) > MAX_REDIRECTS:
        raise ValueError("cgu_transferencias_redirect_chain_invalid")
    current = url
    for hop in redirects:
        if (not isinstance(hop, dict) or type(hop.get("status")) is not int
                or not 300 <= hop["status"] < 400 or hop.get("url") != current):
            raise ValueError("cgu_transferencias_redirect_chain_invalid")
        location = hop.get("location")
        if not isinstance(location, str) or not location:
            raise ValueError("cgu_transferencias_redirect_chain_invalid")
        current = location
    if current != final_url:
        raise ValueError("cgu_transferencias_redirect_chain_incomplete")
    return redirects


def _collection_metadata(collection) -> dict:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo."""
    if not isinstance(collection, dict) or collection.get("dataset") != DATASET:
        raise ValueError("cgu_transferencias_collection_manifest_dataset_mismatch")
    month = _validated_month(collection.get("month"))
    url, final_url = collection.get("url"), collection.get("final_url")
    if url != transferencias_url(month) or final_url != transferencias_cdn_url(month):
        raise ValueError("cgu_transferencias_collection_manifest_url_invalid")
    redirects = _reviewed_redirects(url, final_url, collection.get("redirects"))
    sha256 = collection.get("sha256")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ValueError("cgu_transferencias_collection_manifest_sha256_invalid")
    size = collection.get("bytes")
    if type(size) is not int or size < 1:
        raise ValueError("cgu_transferencias_collection_manifest_bytes_invalid")
    collected_at = collection.get("collected_at")
    if not isinstance(collected_at, str) or not collected_at:
        raise ValueError("cgu_transferencias_collection_manifest_collected_at_invalid")
    artifact = collection.get("artifact")
    if artifact != archive_name(month):
        raise ValueError("cgu_transferencias_collection_manifest_artifact_invalid")
    license_note = collection.get("license_note")
    if not isinstance(license_note, str) or not license_note:
        raise ValueError("cgu_transferencias_collection_manifest_license_note_invalid")
    coverage = collection.get("not_national_coverage")
    if not isinstance(coverage, str) or not coverage:
        raise ValueError("cgu_transferencias_collection_manifest_coverage_note_invalid")
    delay = collection.get("request_delay_seconds")
    if delay is not None and (isinstance(delay, bool) or not isinstance(delay, (int, float))
                              or not math.isfinite(float(delay))):
        raise ValueError("cgu_transferencias_collection_manifest_delay_invalid")
    return {"month": month, "url": url, "final_url": final_url, "redirects": redirects,
            "sha256": sha256, "bytes": size, "collected_at": collected_at, "artifact": artifact,
            "license_note": license_note, "not_national_coverage": coverage,
            "request_delay_seconds": None if delay is None else float(delay)}


def _verify_artifact(artifact: Path, metadata: dict) -> None:
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("cgu_transferencias_artifact_missing_or_not_regular")
    if artifact.stat().st_size != metadata["bytes"]:
        raise ValueError("cgu_transferencias_artifact_size_mismatch")
    sha = hashlib.sha256()
    with artifact.open("rb") as stream:
        for block in iter(lambda: stream.read(_READ_BLOCK), b""):
            sha.update(block)
    if sha.hexdigest() != metadata["sha256"]:
        raise ValueError("cgu_transferencias_artifact_hash_mismatch")


def collect_cgu_transferencias(folder: Path, *, month: str, delay_seconds: float = 1.0) -> dict:
    """Baixa o mês com o baixador allowlisted e grava ``<mês>_Transferencias.zip`` + collection.json.

    A URL do portal redireciona para o CDN da CGU; a cadeia só é aceita se cada
    salto continuar HTTPS/allowlisted (o baixador garante) e terminar na URL
    esperada do CDN, e fica registrada no manifesto. Reutilizar a pasta para
    outro mês é recusado antes de qualquer rede. ``delay_seconds`` é o intervalo
    de cortesia antes da requisição única, obrigatório e nunca inferior a 1s.
    """
    month = _validated_month(month)
    delay = _validated_delay(delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / CHECKPOINT_NAME
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except ValueError as error:
            raise ValueError("cgu_transferencias_collection_manifest_unreadable") from error
        if (not isinstance(existing, dict) or existing.get("dataset") != DATASET
                or existing.get("month") != month):
            raise ValueError("cgu_transferencias_collection_belongs_to_another_month; "
                             "use a different folder")
    time.sleep(delay)
    url = transferencias_url(month)
    metadata = safe_download(url, folder / archive_name(month), DOWNLOAD_MAX_BYTES)
    final_url = metadata.get("final_url")
    if final_url != transferencias_cdn_url(month):
        raise ValueError("cgu_transferencias_unexpected_final_url")
    redirects = _reviewed_redirects(url, final_url, metadata.get("redirects"))
    collection = {
        "dataset": DATASET,
        "month": month,
        "url": url,
        "final_url": final_url,
        "redirects": redirects,
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "status_code": metadata.get("status_code"),
        "etag": metadata.get("etag"),
        "artifact": archive_name(month),
        "request_delay_seconds": delay,
        "license_note": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    _write_json(checkpoint, collection)
    return collection


def _archive_member(artifact: Path, month: str) -> str:
    """Aceita exatamente um membro CSV, com o nome revisado do mês."""
    expected = member_name(month)
    try:
        with zipfile.ZipFile(artifact) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as error:
        raise ValueError("cgu_transferencias_archive_unreadable") from error
    csv_members = [name for name in names if name.casefold().endswith(".csv")]
    if len(csv_members) != 1 or csv_members[0].casefold() != expected.casefold():
        raise ValueError("cgu_transferencias_archive_member_mismatch")
    return csv_members[0]


def _archive_header(artifact: Path, member: str) -> list[str]:
    """Exige o layout revisado de 36 colunas; layout diferente exige revisão, não adaptação."""
    try:
        with zipfile.ZipFile(artifact) as archive:
            with archive.open(member) as raw:
                with io.TextIOWrapper(raw, encoding="cp1252", newline="") as stream:
                    header = next(csv.reader(stream, delimiter=";"), None)
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("cgu_transferencias_archive_unreadable") from error
    if header is None:
        raise ValueError("cgu_transferencias_header_absent")
    header = [name.strip().lstrip("\ufeff") for name in header]
    if any(not name for name in header) or len(set(header)) != len(header):
        raise ValueError("cgu_transferencias_header_invalid")
    if tuple(header) != REQUIRED_COLUMNS:
        raise ValueError("cgu_transferencias_header_unexpected")
    return header


def _sanitize(value) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(character for character in text if character >= " " or character == "\t").strip()


def _text(value: str, field: str, limit: int):
    """Recusa a linha cujo texto publicado não cabe na coluna; nunca trunca."""
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"cgu_transferencias_row_malformed_{field}")
    return value


def _is_pessoa_fisica(beneficiary_type: str) -> bool:
    return _PESSOA_FISICA in fold(beneficiary_type)


def _transfer_row(raw, source: dict, manifest_month: str) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca vínculo inventado."""
    if not isinstance(raw, dict) or None in raw or any(value is None for value in raw.values()):
        raise ValueError("cgu_transferencias_row_column_count_mismatch")
    clean = {name: _sanitize(raw.get(name)) for name in REQUIRED_COLUMNS}
    if _is_pessoa_fisica(clean["TIPO FAVORECIDO"]):
        raise _PessoaFisicaRow("cgu_transferencias_row_pessoa_fisica")
    month = clean["ANO / MÊS"]
    if not _MONTH.fullmatch(month) or not 1 <= int(month[4:]) <= 12:
        raise ValueError("cgu_transferencias_row_malformed_month")
    if month != manifest_month:
        raise ValueError("cgu_transferencias_row_month_mismatch")
    value = clean["VALOR TRANSFERIDO"]
    if not _VALUE.fullmatch(value) or len(value) > 40:
        raise ValueError("cgu_transferencias_row_malformed_value")
    state = clean["UF"]
    if state and not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError("cgu_transferencias_row_malformed_state")
    siafi = clean["CÓDIGO MUNICÍPIO SIAFI"]
    if siafi and not re.fullmatch(r"[0-9]{4}", siafi):
        raise ValueError("cgu_transferencias_row_malformed_siafi_code")
    identity = [clean[name] for name in IDENTITY_COLUMNS]
    row_hash = digest(clean)
    item = {
        "key": digest(identity),
        "alternate_key": digest(identity + [row_hash]),
        "reference_month": month,
        "year": month[:4],
        "month_number": month[4:],
        "value_text": value,
        "payload": clean,
        "source": dict(source) | {"reference_date": month},
    }
    for attribute, column, limit in TYPED_FIELDS:
        item[attribute] = _text(clean[column], attribute, limit)
    return item


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Grava o lote na transação corrente; identidade ocupada cai para o hash da linha completa."""
    lookup: list[str] = []
    for item in batch:
        lookup.append(item["key"])
        lookup.append(item["alternate_key"])
    existing = {}
    for chunk in _chunks(lookup, _QUERY_CHUNK):
        for key, payload in session.execute(
                select(CguTransfer.key, CguTransfer.payload).where(CguTransfer.key.in_(chunk))):
            existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        payload = item["payload"]
        candidates = [item["key"], item["alternate_key"]]
        recorded = [pending.get(candidate) if candidate in pending else existing.get(candidate)
                    for candidate in candidates]
        if payload in recorded:
            counts["unchanged"] += 1
            continue
        key = next((candidate for candidate in candidates
                    if candidate not in pending and candidate not in existing), None)
        if key is None:
            raise ValueError("cgu_transferencias_row_conflict_requires_reconciliation")
        session.add(CguTransfer(
            key=key, reference_month=item["reference_month"], year=item["year"],
            month_number=item["month_number"], transfer_type=item["transfer_type"],
            beneficiary_type=item["beneficiary_type"], state=item["state"],
            siafi_municipality_code=item["siafi_municipality_code"],
            municipality_name=item["municipality_name"], municipality_id=None,
            organ_code=item["organ_code"], organ_name=item["organ_name"],
            management_unit_code=item["management_unit_code"],
            management_unit_name=item["management_unit_name"],
            function_code=item["function_code"], function_name=item["function_name"],
            subfunction_code=item["subfunction_code"], subfunction_name=item["subfunction_name"],
            program_code=item["program_code"], program_name=item["program_name"],
            action_code=item["action_code"], action_name=item["action_name"],
            citizen_language=item["citizen_language"],
            expense_group_code=item["expense_group_code"],
            expense_group_name=item["expense_group_name"],
            expense_modality_code=item["expense_modality_code"],
            expense_modality_name=item["expense_modality_name"],
            expense_element_code=item["expense_element_code"],
            expense_element_name=item["expense_element_name"],
            budget_plan_code=item["budget_plan_code"], budget_plan_name=item["budget_plan_name"],
            subtitle_code=item["subtitle_code"], subtitle_name=item["subtitle_name"],
            locator_code=item["locator_code"], locator_name=item["locator_name"],
            locator_acronym=item["locator_acronym"], locator_complement=item["locator_complement"],
            beneficiary_code=item["beneficiary_code"], beneficiary_name=item["beneficiary_name"],
            value_text=item["value_text"], payload=payload, source=item["source"]))
        pending[key] = payload
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_cgu_transferencias(database: Database, folder: Path, *, batch_size: int = DEFAULT_BATCH_SIZE,
                              max_rows: int = DEFAULT_MAX_ROWS) -> dict:
    """Importa o dump local; nunca baixa, nunca soma e nunca deduplica em silêncio.

    Valida o manifesto e abre a ingestão; confere tamanho e SHA-256 do artefato,
    exige o layout revisado e roda todas as linhas em UMA transação. Linhas de
    pessoa física são recusadas e contadas. Qualquer erro a partir da conferência
    do artefato marca a ingestão como falha com ``counts.rolled_back`` e nenhum
    registro parcial fica commitado.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("max_rows must be a positive integer")
    folder = Path(folder)
    raw_manifest = (folder / CHECKPOINT_NAME).read_bytes()
    metadata = _collection_metadata(decode(raw_manifest))
    artifact = folder / metadata["artifact"]
    initialize_cgu_transferencias(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0,
                               "pessoa_fisica_rejected": 0})
    source_json = {
        "dataset": DATASET,
        "month": metadata["month"],
        "url": metadata["url"],
        "final_url": metadata["final_url"],
        "redirects": metadata["redirects"],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "artifact": metadata["artifact"],
        "request_delay_seconds": metadata["request_delay_seconds"],
        "license_note": metadata["license_note"],
        "not_national_coverage": metadata["not_national_coverage"],
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "encoding": "cp1252",
        "delimiter": ";",
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json)
        session.add(load)
        session.flush()
        load_id = load.id
    batch: list[dict] = []
    try:
        # O artefato é conferido dentro da trilha de evidência: falha vira ingestão failed.
        _verify_artifact(artifact, metadata)
        # Uma única transação para as linhas: qualquer erro volta com o lote inteiro.
        with database.session() as session:
            member = _archive_member(artifact, metadata["month"])
            _archive_header(artifact, member)
            row_source = {"url": metadata["url"], "final_url": metadata["final_url"],
                          "sha256": metadata["sha256"], "collected_at": metadata["collected_at"]}
            for raw in csv_records(artifact, member=member, encoding="cp1252", delimiter=";"):
                counts["read"] += 1
                if counts["read"] > max_rows:
                    raise ValueError("cgu_transferencias_row_budget_exceeded")
                try:
                    item = _transfer_row(raw, row_source, metadata["month"])
                except _PessoaFisicaRow:
                    counts["rejected"] += 1
                    counts["pessoa_fisica_rejected"] += 1
                    continue
                except ValueError:
                    counts["rejected"] += 1
                    continue
                batch.append(item)
                if len(batch) >= batch_size:
                    _flush_batch(session, batch, counts)
            _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("cgu_transferencias_has_no_data_rows")
            if counts["created"] + counts["unchanged"] == 0:
                raise ValueError("cgu_transferencias_has_no_accepted_rows")
            if (folder / CHECKPOINT_NAME).read_bytes() != raw_manifest:
                raise ValueError("cgu_transferencias_manifest_changed_during_import")
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
        "month": metadata["month"],
        "counts": dict(counts),
        "encoding": "cp1252",
        "artifact_sha256": metadata["sha256"],
        "manifest_sha256": source_json["manifest_sha256"],
        "final_url": metadata["final_url"],
        "redirects": metadata["redirects"],
        "national_catalog_certified": False,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa o dump mensal e grava o ZIP + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--month", required=True)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa o dump local com hash verificado")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    importer.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_cgu_transferencias(args.folder, month=args.month,
                                            delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_cgu_transferencias(database, args.folder, batch_size=args.batch_size,
                                               max_rows=args.max_rows)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Coletor operacional do dump de Emendas Parlamentares do Portal da Transparência (CGU).

Pode afirmar: as linhas publicadas na extração de emendas parlamentares, em
três membros do mesmo ZIP — ``EmendasParlamentares.csv`` (bloco ``emenda``),
``EmendasParlamentares_Convenios.csv`` (bloco ``convenio``) e
``EmendasParlamentares_PorFavorecido.csv`` (bloco ``favorecido``) — com todos
os valores publicados, os valores monetários como texto exato (nunca somados,
nunca convertidos para float), e a URL do CDN, a URL final, a cadeia de
redirecionamentos, o SHA-256, o tamanho em bytes e a data de coleta
registrados no manifesto e em cada linha.

Nunca pode afirmar: vínculo municipal fora de uma chave exata de
``municipality_lookup(database)``. O vínculo usa exclusivamente o código
publicado como texto, inclusive a chave derivada de 6 dígitos que o crosswalk
expõe; nunca completa (não preenche zeros), nunca trunca e nunca associa por
nome — ``municipality_id`` fica nulo sem chave exata. Também nunca pode
afirmar: total ou soma de qualquer verba (empenhado, liquidado, pago, restos a
pagar inscritos/cancelados/pagos são fases distintas e permanecem como texto);
completude nacional, do exercício ou de todos os autores e favorecidos;
licença para redistribuir ou espelhar o arquivo — a coleta é operacional e
local, sob a política de dados abertos do Decreto 8.777/2016 com atribuição, e
o manifesto registra "sem espelho derivado"; certificação nacional
(``national_catalog_certified`` é sempre falso).

O cabeçalho revisado foi confirmado contra os bytes reais em 2026-09-27
(32.416.974 bytes, SHA-256 CD43234F...B5ED5). O dicionário de referência
divergia em pontos adaptados ao arquivo real: "Tipo de Emenda" (não "Tipo da
Emenda"), "Número da emenda" (não "Número da Emenda") e "Localidade de
aplicação do recurso" no bloco ``emenda`` (não "Localidade do Gasto"); no
bloco ``convenio``, "Localidade do gasto". O cabeçalho é exigido exatamente
como revisado por membro; qualquer mudança falha fechada e exige nova
revisão, sem importação parcial.

A coluna publicada "Código Município IBGE" (bloco ``emenda``) traz códigos de
7 dígitos ou o texto "Sem informação" (censo de 2026-09-27: 37.703 códigos de
7 dígitos e 56.881 "Sem informação"); a largura de 6 dígitos não apareceu e
não é assumida. A coluna "UF" do bloco ``emenda`` publica o nome do estado
(por exemplo "SÃO PAULO"), enquanto "UF Favorecido" no bloco ``favorecido``
publica a sigla; por isso as colunas tipadas são ``state_name`` e ``state``,
respectivamente.

Linhas do bloco ``favorecido`` cujo "Tipo Favorecido" indique pessoa física
(por exemplo "Pessoa Física") são recusadas e contadas em
``pessoa_fisica_rejected``; a comparação normaliza caixa, acentos, espaços e
pontuação pelo radical (letras), de modo que grafias como "Pessoa  Física",
"Pessoa\tFísica", "Pessoa-Física" e "Pessoa\nFísica" também são recusadas. As
demais categorias publicadas ("Pessoa Jurídica", "Sem informação", "Unidade
Gestora", "Inscrição Genérica", "Inválido") são preservadas com o tipo exato.

A importação usa apenas arquivo e manifesto locais. O manifesto é validado
antes de a ingestão ser aberta; a conferência de tamanho e SHA-256 do artefato
roda imediatamente antes da transação, e a resolução dos três membros, a
exigência dos cabeçalhos revisados e as linhas rodam em UMA transação; qualquer
erro a partir da abertura da ingestão desfaz o lote inteiro e marca a ingestão
como falha com ``counts.rolled_back``. A chave de ``cgu_emendas`` é o
SHA-256 de ``[bloco, todos os valores publicados na ordem do cabeçalho]``, o
que torna a reimportação idempotente sem sobrescrever linha publicada em
silêncio.
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

from sqlalchemy import JSON, Column, ForeignKey, String, select

from .domain import digest, fold, now
from .ingest import MAX_REDIRECTS, csv_records, municipality_lookup, safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "cgu_emendas"
DEFAULT_CDN_URL = ("https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/"
                   "emendas-parlamentares/EmendasParlamentares.zip")
ARTIFACT_NAME = "EmendasParlamentares.zip"
CHECKPOINT_NAME = "collection.json"
DOWNLOAD_MAX_BYTES = 256 * 1024 * 1024
MIN_DELAY_SECONDS = 1.0
DEFAULT_BATCH_SIZE = 1000
DEFAULT_MAX_ROWS = 5_000_000
LICENSE_NOTE = ("Decreto 8.777, atribuição; sem espelho derivado. O arquivo não traz texto de "
                "licença; a coleta é operacional e local ao operador, e o dump nunca é publicado "
                "nem espelhado.")
NOT_NATIONAL_COVERAGE = (
    "A extração cobre as emendas parlamentares publicadas pelo Portal da Transparência em um "
    "único arquivo, sem recorte temporal declarado no nome. Isso não certifica cobertura "
    "nacional, do exercício, de todos os autores ou de todos os favorecidos, nem exaustão."
)

# Cabeçalhos revisados contra os bytes reais em 2026-09-27; exigidos na ordem exata.
EMENDA_HEADER = (
    "Código da Emenda", "Ano da Emenda", "Tipo de Emenda", "Código do Autor da Emenda",
    "Nome do Autor da Emenda", "Número da emenda", "Localidade de aplicação do recurso",
    "Código Município IBGE", "Município", "Código UF IBGE", "UF", "Região", "Código Função",
    "Nome Função", "Código Subfunção", "Nome Subfunção", "Código Programa", "Nome Programa",
    "Código Ação", "Nome Ação", "Código Plano Orçamentário", "Nome Plano Orçamentário",
    "Valor Empenhado", "Valor Liquidado", "Valor Pago", "Valor Restos A Pagar Inscritos",
    "Valor Restos A Pagar Cancelados", "Valor Restos A Pagar Pagos",
)
CONVENIO_HEADER = (
    "Código da Emenda", "Código Função", "Nome Função", "Código Subfunção", "Nome Subfunção",
    "Localidade do gasto", "Tipo de Emenda", "Data Publicação Convênio", "Convenente",
    "Objeto Convênio", "Número Convênio", "Valor Convênio",
)
FAVORECIDO_HEADER = (
    "Código da Emenda", "Código do Autor da Emenda", "Nome do Autor da Emenda",
    "Número da emenda", "Tipo de Emenda", "Ano/Mês", "Código do Favorecido", "Favorecido",
    "Natureza Jurídica", "Tipo Favorecido", "UF Favorecido", "Município Favorecido",
    "Valor Recebido",
)
BLOCK_HEADERS = {"emenda": EMENDA_HEADER, "convenio": CONVENIO_HEADER,
                 "favorecido": FAVORECIDO_HEADER}
BLOCK_MEMBERS = {
    "emenda": "EmendasParlamentares.csv",
    "convenio": "EmendasParlamentares_Convenios.csv",
    "favorecido": "EmendasParlamentares_PorFavorecido.csv",
}
# Valores monetários por bloco: guardados como texto exato, nunca somados.
MONETARY_COLUMNS = {
    "emenda": ("Valor Empenhado", "Valor Liquidado", "Valor Pago",
               "Valor Restos A Pagar Inscritos", "Valor Restos A Pagar Cancelados",
               "Valor Restos A Pagar Pagos"),
    "convenio": ("Valor Convênio",),
    "favorecido": ("Valor Recebido",),
}
# Colunas tipadas por bloco; o limite recusa a linha em vez de truncar texto publicado.
TYPED_FIELDS = {
    "emenda": (
        ("emenda_code", "Código da Emenda", 40),
        ("author_name", "Nome do Autor da Emenda", 300),
        ("reference_year", "Ano da Emenda", 10),
        ("emenda_type", "Tipo de Emenda", 200),
        ("state_name", "UF", 60),  # nome do estado, não sigla
        ("municipality_name", "Município", 300),
        ("ibge_code", "Código Município IBGE", 20),
    ),
    "convenio": (
        ("emenda_code", "Código da Emenda", 40),
        ("emenda_type", "Tipo de Emenda", 200),
    ),
    "favorecido": (
        ("emenda_code", "Código da Emenda", 40),
        ("author_name", "Nome do Autor da Emenda", 300),
        ("year_month", "Ano/Mês", 10),
        ("emenda_type", "Tipo de Emenda", 200),
        ("state", "UF Favorecido", 2),  # sigla, quando publicada
        ("municipality_name", "Município Favorecido", 300),
    ),
}
TYPED_ATTRIBUTES = ("emenda_code", "author_name", "reference_year", "year_month",
                    "emenda_type", "state", "state_name", "municipality_name", "ibge_code")
_PF_COLUMN = "Tipo Favorecido"
_PESSOA = "pessoa"
_FISICA = "fisica"
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_QUERY_CHUNK = 500
_READ_BLOCK = 1024 * 1024
_ZIP_MAGIC = frozenset({b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"})


class _PessoaFisicaRow(ValueError):
    """Linha recusada por precaução porque o tipo de favorecido é pessoa física."""


class CguEmenda(Base):
    """Uma linha publicada de emenda, convênio ou favorecido; vínculo municipal só por chave exata."""
    __tablename__ = "cgu_emendas"
    key = Column(String(64), primary_key=True)
    block = Column(String(20), nullable=False, index=True)
    emenda_code = Column(String(40), index=True)
    author_name = Column(String(300))
    reference_year = Column(String(10))
    year_month = Column(String(10))
    emenda_type = Column(String(200))
    state = Column(String(2), index=True)
    state_name = Column(String(60), index=True)
    municipality_name = Column(String(300))
    ibge_code = Column(String(20), index=True)
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), index=True)
    values = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_cgu_emendas(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    CguEmenda.__table__.create(database.engine, checkfirst=True)


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


def _reviewed_redirects(url: str, final_url, redirects) -> list:
    """Valida a cadeia registrada; a cadeia vazia só é aceita quando não houve salto."""
    if not isinstance(final_url, str) or not final_url:
        raise ValueError("cgu_emendas_final_url_invalid")
    if not isinstance(redirects, list) or len(redirects) > MAX_REDIRECTS:
        raise ValueError("cgu_emendas_redirect_chain_invalid")
    current = url
    for hop in redirects:
        if (not isinstance(hop, dict) or type(hop.get("status")) is not int
                or not 300 <= hop["status"] < 400 or hop.get("url") != current):
            raise ValueError("cgu_emendas_redirect_chain_invalid")
        location = hop.get("location")
        if not isinstance(location, str) or not location:
            raise ValueError("cgu_emendas_redirect_chain_invalid")
        current = location
    if current != final_url:
        raise ValueError("cgu_emendas_redirect_chain_incomplete")
    return redirects


def _collection_metadata(collection) -> dict:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo."""
    if not isinstance(collection, dict) or collection.get("dataset") != DATASET:
        raise ValueError("cgu_emendas_collection_manifest_dataset_mismatch")
    url, final_url = collection.get("url"), collection.get("final_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("cgu_emendas_collection_manifest_url_invalid")
    if not isinstance(final_url, str) or not final_url.startswith("https://"):
        raise ValueError("cgu_emendas_collection_manifest_final_url_invalid")
    redirects = _reviewed_redirects(url, final_url, collection.get("redirects"))
    sha256 = collection.get("sha256")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ValueError("cgu_emendas_collection_manifest_sha256_invalid")
    size = collection.get("bytes")
    if type(size) is not int or size < 1:
        raise ValueError("cgu_emendas_collection_manifest_bytes_invalid")
    collected_at = collection.get("collected_at")
    if not isinstance(collected_at, str) or not collected_at:
        raise ValueError("cgu_emendas_collection_manifest_collected_at_invalid")
    if collection.get("artifact") != ARTIFACT_NAME:
        raise ValueError("cgu_emendas_collection_manifest_artifact_invalid")
    if collection.get("format") != "zip":
        raise ValueError("cgu_emendas_collection_manifest_format_invalid")
    license_note = collection.get("license_note")
    if not isinstance(license_note, str) or not license_note:
        raise ValueError("cgu_emendas_collection_manifest_license_note_invalid")
    coverage = collection.get("not_national_coverage")
    if not isinstance(coverage, str) or not coverage:
        raise ValueError("cgu_emendas_collection_manifest_coverage_note_invalid")
    delay = collection.get("request_delay_seconds")
    if delay is not None and (isinstance(delay, bool) or not isinstance(delay, (int, float))
                              or not math.isfinite(float(delay))):
        raise ValueError("cgu_emendas_collection_manifest_delay_invalid")
    return {"url": url, "final_url": final_url, "redirects": redirects, "sha256": sha256,
            "bytes": size, "collected_at": collected_at, "artifact": ARTIFACT_NAME,
            "license_note": license_note, "not_national_coverage": coverage,
            "request_delay_seconds": None if delay is None else float(delay)}


def _verify_artifact(artifact: Path, metadata: dict) -> None:
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("cgu_emendas_artifact_missing_or_not_regular")
    if artifact.stat().st_size != metadata["bytes"]:
        raise ValueError("cgu_emendas_artifact_size_mismatch")
    sha = hashlib.sha256()
    with artifact.open("rb") as stream:
        for block in iter(lambda: stream.read(_READ_BLOCK), b""):
            sha.update(block)
    if sha.hexdigest() != metadata["sha256"]:
        raise ValueError("cgu_emendas_artifact_hash_mismatch")


def _detect_zip(artifact: Path) -> None:
    """Detecta o ZIP pelo magic number, nunca pela extensão."""
    with artifact.open("rb") as stream:
        magic = stream.read(4)
    if magic not in _ZIP_MAGIC:
        raise ValueError("cgu_emendas_artifact_not_zip")


def collect_cgu_emendas(folder: Path, *, url: str = DEFAULT_CDN_URL,
                        delay_seconds: float = 1.0) -> dict:
    """Baixa o dump com o baixador allowlisted e grava ``EmendasParlamentares.zip`` + collection.json.

    A URL revisada é a do CDN da CGU, que responde sem redirecionamento; a
    cadeia registrada é validada e fica no manifesto junto da URL final.
    Reutilizar a pasta para outra URL é recusado antes de qualquer rede.
    ``delay_seconds`` é o intervalo de cortesia antes da requisição única,
    obrigatório e nunca inferior a 1s. O artefato é detectado como ZIP pelo
    magic number; um download que não seja ZIP é removido e recusado sem
    manifesto.
    """
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("url must be an https URL")
    delay = _validated_delay(delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / CHECKPOINT_NAME
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except ValueError as error:
            raise ValueError("cgu_emendas_collection_manifest_unreadable") from error
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET:
            raise ValueError("cgu_emendas_collection_belongs_to_another_dataset; "
                             "use a different folder")
        if existing.get("url") != url:
            raise ValueError("cgu_emendas_collection_belongs_to_another_url; "
                             "use a different folder")
    time.sleep(delay)
    artifact = folder / ARTIFACT_NAME
    metadata = safe_download(url, artifact, DOWNLOAD_MAX_BYTES)
    final_url = metadata.get("final_url")
    redirects = _reviewed_redirects(url, final_url, metadata.get("redirects"))
    try:
        _detect_zip(artifact)
    except ValueError:
        artifact.unlink(missing_ok=True)
        raise
    collection = {
        "dataset": DATASET,
        "url": url,
        "final_url": final_url,
        "redirects": redirects,
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "status_code": metadata.get("status_code"),
        "etag": metadata.get("etag"),
        "artifact": ARTIFACT_NAME,
        "format": "zip",
        "request_delay_seconds": delay,
        "license_note": LICENSE_NOTE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    _write_json(checkpoint, collection)
    return collection


def _archive_members(artifact: Path) -> dict:
    """Resolve os três membros revisados; nome duplicado ou CSV extra é ambiguidade."""
    try:
        with zipfile.ZipFile(artifact) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as error:
        raise ValueError("cgu_emendas_archive_unreadable") from error
    by_fold = {}
    for name in names:
        folded = name.casefold()
        if folded in by_fold:
            raise ValueError("cgu_emendas_archive_member_ambiguous")
        by_fold[folded] = name
    resolved = {}
    for block, expected in BLOCK_MEMBERS.items():
        member = by_fold.get(expected.casefold())
        if member is None:
            raise ValueError(f"cgu_emendas_archive_member_missing:{block}")
        resolved[block] = member
    reviewed = {expected.casefold() for expected in BLOCK_MEMBERS.values()}
    extra = {name.casefold() for name in names if name.casefold().endswith(".csv")} - reviewed
    if extra:
        raise ValueError("cgu_emendas_archive_member_ambiguous")
    return resolved


def _archive_header(artifact: Path, member: str, block: str) -> list:
    """Exige o cabeçalho revisado exato do bloco; layout diferente exige revisão, não adaptação."""
    try:
        with zipfile.ZipFile(artifact) as archive:
            with archive.open(member) as raw:
                with io.TextIOWrapper(raw, encoding="cp1252", newline="") as stream:
                    header = next(csv.reader(stream, delimiter=";"), None)
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("cgu_emendas_archive_unreadable") from error
    if header is None:
        raise ValueError(f"cgu_emendas_header_absent:{block}")
    header = [name.strip().lstrip("\ufeff") for name in header]
    if any(not name for name in header) or len(set(header)) != len(header):
        raise ValueError(f"cgu_emendas_header_invalid:{block}")
    if tuple(header) != BLOCK_HEADERS[block]:
        raise ValueError(f"cgu_emendas_header_unexpected:{block}")
    return header


def _sanitize(value) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(character for character in text if character >= " " or character == "\t").strip()


def _text(value: str, field: str, limit: int):
    """Recusa a linha cujo texto publicado não cabe na coluna; nunca trunca."""
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"cgu_emendas_row_malformed_{field}")
    return value


def _is_pessoa_fisica(beneficiary_type: str) -> bool:
    """Recusa qualquer grafia que una os radicais "pessoa" e "física".

    ``fold`` remove caixa e acentos; em seguida só as letras são mantidas, de
    modo que espaços internos, tabulações, hífens, quebras de linha e
    pontuação não escondem a categoria ("Pessoa  Física", "Pessoa\\tFísica",
    "Pessoa-Física", "Pessoa\\nFísica", "PESSOAFÍSICA"). Categorias publicadas
    de pessoa jurídica e demais rótulos nunca contêm os dois radicais juntos.
    """
    letters = "".join(character for character in fold(beneficiary_type) if character.isalpha())
    return _PESSOA in letters and _FISICA in letters


def _published_values(raw: dict) -> dict:
    """Normaliza as chaves do CSV (BOM/espaço) e recusa linha com coluna sobrando ou faltando."""
    if not isinstance(raw, dict):
        raise ValueError("cgu_emendas_row_column_count_mismatch")
    values = {}
    for key, value in raw.items():
        if not isinstance(key, str) or value is None:
            raise ValueError("cgu_emendas_row_column_count_mismatch")
        name = key.strip().lstrip("\ufeff")
        if not name or name in values:
            raise ValueError("cgu_emendas_row_column_count_mismatch")
        values[name] = _sanitize(value)
    return values


def _emenda_row(block: str, header, raw, lookup: dict, source: dict) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca vínculo inventado."""
    values = _published_values(raw)
    if set(values) != set(header):
        raise ValueError("cgu_emendas_row_column_count_mismatch")
    clean = {name: values[name] for name in header}
    if _PF_COLUMN in clean and _is_pessoa_fisica(clean[_PF_COLUMN]):
        raise _PessoaFisicaRow("cgu_emendas_row_pessoa_fisica")
    item = {
        "key": digest([block] + [clean[name] for name in header]),
        "block": block,
        "values": {name: clean[name] for name in MONETARY_COLUMNS[block]},
        "payload": clean,
        "source": dict(source) | {"block": block, "member": BLOCK_MEMBERS[block]},
        "municipality_id": None,
    }
    for attribute in TYPED_ATTRIBUTES:
        item[attribute] = None
    for attribute, column, limit in TYPED_FIELDS[block]:
        item[attribute] = _text(clean.get(column, ""), attribute, limit)
    code = item["ibge_code"]
    if code:
        entry = lookup.get(code)
        if entry is not None:
            item["municipality_id"] = entry[0]
    return item


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _empty_block_counts() -> dict:
    return {"read": 0, "created": 0, "unchanged": 0, "rejected": 0, "pessoa_fisica_rejected": 0}


def _flush_batch(session, batch: list, counts: Counter, block_counts: dict) -> None:
    """Grava o lote na transação corrente; a chave cobre todos os valores publicados."""
    keys = [item["key"] for item in batch]
    existing = set()
    for chunk in _chunks(keys, _QUERY_CHUNK):
        existing.update(session.scalars(select(CguEmenda.key).where(CguEmenda.key.in_(chunk))))
    pending = set()
    for item in batch:
        target = block_counts[item["block"]]
        if item["key"] in pending or item["key"] in existing:
            counts["unchanged"] += 1
            target["unchanged"] += 1
            continue
        session.add(CguEmenda(
            key=item["key"], block=item["block"], emenda_code=item["emenda_code"],
            author_name=item["author_name"], reference_year=item["reference_year"],
            year_month=item["year_month"], emenda_type=item["emenda_type"],
            state=item["state"], state_name=item["state_name"],
            municipality_name=item["municipality_name"], ibge_code=item["ibge_code"],
            municipality_id=item["municipality_id"], values=item["values"],
            payload=item["payload"], source=item["source"]))
        pending.add(item["key"])
        counts["created"] += 1
        target["created"] += 1
    session.flush()
    batch.clear()


def import_cgu_emendas(database: Database, folder: Path, *, batch_size: int = DEFAULT_BATCH_SIZE,
                       max_rows: int = DEFAULT_MAX_ROWS) -> dict:
    """Importa o dump local; nunca baixa, nunca soma e nunca vincula fora da chave exata.

    Valida o manifesto e abre a ingestão; confere tamanho e SHA-256
    imediatamente antes da transação e roda a resolução dos três membros, os
    cabeçalhos revisados e todas as linhas em UMA transação. Linhas de pessoa
    física são recusadas e contadas. Qualquer erro a partir da conferência do
    artefato marca a ingestão como falha com ``counts.rolled_back`` e nenhum
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
    initialize_cgu_emendas(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0,
                               "pessoa_fisica_rejected": 0})
    block_counts = {block: _empty_block_counts() for block in BLOCK_HEADERS}
    source_json = {
        "dataset": DATASET,
        "url": metadata["url"],
        "final_url": metadata["final_url"],
        "redirects": metadata["redirects"],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "artifact": metadata["artifact"],
        "members": dict(BLOCK_MEMBERS),
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
    batch: list = []
    try:
        # O artefato é conferido dentro da trilha de evidência: falha vira ingestão failed.
        _verify_artifact(artifact, metadata)
        # Uma única transação cobre membros, cabeçalhos e linhas: falha volta com o lote inteiro.
        with database.session() as session:
            members = _archive_members(artifact)
            headers = {block: _archive_header(artifact, member, block)
                       for block, member in members.items()}
            lookup = municipality_lookup(database)
            row_source = {"dataset": DATASET, "url": metadata["url"],
                          "final_url": metadata["final_url"], "sha256": metadata["sha256"],
                          "collected_at": metadata["collected_at"]}
            for block, member in members.items():
                for raw in csv_records(artifact, member=member, encoding="cp1252", delimiter=";"):
                    counts["read"] += 1
                    block_counts[block]["read"] += 1
                    if counts["read"] > max_rows:
                        raise ValueError("cgu_emendas_row_budget_exceeded")
                    try:
                        item = _emenda_row(block, headers[block], raw, lookup, row_source)
                    except _PessoaFisicaRow:
                        counts["rejected"] += 1
                        block_counts[block]["rejected"] += 1
                        counts["pessoa_fisica_rejected"] += 1
                        block_counts[block]["pessoa_fisica_rejected"] += 1
                        continue
                    except ValueError:
                        counts["rejected"] += 1
                        block_counts[block]["rejected"] += 1
                        continue
                    batch.append(item)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts, block_counts)
                _flush_batch(session, batch, counts, block_counts)
            if counts["read"] == 0:
                raise ValueError("cgu_emendas_has_no_data_rows")
            if counts["created"] + counts["unchanged"] == 0:
                raise ValueError("cgu_emendas_has_no_accepted_rows")
            if (folder / CHECKPOINT_NAME).read_bytes() != raw_manifest:
                raise ValueError("cgu_emendas_manifest_changed_during_import")
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at = "success", now()
            load.counts = dict(counts) | {"blocks": block_counts}
    except Exception as error:
        with database.session() as session:
            load = session.get(Ingestion, load_id)
            if load is not None:
                load.status, load.finished_at = "failed", now()
                load.counts = dict(counts) | {"blocks": block_counts, "rolled_back": True}
                load.error = str(error)[:160] if isinstance(error, ValueError) else type(error).__name__
        raise
    return {
        "status": "imported",
        "dataset": DATASET,
        "ingestion_id": load_id,
        "counts": dict(counts) | {"blocks": block_counts},
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
        "collect", help="Baixa o dump de emendas e grava o ZIP + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--url", default=DEFAULT_CDN_URL)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa o dump local com hash verificado")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    importer.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_cgu_emendas(args.folder, url=args.url, delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_cgu_emendas(database, args.folder, batch_size=args.batch_size,
                                        max_rows=args.max_rows)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Coletor operacional do PDDE Básico publicado pelo FNDE.

Pode afirmar: linhas publicadas de execução/liberação do PDDE Básico por
exercício, com o código de escola publicado (CO_ESCOLA), o CNPJ e o nome do
recebedor (CNPJ_UEX/NO_UEX), os valores publicados (colunas VL_*) e o exercício
de referência, sempre com URL, SHA-256 do artefato e data de coleta.

Nunca pode afirmar: dinheiro "para a escola" quando o CNPJ recebedor é uma EEx
ou prefeitura; totais mensais acumulados; completude de 2026; equivalência com
o PDDE Info; zero PDDE para escola ausente da publicação; certificação
nacional. Não é um razão de pagamentos: linhas duplicadas do mesmo par
escola/CNPJ com DT_INI_VINCULACAO diferente são preservadas, nunca somadas nem
deduplicadas em silêncio.

O endpoint de acesso (``.../data-products/{id}/artifact``) é público, mas não
está vinculado no registro DCAT; por isso a proveniência registra
``access_note``. Licença CC BY (atribuição; redistribuição permitida).

No artefato nacional verificado em 2026-09-27 o CSV é UTF-8 estrito (o decode
cp1252 falha no byte 10.969.033); a importação tenta UTF-8 e depois cp1252 e
recusa o que não decodifica, sem substituir caracteres em silêncio. A tupla de
identidade prescrita (product_id + AN_EXERCICIO + CO_ESCOLA + CNPJ_UEX +
DT_INI_VINCULACAO + VL_PAGO_TOTAL) não é única nessa publicação: a mesma
escola/CNPJ/data/total aparece em 1ª e 2ª parcelas (SG_DESTINACAO) e em cargos
distintos. A chave usa a tupla quando ela está livre e cai para um hash da
linha completa quando ela já pertence a outra linha; nenhuma linha publicada é
somada, descartada ou deduplicada em silêncio.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import zlib
from collections import Counter
from pathlib import Path

from sqlalchemy import JSON, Column, ForeignKey, Integer, String, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion, Municipality, Place

DATASET = "pdde"
DEFAULT_PRODUCT_ID = 66
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 4 * 1024 ** 3
MAX_COMPRESSION_RATIO = 500
ARTIFACT_URL = "https://www.fnde.gov.br/plataforma-antonieta-de-barros-api/products/data-products/{product_id}/artifact"
ACCESS_NOTE = ("Endpoint público do FNDE, mas não vinculado no registro DCAT; "
               "acesso operacional de leitura, não um contrato público de API.")
REQUIRED_COLUMNS = ("AN_EXERCICIO", "CO_ESCOLA")
_QUERY_CHUNK = 500
_READ_BLOCK = 1024 * 1024


class PddePayment(Base):
    """Uma linha publicada de execução/liberação do PDDE Básico."""
    __tablename__ = "pdde_payments"
    key = Column(String(64), primary_key=True)
    product_id = Column(Integer, nullable=False, index=True)
    exercise = Column(String(4), nullable=False, index=True)
    state = Column(String(2), index=True)
    municipality_name = Column(String(200))
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), index=True)
    school_code = Column(String(8), index=True)
    school_place_id = Column(String(180), ForeignKey("places.id"), index=True)
    recipient_cnpj = Column(String(20), index=True)
    recipient_name = Column(String(300))
    values = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_pdde(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    PddePayment.__table__.create(database.engine, checkfirst=True)


def artifact_url(product_id: int) -> str:
    return ARTIFACT_URL.format(product_id=product_id)


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def collect_pdde(folder: Path, *, product_id: int = DEFAULT_PRODUCT_ID,
                 max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Baixa o artefato com o baixador allowlisted e grava artifact.gz + collection.json.

    Reutilizar a pasta para outro product_id é recusado antes de qualquer rede.
    O exercício de referência fica nulo aqui e é fixado na importação, quando
    observado no arquivo.
    """
    if type(product_id) is not int or product_id < 1:
        raise ValueError("product_id must be a positive integer")
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        existing = decode(checkpoint.read_bytes())
        if not isinstance(existing, dict) or existing.get("product_id") != product_id:
            raise ValueError("collection.json belongs to another product_id; use a different folder")
    metadata = safe_download(artifact_url(product_id), folder / "artifact.gz", max_bytes)
    collection = {
        "dataset": DATASET,
        "product_id": product_id,
        "url": metadata["url"],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "reference_date": None,
        "access_note": ACCESS_NOTE,
    }
    _write_json(checkpoint, collection)
    return collection


def _collection_metadata(collection) -> dict:
    if not isinstance(collection, dict) or collection.get("dataset") != DATASET:
        raise ValueError("collection_manifest_dataset_mismatch")
    product_id = collection.get("product_id")
    if type(product_id) is not int or product_id < 1:
        raise ValueError("collection_manifest_product_id_invalid")
    url = collection.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("collection_manifest_url_invalid")
    sha256 = collection.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("collection_manifest_sha256_invalid")
    size = collection.get("bytes")
    if type(size) is not int or size < 1:
        raise ValueError("collection_manifest_bytes_invalid")
    collected_at = collection.get("collected_at")
    if not isinstance(collected_at, str) or not collected_at:
        raise ValueError("collection_manifest_collected_at_invalid")
    reference_date = collection.get("reference_date")
    if reference_date is not None and not isinstance(reference_date, str):
        raise ValueError("collection_manifest_reference_date_invalid")
    access_note = collection.get("access_note") or ACCESS_NOTE
    if not isinstance(access_note, str):
        raise ValueError("collection_manifest_access_note_invalid")
    return {"product_id": product_id, "url": url, "sha256": sha256, "bytes": size,
            "collected_at": collected_at, "reference_date": reference_date, "access_note": access_note}


def _verify_artifact(artifact: Path, metadata: dict) -> None:
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("pdde_artifact_missing_or_not_regular")
    if artifact.stat().st_size != metadata["bytes"]:
        raise ValueError("pdde_artifact_size_mismatch")
    sha = hashlib.sha256()
    with artifact.open("rb") as stream:
        for block in iter(lambda: stream.read(_READ_BLOCK), b""):
            sha.update(block)
    if sha.hexdigest() != metadata["sha256"]:
        raise ValueError("pdde_artifact_hash_mismatch")


def _decompress(artifact: Path, compressed_bytes: int) -> tuple[str, str]:
    """Descomprime em memória com teto duro de bytes e recusa razão de bomba.

    Devolve também o encoding aplicado: o artefato oficial é UTF-8 estrito, e o
    fallback cp1252 fica registrado na proveniência em vez de trocar caracteres
    em silêncio.
    """
    limit = min(MAX_DECOMPRESSED_BYTES, compressed_bytes * MAX_COMPRESSION_RATIO)
    buffer, total = bytearray(), 0
    try:
        with gzip.open(artifact, "rb") as stream:
            while True:
                block = stream.read(_READ_BLOCK)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise ValueError("pdde_decompressed_byte_limit_exceeded")
                buffer.extend(block)
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise ValueError("pdde_artifact_decompression_failed") from error
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return buffer.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("pdde_artifact_encoding_unsupported")


def _validate_header(header) -> list[str]:
    if header is None:
        raise ValueError("pdde_header_absent")
    header = [name.strip().lstrip("\ufeff") for name in header]
    if any(not name for name in header) or len(set(header)) != len(header):
        raise ValueError("pdde_header_invalid")
    if not set(REQUIRED_COLUMNS).issubset(header):
        raise ValueError("pdde_header_missing_required_columns")
    return header


def _sanitize(value: str) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(character for character in text if character >= " " or character == "\t").strip()


def _payment_row(header: list[str], fields: list[str], product_id: int, source: dict) -> dict:
    """Valida uma linha; ``alternate_key`` é o hash da tupla + linha completa, usado só em colisão."""
    if len(fields) != len(header):
        raise ValueError("pdde_row_column_count_mismatch")
    raw = dict(zip(header, fields))
    clean = {name: _sanitize(value) for name, value in raw.items()}
    exercise = clean["AN_EXERCICIO"]
    if not re.fullmatch(r"[0-9]{4}", exercise):
        raise ValueError("pdde_row_malformed_exercise")
    school_code = clean["CO_ESCOLA"]
    if not re.fullmatch(r"[0-9]{8}", school_code):
        raise ValueError("pdde_row_malformed_school_code")
    state = clean.get("SG_UF", "")
    if state and not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError("pdde_row_malformed_state")
    municipality_code = clean.get("CO_MUNICIPIO_IBGE", "")
    if municipality_code and not re.fullmatch(r"[0-9]{7}", municipality_code):
        raise ValueError("pdde_row_malformed_municipality_id")
    identity = [str(product_id), exercise, school_code, clean.get("CNPJ_UEX", ""),
                clean.get("DT_INI_VINCULACAO", ""), clean.get("VL_PAGO_TOTAL", "")]
    row_hash = digest(clean)
    return {
        "key": digest(identity) if all(identity) else row_hash,
        "alternate_key": digest(identity + [row_hash]) if all(identity) else None,
        "product_id": product_id,
        "exercise": exercise,
        "state": state or None,
        "municipality_name": clean.get("NO_MUNICIPIO") or None,
        "municipality_code": municipality_code or None,
        "school_code": school_code,
        "recipient_cnpj": clean.get("CNPJ_UEX") or None,
        "recipient_name": clean.get("NO_UEX") or None,
        "values": {name: raw[name] for name in header if name.startswith("VL_")},
        "payload": clean,
        "source": source | {"reference_date": exercise},
    }


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    if not batch:
        return
    lookup = [item["key"] for item in batch]
    lookup.extend(item["alternate_key"] for item in batch if item["alternate_key"] is not None)
    existing = {}
    for chunk in _chunks(lookup, _QUERY_CHUNK):
        for key, payload in session.execute(
                select(PddePayment.key, PddePayment.payload).where(PddePayment.key.in_(chunk))):
            existing[key] = payload
    municipality_codes = sorted({item["municipality_code"] for item in batch if item["municipality_code"]})
    known_municipalities = set()
    for chunk in _chunks(municipality_codes, _QUERY_CHUNK):
        known_municipalities.update(session.scalars(select(Municipality.id).where(Municipality.id.in_(chunk))))
    place_ids = sorted({f"inep:{item['school_code']}" for item in batch})
    known_places = set()
    for chunk in _chunks(place_ids, _QUERY_CHUNK):
        known_places.update(session.scalars(select(Place.id).where(Place.id.in_(chunk))))
    pending = {}
    for item in batch:
        payload = item["payload"]
        candidates = [item["key"]] if item["alternate_key"] is None else [item["key"], item["alternate_key"]]
        matched = False
        for candidate in candidates:
            recorded = pending.get(candidate) if candidate in pending else existing.get(candidate)
            if recorded == payload:
                matched = True
                break
        if matched:
            counts["unchanged"] += 1
            continue
        key = next((candidate for candidate in candidates
                    if candidate not in pending and candidate not in existing), None)
        if key is None:
            raise ValueError("pdde_row_conflict_requires_reconciliation")
        place_id = f"inep:{item['school_code']}"
        session.add(PddePayment(
            key=key, product_id=item["product_id"], exercise=item["exercise"], state=item["state"],
            municipality_name=item["municipality_name"],
            municipality_id=item["municipality_code"] if item["municipality_code"] in known_municipalities else None,
            school_code=item["school_code"],
            school_place_id=place_id if place_id in known_places else None,
            recipient_cnpj=item["recipient_cnpj"], recipient_name=item["recipient_name"],
            values=item["values"], payload=payload, source=item["source"]))
        pending[key] = payload
        counts["created"] += 1
    session.flush()
    batch.clear()


def import_pdde(database: Database, folder: Path, *, batch_size: int = 500,
                max_rows: int = 5_000_000) -> dict:
    """Importa o artefato local; nunca baixa, nunca soma e nunca deduplica em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("max_rows must be a positive integer")
    folder = Path(folder)
    artifact = folder / "artifact.gz"
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    metadata = _collection_metadata(decode(raw_manifest))
    _verify_artifact(artifact, metadata)
    initialize_pdde(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "product_id": metadata["product_id"],
        "url": metadata["url"],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "collected_at": metadata["collected_at"],
        "reference_date": metadata["reference_date"],
        "access_note": metadata["access_note"],
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json, counts=dict(counts))
        session.add(load)
        session.flush()
        load_id = load.id
    try:
        row_source = {"url": metadata["url"], "sha256": metadata["sha256"],
                      "collected_at": metadata["collected_at"]}
        exercises = set()
        with database.session() as session:
            text, encoding = _decompress(artifact, metadata["bytes"])
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
            header = _validate_header(next(reader, None))
            batch: list[dict] = []
            for fields in reader:
                if not fields:
                    continue
                counts["read"] += 1
                if counts["read"] > max_rows:
                    raise ValueError("pdde_row_budget_exceeded")
                try:
                    item = _payment_row(header, fields, metadata["product_id"], row_source)
                except ValueError:
                    counts["rejected"] += 1
                    continue
                exercises.add(item["exercise"])
                batch.append(item)
                if len(batch) >= batch_size:
                    _flush_batch(session, batch, counts)
            _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("pdde_artifact_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("pdde_manifest_changed_during_import")
            reference_date = next(iter(exercises)) if len(exercises) == 1 else None
            source_json["reference_date"] = reference_date
            source_json["encoding"] = encoding
            source_json["encoding_fallback"] = encoding != "utf-8-sig"
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at, load.counts, load.source = "success", now(), dict(counts), source_json
    except Exception as error:
        with database.session() as session:
            load = session.get(Ingestion, load_id)
            if load is not None:
                load.status, load.finished_at = "failed", now()
                load.counts = dict(counts) | {"rolled_back": True}
                load.error = str(error)[:160] if isinstance(error, ValueError) else type(error).__name__
        raise
    return {"status": "imported", "dataset": DATASET, "ingestion_id": load_id,
            "product_id": metadata["product_id"], "reference_date": reference_date,
            "exercises": sorted(exercises), "counts": dict(counts), "encoding": encoding,
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
            "national_catalog_certified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect", help="Baixa o artefato público e grava artifact.gz + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--product-id", type=int, default=DEFAULT_PRODUCT_ID)
    collector.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    importer = commands.add_parser("import", help="Importa o artefato local para o banco operacional")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    importer.add_argument("--max-rows", type=int, default=5_000_000)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_pdde(args.folder, product_id=args.product_id, max_bytes=args.max_bytes)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_pdde(database, args.folder, batch_size=args.batch_size, max_rows=args.max_rows)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

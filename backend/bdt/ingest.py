"""File-first ingestion. No network request or national-coverage claim is implicit."""
from __future__ import annotations
import csv
import hashlib
import io
import ipaddress
import json
import math
import os
import socket
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from sqlalchemy import select
from .domain import MoneyEvent, PlaceInput, Source, brl, decimal_cents, digest, now
from .storage import Database, Finance, Ingestion, Municipality, Place, upsert_place

IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
CNES_URL = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
HOSTS = frozenset({
    "servicodados.ibge.gov.br", "apidadosabertos.saude.gov.br", "download.inep.gov.br",
    "dadosabertos.saude.gov.br", "repositorio.dados.gov.br", "repositorio.transferegov.gestao.gov.br",
    "api-publica.transferegov.gestao.gov.br", "api-publica.obrasgov.gestao.gov.br", "pncp.gov.br",
})

def safe_download(url: str, target: Path, max_bytes: int = 256 * 1024 * 1024, *, allow_no_content: bool = False) -> dict:
    """Operator-only downloader. Use a network-restricted worker, never public HTTP."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise ValueError("Download source is not in the reviewed HTTPS allowlist")
    resolved = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not resolved or any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
        raise ValueError("Source resolves to a non-public address")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part-" + str(uuid4()))
    total, sha = 0, hashlib.sha256()
    try:
        with httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", url, headers={"User-Agent": "BrasilDeTodos/0.1 (+https://github.com/rafaelob/brasildetodos)"}) as response:
                response.raise_for_status()
                no_content = allow_no_content and response.status_code == 204
                if response.status_code != 200 and not no_content:
                    raise ValueError("Expected full HTTP 200 response; redirects require reviewed source configuration")
                with part.open("wb") as handle:
                    for block in response.iter_bytes():
                        total += len(block)
                        if total > max_bytes:
                            raise ValueError("Download exceeds configured byte budget")
                        handle.write(block)
                        sha.update(block)
                if total == 0 and not no_content:
                    raise ValueError("Empty download")
                if no_content and total != 0:
                    raise ValueError("HTTP 204 must not contain a body")
                metadata = {"url": url, "sha256": sha.hexdigest(), "bytes": total, "collected_at": now(), "etag": response.headers.get("etag"), "status_code": response.status_code}
        os.replace(part, target)
        target.with_suffix(target.suffix + ".manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata
    finally:
        part.unlink(missing_ok=True)

def file_source(path: Path, dataset: str, url: str, reference_date: str | None) -> Source:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    return Source(dataset=dataset, url=url, record_id=path.name, reference_date=reference_date, collected_at=now(), snapshot_sha256=sha.hexdigest())

def json_records(path: Path, root: str | None = None) -> list:
    content = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal)
    if root:
        content = content[root]
    if not isinstance(content, list):
        raise ValueError("Expected a JSON array; specify the documented root explicitly")
    return content

def csv_records(path: Path, member: str | None = None, encoding: str = "utf-8-sig", delimiter: str = ";"):
    """Stream one operator-selected CSV; never extract archive paths to disk."""
    archive = None
    if member:
        archive = zipfile.ZipFile(path)
        info = archive.getinfo(member)
        if info.is_dir() or info.file_size > 4 * 1024**3 or info.file_size / max(info.compress_size, 1) > 500:
            archive.close()
            raise ValueError("Archive member exceeds safe processing limits")
        raw = archive.open(info)
    else:
        raw = path.open("rb")
    try:
        with io.TextIOWrapper(raw, encoding=encoding, newline="") as stream:
            yield from csv.DictReader(stream, delimiter=delimiter)
    finally:
        if archive:
            archive.close()

def import_ibge(database: Database, path: Path, source: Source) -> int:
    records = json_records(path)
    if not records:
        raise ValueError("Empty municipality input is not a valid load")
    seen = set()
    with database.session() as session:
        for raw in records:
            code = str(raw["id"])
            if len(code) != 7 or not code.isdigit() or code in seen:
                raise ValueError("Invalid or duplicate municipality ID")
            seen.add(code)
            region = raw.get("microrregiao")
            uf = region["mesorregiao"]["UF"] if region else raw["regiao-imediata"]["regiao-intermediaria"]["UF"]
            row = session.get(Municipality, code) or Municipality(id=code)
            row.name, row.state = raw["nome"], uf["sigla"]
            row.source = source.model_copy(update={"record_id": code}).model_dump()
            session.add(row)
    return len(seen)

def municipality_lookup(database: Database) -> dict[str, tuple[str, str]]:
    """Six-digit mapping is derived only from loaded IBGE identities, never padded."""
    lookup = {}
    with database.session() as session:
        for item in session.scalars(select(Municipality)):
            for key in (item.id, item.id[:6]):
                if key in lookup and lookup[key] != (item.id, item.state):
                    raise ValueError("Ambiguous municipality crosswalk")
                lookup[key] = (item.id, item.state)
    return lookup

def official_id(value: str | int, width: int) -> str:
    if isinstance(value, bool):
        raise ValueError("Boolean identifier")
    raw = str(value).strip()
    if not raw.isdigit() or len(raw) > width:
        raise ValueError("Malformed identifier")
    return raw.zfill(width)

def coordinates(lat, lon):
    try:
        a, b = float(str(lat).replace(",", ".")), float(str(lon).replace(",", "."))
        if math.isfinite(a) and math.isfinite(b) and -35 <= a <= 6 and -75 <= b <= -32:
            return a, b
    except (TypeError, ValueError):
        pass
    return None, None

def cnes_record(raw: dict, source: Source, lookup: dict) -> PlaceInput | None:
    required = {"codigo_cnes", "nome_fantasia", "codigo_municipio", "estabelecimento_faz_atendimento_ambulatorial_sus"}
    if not required.issubset(raw):
        raise ValueError("CNES schema changed: required fields absent")
    sus = str(raw["estabelecimento_faz_atendimento_ambulatorial_sus"]).upper().strip()
    if raw.get("codigo_motivo_desabilitacao_estabelecimento") not in {None, ""} or sus not in {"SIM", "S", "1"}:
        return None
    municipality, state = lookup[str(raw["codigo_municipio"])]
    code = official_id(raw["codigo_cnes"], 7)
    lat, lon = coordinates(raw.get("latitude_estabelecimento_decimo_grau"), raw.get("longitude_estabelecimento_decimo_grau"))
    return PlaceInput(
        id=f"cnes:{code}", kind="health", name=raw["nome_fantasia"], municipality_id=municipality, state=state,
        address=" ".join(str(raw.get(k) or "") for k in ("endereco_estabelecimento", "numero_estabelecimento", "bairro_estabelecimento")).strip(),
        phone=str(raw["numero_telefone_estabelecimento"]) if raw.get("numero_telefone_estabelecimento") else None,
        latitude=lat, longitude=lon, geo_source="CNES" if lat is not None else None,
        declared_services=["sus_outpatient_declared"],
        source=source.model_copy(update={"record_id": code, "reference_date": str(raw.get("data_atualizacao") or source.reference_date or "") or None}),
    )

def inep_record(raw: dict, source: Source, lookup: dict) -> PlaceInput | None:
    required = {"CO_ENTIDADE", "NO_ENTIDADE", "CO_MUNICIPIO", "TP_DEPENDENCIA", "TP_SITUACAO_FUNCIONAMENTO"}
    if not required.issubset(raw):
        raise ValueError("INEP schema changed: reviewed CO_ENTIDADE profile required")
    if str(raw["TP_DEPENDENCIA"]) not in {"1", "2", "3"} or str(raw["TP_SITUACAO_FUNCIONAMENTO"]) != "1":
        return None
    municipality, state = lookup[str(raw["CO_MUNICIPIO"])]
    code = official_id(raw["CO_ENTIDADE"], 8)
    lat, lon = coordinates(raw.get("NU_LATITUDE"), raw.get("NU_LONGITUDE"))
    services = {"IN_INF_CRE": "nursery", "IN_INF_PRE": "preschool", "IN_FUND_AI": "primary", "IN_FUND_AF": "lower_secondary", "IN_MED": "secondary"}
    return PlaceInput(
        id=f"inep:{code}", kind="school", name=raw["NO_ENTIDADE"], municipality_id=municipality, state=state,
        address=" ".join(str(raw.get(k) or "") for k in ("DS_ENDERECO", "NU_ENDERECO", "NO_BAIRRO")).strip(),
        phone=str(raw["NU_TELEFONE"]) if raw.get("NU_TELEFONE") else None,
        latitude=lat, longitude=lon, geo_source="INEP" if lat is not None else None,
        declared_services=[value for key, value in services.items() if str(raw.get(key)) == "1"],
        source=source.model_copy(update={"record_id": code}),
    )

def import_places(database: Database, rows, source: Source, adapter: str) -> dict:
    lookup = municipality_lookup(database)
    run_id, counts = str(uuid4()), Counter()
    with database.session() as session:
        session.add(Ingestion(id=run_id, dataset=source.dataset, source=source.model_dump()))
    try:
        with database.session() as session:
            ids = set()
            for raw in rows:
                counts["read"] += 1
                if adapter == "places":
                    identity = raw["id"]
                    item = PlaceInput.model_validate(raw | {"source": source.model_copy(update={"record_id": identity}).model_dump()})
                else:
                    item = {"cnes": cnes_record, "inep": inep_record}[adapter](raw, source, lookup)
                    identity = adapter + ":" + official_id(raw["codigo_cnes" if adapter == "cnes" else "CO_ENTIDADE"], 7 if adapter == "cnes" else 8)
                if identity in ids:
                    raise ValueError("Duplicate source identity in input")
                ids.add(identity)
                if item is None:
                    counts["excluded"] += 1
                    previous = session.get(Place, identity)
                    if previous and previous.dataset == source.dataset and previous.catalogue_eligible:
                        archived = previous.payload | {"catalogue_eligible": False, "source": source.model_copy(update={"record_id": identity, "reference_date": str(raw.get("data_atualizacao") or source.reference_date or "") or None}).model_dump()}
                        upsert_place(session, PlaceInput.model_validate(archived))
                        counts["withdrawn"] += 1
                    continue
                outcome = upsert_place(session, item)
                counts[outcome] += 1
                counts["without_geometry"] += int(item.latitude is None)
            if counts["read"] == 0:
                raise ValueError("Empty input cannot be published as a successful national load")
            row = session.get(Ingestion, run_id)
            row.status, row.finished_at, row.counts = "completed_file", now(), dict(counts)
        return {"run_id": run_id, "counts": dict(counts), "coverage": "provided_file_only"}
    except Exception as error:
        with database.session() as session:
            row = session.get(Ingestion, run_id)
            row.status, row.finished_at, row.counts = "failed", now(), dict(counts)
            row.error = type(error).__name__ + ": input rejected; inspect locally"
        raise

def import_finance(database: Database, rows, source: Source) -> int:
    """Normalized event format. No facility association is inferred from municipality."""
    count = 0
    with database.session() as session:
        for raw in rows:
            item = MoneyEvent.model_validate(raw | {"source": source.model_copy(update={"record_id": raw["id"]}).model_dump()})
            payload = item.model_dump(mode="json")
            key = digest([item.source.dataset, item.id])
            existing = session.get(Finance, key)
            if existing:
                a = {k: v for k, v in existing.payload.items() if k != "source"}
                b = {k: v for k, v in payload.items() if k != "source"}
                if a != b:
                    raise ValueError("Financial correction requires explicit reconciliation; prior value preserved")
                continue
            session.add(Finance(key=key, municipality_id=item.municipality_id, facility_id=item.facility_id, cents=item.cents, payload=payload))
            count += 1
    return count

def transferegov_rows(rows, columns: dict, *, phase: str, nature: str, perspective: str):
    """Reviewed CSV profile, not a claim of universal Transferegov integration."""
    required = {"id", "municipality_id", "instrument_id", "recipient", "period", "amount"}
    if set(columns) != required:
        raise ValueError("Incomplete or unexpected column mapping")
    for row in rows:
        if not set(columns.values()).issubset(row):
            raise ValueError("Source CSV headers differ from the reviewed profile")
        fields = {field: row[column] for field, column in columns.items()}
        amount = fields.pop("amount")
        yield fields | {"cents": brl(amount), "phase": phase, "nature": nature, "perspective": perspective}

def pncp_contracts(payload: dict) -> list[dict]:
    """Metadata only: a published contract is never converted into a paid event."""
    if not isinstance(payload.get("data"), list):
        raise ValueError("PNCP response requires the documented data array")
    output = []
    for row in payload["data"]:
        output.append({
            "id": row["numeroControlePNCP"], "object": row["objetoContrato"],
            "phase": "contracted", "cents": decimal_cents(row["valorInicial"]),
            "municipality_id": str(row["unidadeOrgao"]["codigoIbge"]),
            "place_id": None, "relation_state": "territorial",
        })
    return output

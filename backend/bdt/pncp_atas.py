"""Atas de registro de preço publicadas na API de consulta do PNCP.

Pode afirmar: as atas retornadas pelo endpoint público
``/api/consulta/v1/atas`` para a janela de vigência e, quando informado, o órgão
(``cnpj``) declarados, exatamente como publicadas — número de controle, número
da ata, compra de origem, órgão e unidade, datas, cancelamento e possibilidade
de adesão — com a URL da página, o SHA-256 do arquivo e a data de coleta. O
envelope (``data``/``totalRegistros``/``totalPaginas``/``numeroPagina``/
``paginasRestantes``/``empty``) é validado em toda página, a aritmética
declarada (``totalPaginas = ceil(totalRegistros/tamanhoPagina)``) é conferida e
uma resposta HTTP 204 só é terminal vazio legítimo quando nenhum total foi
declarado antes (página 1, ou total declarado zero): depois de totais
declarados, o 204 é erro de contrato e nenhum manifesto é gravado. ``complete``
exige a última página declarada alcançada ou o 204 legítimo; qualquer outra
parada é ``bounded`` e permanece visível como parcial. A ordenação não é
garantida; a identidade é o
SHA-256 do ``numeroControlePNCPAta``, nunca a posição na página.

Nunca pode afirmar: fornecedor, valor, município, unidade federativa ou vínculo
territorial — o DTO deste endpoint não publica esses campos e nenhum vínculo é
criado; completude nacional ou ``national_catalog_certified``. A coleta é
recortada pela janela e pelo órgão solicitados, e ``total_registros`` reflete o
declarado pela origem, não uma verificação independente. A importação usa
apenas arquivos e manifestos locais, confere tamanho e SHA-256 de todas as
páginas antes de gravar, só aceita página terminal de zero bytes com totais
declarados zero e nunca inventa valores.

Licença: o PNCP não publica texto de licença explícito para este endpoint
(UNVERIFIED em 2026-09-27); a condição fica registrada no manifesto e no JSON de
origem, sem certificação de redistribuição.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import JSON, Boolean, Column, Integer, String, Text, select

from .domain import cnpj as cnpj_code, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "pncp_atas"
API_URL = "https://pncp.gov.br/api/consulta/v1/atas"
PAGES_DIR = "atas"
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 500
MAX_WINDOW_DAYS = 365
MIN_DELAY_SECONDS = 1.0
COMPLETE_TERMINALS = ("declared_total_pages", "no_content")
LICENSE = ("O PNCP não publica texto de licença explícito para este endpoint "
           "(UNVERIFIED em 2026-09-27); redistribuição não certificada.")
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre apenas as páginas solicitadas do endpoint público de atas do PNCP "
    "para a janela de vigência e o órgão informados; status complete/bounded nunca prova "
    "cobertura nacional nem de todas as atas publicadas, e total_registros reflete o "
    "declarado pela origem, não uma verificação independente."
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_CNPJ = re.compile(r"[A-Z0-9]{14}\Z")


class PncpAta(Base):
    """Uma ata publicada; nenhum fornecedor, valor ou vínculo territorial é criado."""
    __tablename__ = "pncp_atas"
    key = Column(String(64), primary_key=True)
    control = Column(String(80), nullable=False, index=True)
    ata_number = Column(String(60), nullable=False, index=True)
    compra_control = Column(String(80), nullable=False, index=True)
    ano_ata = Column(Integer, nullable=False)
    orgao_cnpj = Column(String(14), nullable=False, index=True)
    orgao_nome = Column(String(300), nullable=False)
    unit_code = Column(String(20), nullable=False, index=True)
    unit_name = Column(String(300), nullable=False)
    orgao_cnpj_subrogado = Column(String(14))
    orgao_nome_subrogado = Column(String(300))
    unit_code_subrogado = Column(String(20))
    unit_name_subrogado = Column(String(300))
    usuario = Column(String(200))
    objeto_text = Column(Text)
    cancelado = Column(Boolean, nullable=False)
    data_cancelamento = Column(String(40))
    assinado_em = Column(String(40), nullable=False)
    vigencia_inicio = Column(String(40), nullable=False)
    vigencia_fim = Column(String(40), nullable=False)
    publicado_em = Column(String(40), nullable=False)
    incluido_em = Column(String(40), nullable=False)
    atualizado_em = Column(String(40), nullable=False)
    atualizado_global_em = Column(String(40), nullable=False)
    possibilidade_adesao = Column(Boolean)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_pncp_atas(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    PncpAta.__table__.create(database.engine, checkfirst=True)


def page_url(page: int, window_from: str, window_to: str, page_size: int,
             cnpj: str | None = None) -> str:
    query = {"dataInicial": window_from.replace("-", ""), "dataFinal": window_to.replace("-", ""),
             "pagina": page, "tamanhoPagina": page_size}
    if cnpj is not None:
        query["cnpj"] = cnpj
    return f"{API_URL}?{urlencode(query)}"


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _window_day(value, field: str) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value.strip()):
        raise ValueError(f"{field} must be a YYYY-MM-DD date")
    text = value.strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field} must be a YYYY-MM-DD date") from None
    return text


def _validated_plan(*, window_from, window_to, cnpj, page_size, max_pages, delay_seconds) -> dict:
    """Valida o plano antes de qualquer rede; nunca inventa janela, órgão ou página."""
    if type(page_size) is not int or not MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("page_size must be an integer between 10 and 500")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError("delay_seconds must be at least 1.0 second")
    if cnpj is None:
        code = None
    else:
        try:
            code = cnpj_code(cnpj)
        except ValueError:
            raise ValueError("cnpj must be a 14-character CNPJ") from None
    window_from = _window_day(window_from, "--from")
    window_to = _window_day(window_to, "--to")
    if window_from > window_to:
        raise ValueError("window_from must not be after window_to")
    if (date.fromisoformat(window_to) - date.fromisoformat(window_from)).days > MAX_WINDOW_DAYS:
        raise ValueError("window must be at most 365 days")
    return {"window_from": window_from, "window_to": window_to, "cnpj": code,
            "page_size": page_size, "max_pages": max_pages, "delay_seconds": float(delay_seconds)}


def _error_message(response) -> str:
    """Lê a mensagem do corpo quando ainda disponível; o stream real chega fechado e degrada."""
    try:
        raw = response.read()
    except (httpx.StreamError, ValueError):
        return ""
    if not raw:
        return ""
    try:
        payload = decode(raw)
    except ValueError:
        return ""
    if isinstance(payload, dict):
        for key in ("message", "mensagem", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return ": " + value.strip()[:160]
    return ""


def _download(url: str, path: Path) -> dict:
    """Baixa pela allowlist, aceita 204 vazio e traduz 400/422 em erro de contrato."""
    try:
        return safe_download(url, path, allow_no_content=True)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        message = _error_message(error.response)
        if status in {400, 422}:
            raise ValueError(f"pncp_atas_contract_error_http_{status}{message}") from error
        raise ValueError(f"pncp_atas_http_error_{status}{message}") from error


def _reviewed_envelope(payload, page_size: int, page: int) -> tuple[list, int, int, int]:
    """Confere o envelope declarado e a aritmética documentada de paginação."""
    if (not isinstance(payload, dict) or not isinstance(payload.get("data"), list)
            or type(payload.get("totalRegistros")) is not int or payload["totalRegistros"] < 0
            or type(payload.get("totalPaginas")) is not int or payload["totalPaginas"] < 0
            or type(payload.get("numeroPagina")) is not int or payload["numeroPagina"] != page
            or type(payload.get("paginasRestantes")) is not int
            or type(payload.get("empty")) is not bool):
        raise ValueError("pncp_atas_page_schema_changed")
    rows = payload["data"]
    registros = payload["totalRegistros"]
    paginas = payload["totalPaginas"]
    remaining = payload["paginasRestantes"]
    if (len(rows) > page_size
            or paginas != (registros + page_size - 1) // page_size
            or remaining != paginas - page
            or (registros == 0 and rows)):
        raise ValueError("pncp_atas_page_totals_invalid")
    return rows, registros, paginas, remaining


def collect_pncp_atas(folder: Path, *, window_from, window_to, cnpj=None, page_size: int = 500,
                      max_pages: int = 5, delay_seconds: float = 1.0) -> dict:
    """Baixa páginas com o baixador allowlisted e grava ``atas/page-<i>.json``.

    Sem autenticação e sem limite de taxa documentado: o intervalo entre páginas
    é obrigatório e nunca inferior a 1 segundo. Reutilizar a pasta para outro
    plano é recusado antes de qualquer rede. ``complete`` exige a última página
    declarada alcançada ou o HTTP 204 legítimo (sem totais declarados antes);
    um 204 posterior a totais declarados é erro de contrato e não grava
    manifesto. Caso contrário o status é ``bounded``. Uma página nunca é pedida
    além de ``totalPaginas``.
    """
    plan = _validated_plan(window_from=window_from, window_to=window_to, cnpj=cnpj,
                           page_size=page_size, max_pages=max_pages, delay_seconds=delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("pncp_atas_collection_manifest_unreadable") from error
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET or existing.get("plan") != plan:
            raise ValueError("pncp_atas_collection_manifest_plan_mismatch; use a different folder")
    pages_dir = folder / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    started_at = now()
    entries: list[dict] = []
    total_registros = total_paginas = None
    terminal = None
    page = 1
    while page <= plan["max_pages"]:
        if page > 1:
            time.sleep(plan["delay_seconds"])
        url = page_url(page, plan["window_from"], plan["window_to"], plan["page_size"], plan["cnpj"])
        path = pages_dir / f"page-{page}.json"
        metadata = _download(url, path)
        entries.append({"index": page, "url": metadata["url"], "sha256": metadata["sha256"],
                        "bytes": metadata["bytes"]})
        if metadata.get("status_code") == 204:
            # 204 só é terminal vazio legítimo quando nenhum total foi declarado antes.
            if total_registros not in (None, 0):
                raise ValueError("pncp_atas_no_content_after_declared_totals")
            terminal = "no_content"
            if total_registros is None:
                total_registros, total_paginas = 0, 0
            break
        payload = decode(path.read_bytes())
        rows, declared_registros, declared_paginas, _remaining = _reviewed_envelope(
            payload, plan["page_size"], page)
        if total_registros is not None and (declared_registros != total_registros
                                            or declared_paginas != total_paginas):
            raise ValueError("pncp_atas_page_totals_changed")
        total_registros, total_paginas = declared_registros, declared_paginas
        if not rows:
            terminal = "empty_page"
            break
        if page >= declared_paginas:
            terminal = "declared_total_pages"
            break
        page += 1
    else:
        terminal = "max_pages_bound"
    status = "complete" if terminal in COMPLETE_TERMINALS else "bounded"
    collection = {
        "dataset": DATASET,
        "url": API_URL,
        "license": LICENSE,
        "plan": plan,
        "started_at": started_at,
        "finished_at": now(),
        "status": status,
        "terminal": terminal,
        "pages": entries,
        "total_registros": total_registros,
        "total_paginas": total_paginas,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    _write_json(checkpoint, collection)
    return collection


def _reviewed_manifest(manifest) -> dict:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo de completo."""
    if not isinstance(manifest, dict) or manifest.get("dataset") != DATASET:
        raise ValueError("pncp_atas_collection_manifest_dataset_mismatch")
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("pncp_atas_collection_manifest_plan_invalid")
    try:
        reviewed = _validated_plan(window_from=plan.get("window_from"), window_to=plan.get("window_to"),
                                   cnpj=plan.get("cnpj"), page_size=plan.get("page_size"),
                                   max_pages=plan.get("max_pages"),
                                   delay_seconds=plan.get("delay_seconds"))
    except ValueError as error:
        raise ValueError("pncp_atas_collection_manifest_plan_invalid") from error
    if reviewed != plan:
        raise ValueError("pncp_atas_collection_manifest_plan_invalid")
    status = manifest.get("status")
    terminal = manifest.get("terminal")
    if status not in {"complete", "bounded"} or not isinstance(terminal, str) or not terminal:
        raise ValueError("pncp_atas_collection_manifest_status_invalid")
    if status == "complete" and terminal not in COMPLETE_TERMINALS:
        raise ValueError("pncp_atas_collection_complete_without_terminal_evidence")
    entries = manifest.get("pages")
    if not isinstance(entries, list) or not entries or len(entries) > plan["max_pages"]:
        raise ValueError("pncp_atas_collection_manifest_pages_invalid")
    finished_at = manifest.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        raise ValueError("pncp_atas_collection_manifest_finished_at_invalid")
    total_registros = manifest.get("total_registros")
    total_paginas = manifest.get("total_paginas")
    if total_registros is not None and (type(total_registros) is not int or total_registros < 0):
        raise ValueError("pncp_atas_collection_manifest_totals_invalid")
    if total_paginas is not None and (type(total_paginas) is not int or total_paginas < 0):
        raise ValueError("pncp_atas_collection_manifest_totals_invalid")
    return {"plan": plan, "status": status, "terminal": terminal, "entries": entries,
            "finished_at": finished_at, "total_registros": total_registros,
            "total_paginas": total_paginas}


def _verified_pages(folder: Path, reviewed: dict, plan: dict) -> list[tuple[dict, dict | None]]:
    """Confere tamanho e SHA-256 de cada página antes de publicar qualquer linha."""
    pages_dir = folder / PAGES_DIR
    entries = reviewed["entries"]
    status, terminal = reviewed["status"], reviewed["terminal"]
    expected_registros, expected_paginas = reviewed["total_registros"], reviewed["total_paginas"]
    declared_registros = declared_paginas = None
    verified: list[tuple[dict, dict | None]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("pncp_atas_page_manifest_invalid")
        index = entry.get("index")
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        if type(index) is not int or index != position + 1:
            raise ValueError("pncp_atas_page_manifest_invalid")
        expected_url = page_url(index, plan["window_from"], plan["window_to"],
                                plan["page_size"], plan["cnpj"])
        if not isinstance(url, str) or url != expected_url:
            raise ValueError("pncp_atas_page_url_invalid")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("pncp_atas_page_sha256_invalid")
        if type(size) is not int or size < 0:
            raise ValueError("pncp_atas_page_bytes_invalid")
        path = pages_dir / f"page-{index}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("pncp_atas_page_missing_or_not_regular")
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("pncp_atas_page_integrity_failure")
        if size == 0:
            if position != len(entries) - 1 or status != "complete" or terminal != "no_content":
                raise ValueError("pncp_atas_empty_page_without_terminal_evidence")
            # Zero bytes só é terminal legítimo sem total declarado que o contradiga.
            if (declared_registros not in (None, 0) or declared_paginas not in (None, 0)
                    or expected_registros not in (None, 0) or expected_paginas not in (None, 0)):
                raise ValueError("pncp_atas_no_content_after_declared_totals")
            verified.append((entry, None))
            continue
        payload = decode(raw)
        rows, registros, paginas, _remaining = _reviewed_envelope(payload, plan["page_size"], index)
        if declared_registros is None:
            declared_registros, declared_paginas = registros, paginas
        elif declared_registros != registros or declared_paginas != paginas:
            raise ValueError("pncp_atas_page_totals_changed")
        if expected_registros is not None and registros != expected_registros:
            raise ValueError("pncp_atas_page_totals_changed")
        if expected_paginas is not None and paginas != expected_paginas:
            raise ValueError("pncp_atas_page_totals_changed")
        if (status == "complete" and position == len(entries) - 1
                and not (index >= paginas or not rows)):
            raise ValueError("pncp_atas_collection_complete_without_terminal_evidence")
        verified.append((entry, payload))
    return verified


def _required_text(value, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pncp_atas_row_missing_{field}")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return text


def _optional_text(value, field: str, limit: int | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    text = value.strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return text


def _required_date(value, field: str) -> str:
    """Aceita apenas a data ``yyyy-MM-dd`` como servida; carimbo com hora é mudança de schema."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pncp_atas_row_missing_{field}")
    text = value.strip()
    if not _DATE.fullmatch(text):
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"pncp_atas_row_malformed_{field}") from None
    return text


def _optional_date(value, field: str) -> str | None:
    if value is None:
        return None
    return _required_date(value, field)


def _required_int(value, field: str) -> int:
    if value is None:
        raise ValueError(f"pncp_atas_row_missing_{field}")
    if type(value) is not int:
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return value


def _required_bool(value, field: str) -> bool:
    if value is None:
        raise ValueError(f"pncp_atas_row_missing_{field}")
    if type(value) is not bool:
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return value


def _optional_bool(value, field: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return value


def _required_cnpj(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pncp_atas_row_missing_{field}")
    text = value.strip()
    if not _CNPJ.fullmatch(text):
        raise ValueError(f"pncp_atas_row_malformed_{field}")
    return text


def _optional_cnpj(value, field: str) -> str | None:
    if value is None:
        return None
    return _required_cnpj(value, field)


def _ata_row(raw, source: dict) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca valor inventado."""
    if not isinstance(raw, dict):
        raise ValueError("pncp_atas_row_not_object")
    control = _required_text(raw.get("numeroControlePNCPAta"), "numero_controle", 80)
    return {
        "key": hashlib.sha256(control.encode("utf-8")).hexdigest(),
        "control": control,
        "ata_number": _required_text(raw.get("numeroAtaRegistroPreco"), "ata_number", 60),
        "compra_control": _required_text(raw.get("numeroControlePNCPCompra"), "compra_control", 80),
        "ano_ata": _required_int(raw.get("anoAta"), "ano_ata"),
        "orgao_cnpj": _required_cnpj(raw.get("cnpjOrgao"), "orgao_cnpj"),
        "orgao_nome": _required_text(raw.get("nomeOrgao"), "orgao_nome", 300),
        "unit_code": _required_text(raw.get("codigoUnidadeOrgao"), "unit_code", 20),
        "unit_name": _required_text(raw.get("nomeUnidadeOrgao"), "unit_name", 300),
        "orgao_cnpj_subrogado": _optional_cnpj(raw.get("cnpjOrgaoSubrogado"), "orgao_cnpj_subrogado"),
        "orgao_nome_subrogado": _optional_text(raw.get("nomeOrgaoSubrogado"), "orgao_nome_subrogado", 300),
        "unit_code_subrogado": _optional_text(raw.get("codigoUnidadeOrgaoSubrogado"), "unit_code_subrogado", 20),
        "unit_name_subrogado": _optional_text(raw.get("nomeUnidadeOrgaoSubrogado"), "unit_name_subrogado", 300),
        "usuario": _optional_text(raw.get("usuario"), "usuario", 200),
        "objeto_text": _optional_text(raw.get("objetoContratacao"), "objeto"),
        "cancelado": _required_bool(raw.get("cancelado"), "cancelado"),
        "data_cancelamento": _optional_date(raw.get("dataCancelamento"), "data_cancelamento"),
        "assinado_em": _required_date(raw.get("dataAssinatura"), "data_assinatura"),
        "vigencia_inicio": _required_date(raw.get("vigenciaInicio"), "vigencia_inicio"),
        "vigencia_fim": _required_date(raw.get("vigenciaFim"), "vigencia_fim"),
        "publicado_em": _required_date(raw.get("dataPublicacaoPncp"), "data_publicacao"),
        "incluido_em": _required_date(raw.get("dataInclusao"), "data_inclusao"),
        "atualizado_em": _required_date(raw.get("dataAtualizacao"), "data_atualizacao"),
        "atualizado_global_em": _required_date(raw.get("dataAtualizacaoGlobal"),
                                               "data_atualizacao_global"),
        "possibilidade_adesao": _optional_bool(raw.get("possibilidadeAdesao"), "possibilidade_adesao"),
        "payload": raw,
        "source": dict(source),
    }


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Uma transação por lote: o lote inteiro grava ou volta atrás junto."""
    keys = [item["key"] for item in batch]
    existing = {}
    for key, payload in session.execute(
            select(PncpAta.key, PncpAta.payload).where(PncpAta.key.in_(keys))):
        existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        key = item["key"]
        recorded = pending[key] if key in pending else existing.get(key)
        if recorded is not None and recorded == item["payload"]:
            counts["unchanged"] += 1
            continue
        if recorded is not None:
            raise ValueError("pncp_atas_row_conflict_requires_reconciliation")
        session.add(PncpAta(
            key=key, control=item["control"], ata_number=item["ata_number"],
            compra_control=item["compra_control"], ano_ata=item["ano_ata"],
            orgao_cnpj=item["orgao_cnpj"], orgao_nome=item["orgao_nome"],
            unit_code=item["unit_code"], unit_name=item["unit_name"],
            orgao_cnpj_subrogado=item["orgao_cnpj_subrogado"],
            orgao_nome_subrogado=item["orgao_nome_subrogado"],
            unit_code_subrogado=item["unit_code_subrogado"],
            unit_name_subrogado=item["unit_name_subrogado"], usuario=item["usuario"],
            objeto_text=item["objeto_text"], cancelado=item["cancelado"],
            data_cancelamento=item["data_cancelamento"], assinado_em=item["assinado_em"],
            vigencia_inicio=item["vigencia_inicio"], vigencia_fim=item["vigencia_fim"],
            publicado_em=item["publicado_em"], incluido_em=item["incluido_em"],
            atualizado_em=item["atualizado_em"], atualizado_global_em=item["atualizado_global_em"],
            possibilidade_adesao=item["possibilidade_adesao"], payload=item["payload"],
            source=item["source"]))
        pending[key] = item["payload"]
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_pncp_atas(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa páginas e manifesto locais; nunca baixa, nunca inventa e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    reviewed = _reviewed_manifest(decode(raw_manifest))
    plan, status, terminal = reviewed["plan"], reviewed["status"], reviewed["terminal"]
    entries, finished_at = reviewed["entries"], reviewed["finished_at"]
    initialize_pncp_atas(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "url": API_URL,
        "collected_at": finished_at,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "window": {"from": plan["window_from"], "to": plan["window_to"]},
        "cnpj": plan["cnpj"],
        "plan": plan,
        "collection_status": status,
        "terminal": terminal,
        "pages": len(entries),
        "total_registros": reviewed["total_registros"],
        "total_paginas": reviewed["total_paginas"],
        "license": LICENSE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json)
        session.add(load)
        session.flush()
        load_id = load.id
    batch: list[dict] = []
    try:
        # Uma única transação para as linhas: qualquer erro volta com o lote inteiro,
        # sem deixar registros parciais commitados.
        with database.session() as session:
            for entry, payload in _verified_pages(folder, reviewed, plan):
                if payload is None:
                    continue
                page_source = {"url": entry["url"], "sha256": entry["sha256"],
                               "collected_at": finished_at}
                for raw in payload["data"]:
                    counts["read"] += 1
                    try:
                        item = _ata_row(raw, page_source)
                    except ValueError:
                        counts["rejected"] += 1
                        continue
                    batch.append(item)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts)
            if batch:
                _flush_batch(session, batch, counts)
            if counts["read"] == 0 and not (terminal == "no_content"
                                            or reviewed["total_registros"] == 0):
                raise ValueError("pncp_atas_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("pncp_atas_manifest_changed_during_import")
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
        "counts": dict(counts),
        "collection_status": status,
        "collection_terminal": terminal,
        "pages": len(entries),
        "window": {"from": plan["window_from"], "to": plan["window_to"]},
        "cnpj": plan["cnpj"],
        "manifest_sha256": source_json["manifest_sha256"],
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa páginas públicas e grava atas/page-<i>.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--from", dest="window_from", required=True, metavar="YYYY-MM-DD")
    collector.add_argument("--to", dest="window_to", required=True, metavar="YYYY-MM-DD")
    collector.add_argument("--cnpj")
    collector.add_argument("--page-size", type=int, default=500)
    collector.add_argument("--max-pages", type=int, default=5)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa páginas locais com hashes verificados")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_pncp_atas(args.folder, window_from=args.window_from,
                                   window_to=args.window_to, cnpj=args.cnpj,
                                   page_size=args.page_size, max_pages=args.max_pages,
                                   delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_pncp_atas(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

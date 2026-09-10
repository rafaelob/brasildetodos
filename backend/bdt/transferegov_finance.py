# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalized Transferegov financial integration.

Parses official SICONV agreement, amendment, disbursement, and municipality crosswalk tables.
Preserves negative amendments, distinguishes signed instruments from pre-agreements,
keeps disbursements separate from commitments/agreed ceilings, and excludes personal/bank details.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from typing import Iterable, Iterator

from .domain import MoneyEvent, Source, digest, fold, now
from .storage import Database, Finance, Ingestion, Municipality

REQUIRED_CONVENIO = frozenset({
    'NR_CONVENIO', 'IND_ASSINADO', 'VL_GLOBAL_CONV', 'VL_REPASSE_CONV',
    'DIA_ASSIN_CONV', 'ANO', 'SIT_CONVENIO'
})
REQUIRED_ADITIVO = frozenset({
    'NR_CONVENIO', 'NUMERO_TA', 'TIPO_TA', 'VL_GLOBAL_TA', 'DT_ASSINATURA_TA'
})
REQUIRED_DESEMBOLSO = frozenset({
    'ID_DESEMBOLSO', 'NR_CONVENIO', 'DATA_DESEMBOLSO', 'VL_DESEMBOLSADO'
})
REQUIRED_CROSSWALK = frozenset({
    'NR_CONVENIO', 'COD_MUNIC_IBGE', 'NM_PROPONENTE'
})

EXCLUDED_SENSITIVE_KEYS = frozenset({
    'CPF', 'CONTA', 'BANCO', 'AGENCIA', 'NR_SIAFI', 'UG_EMITENTE_DH',
    'OBSERVACAO_DH', 'CD_IDENTIF_PROPONENTE'
})


def public_finance_payload(raw: MoneyEvent | dict) -> dict:
    """Drop identity/bank columns from a public finance projection. Never a phase total."""
    payload = raw.model_dump(mode='json') if isinstance(raw, MoneyEvent) else dict(raw)
    excluded = {key.upper() for key in EXCLUDED_SENSITIVE_KEYS}
    return {key: value for key, value in payload.items() if str(key).upper() not in excluded}


def parse_date_to_iso(text: str | None, fallback_year: str | None = None) -> str:
    """Strict date conversion to YYYY-MM-DD or YYYY-MM."""
    if text:
        raw = text.strip()
        # Format DD/MM/YYYY
        match_br = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', raw)
        if match_br:
            d, m, y = match_br.groups()
            return f'{y}-{m}-{d}'
        # Format YYYY-MM-DD
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            return raw
        # Format YYYY-MM
        if re.fullmatch(r'\d{4}-\d{2}', raw):
            return raw
        # Format YYYY
        if re.fullmatch(r'\d{4}', raw):
            return f'{raw}-01-01'
    if fallback_year and re.fullmatch(r'\d{4}', fallback_year.strip()):
        return f'{fallback_year.strip()}-01-01'
    raise ValueError(f'invalid_date_format:{text}')


def parse_brl_cents(value: str | int | float | None) -> int:
    """Parse Brazilian currency string into integer cents. Supports negative amounts."""
    if value is None:
        return 0
    raw = str(value).replace('\u00a0', ' ').strip()
    if not raw or raw == '0' or raw == '0,00' or raw == '0.00':
        return 0
    raw = re.sub(r'^R\$\s*', '', raw).strip()
    # Match standard Brazilian format: -?123.456,78 or -?123456,78
    if re.fullmatch(r'-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}', raw):
        cleaned = raw.replace('.', '').replace(',', '.')
        return int(Decimal(cleaned) * 100)
    # Match plain integer or decimal without thousand separator: -?123456 or -?123456.78
    if re.fullmatch(r'-?\d+(?:\.\d{1,2})?', raw):
        return int(Decimal(raw) * 100)
    raise ValueError(f'ambiguous_brl_amount:{value}')


def load_municipality_crosswalk(rows: Iterable[dict[str, str]], lookup: dict[str, tuple[str, str]] | None = None) -> dict[str, tuple[str, str]]:
    """Load mapping from NR_CONVENIO to (municipality_id, recipient_name)."""
    crosswalk: dict[str, tuple[str, str]] = {}
    for row in rows:
        if not REQUIRED_CROSSWALK.issubset(row):
            raise ValueError('missing_crosswalk_required_columns')
        nr = row['NR_CONVENIO'].strip()
        code = row['COD_MUNIC_IBGE'].strip()
        recipient = row['NM_PROPONENTE'].strip()
        if not nr or not code:
            continue
        # Normalize code to 7 digits
        if len(code) == 6 and lookup and code in lookup:
            code = lookup[code][0]
        elif len(code) != 7 or not code.isdigit():
            continue
        if lookup and code not in lookup:
            continue
        clean_recipient = recipient[:200] if recipient else 'Município'
        crosswalk[nr] = (code, clean_recipient)
    return crosswalk


def normalize_agreements(rows: Iterable[dict[str, str]], crosswalk: dict[str, tuple[str, str]], source: Source) -> Iterator[MoneyEvent]:
    """Normalize signed agreements into agreed MoneyEvents. Excludes pre-agreements."""
    seen_ids: set[str] = set()
    for row in rows:
        if not REQUIRED_CONVENIO.issubset(row):
            raise ValueError('missing_convenio_required_columns')
        nr = row['NR_CONVENIO'].strip()
        if not nr or nr in seen_ids:
            continue
        signed = row['IND_ASSINADO'].strip().upper()
        # Only signed instruments; pre-agreements are not signed contracts
        if signed != 'SIM':
            continue
        # Orphan check: must have resolved municipality in crosswalk
        if nr not in crosswalk:
            continue
        municipality_id, recipient = crosswalk[nr]
        try:
            cents = parse_brl_cents(row.get('VL_GLOBAL_CONV'))
        except ValueError:
            continue
        if cents <= 0:
            continue
        try:
            date_iso = parse_date_to_iso(row.get('DIA_ASSIN_CONV'), row.get('ANO'))
        except ValueError:
            continue
        period = date_iso[:7] if len(date_iso) >= 7 else date_iso[:4]
        seen_ids.add(nr)
        yield MoneyEvent(
            id=f'transferegov:agreement:{nr}',
            source=source.model_copy(update={'record_id': f'transferegov:agreement:{nr}'}),
            municipality_id=municipality_id,
            instrument_id=nr,
            phase='agreed',
            cents=cents,
            currency='BRL',
            period=period,
            recipient=recipient,
            perspective='federal',
            nature='estimate',
            facility_id=None,
            relation_state='territorial',
            evidence=None,
        )


def normalize_amendments(rows: Iterable[dict[str, str]], crosswalk: dict[str, tuple[str, str]], source: Source) -> Iterator[MoneyEvent]:
    """Normalize amendments, preserving negative adjustments (supressões) as negative cents."""
    seen_ids: set[str] = set()
    for row in rows:
        if not REQUIRED_ADITIVO.issubset(row):
            raise ValueError('missing_aditivo_required_columns')
        nr = row['NR_CONVENIO'].strip()
        ta_num = row['NUMERO_TA'].strip()
        if not nr or not ta_num or nr not in crosswalk:
            continue
        try:
            cents = parse_brl_cents(row.get('VL_GLOBAL_TA'))
        except ValueError:
            continue
        # Administrative-only amendments (e.g. prazo) with zero financial adjustment are omitted
        if cents == 0:
            continue
        try:
            date_iso = parse_date_to_iso(row.get('DT_ASSINATURA_TA'))
        except ValueError:
            continue
        period = date_iso[:7] if len(date_iso) >= 7 else date_iso[:4]
        municipality_id, recipient = crosswalk[nr]
        clean_num = re.sub(r'[^A-Za-z0-9_-]', '-', ta_num)
        event_id = f'transferegov:amendment:{nr}:{clean_num}'
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        yield MoneyEvent(
            id=event_id,
            source=source.model_copy(update={'record_id': event_id}),
            municipality_id=municipality_id,
            instrument_id=nr,
            phase='agreed',
            cents=cents,
            currency='BRL',
            period=period,
            recipient=recipient,
            perspective='federal',
            nature='event',
            facility_id=None,
            relation_state='territorial',
            evidence=None,
        )


def normalize_disbursements(rows: Iterable[dict[str, str]], crosswalk: dict[str, tuple[str, str]], source: Source) -> Iterator[MoneyEvent]:
    """Normalize actual disbursements into transferred MoneyEvents."""
    seen_ids: set[str] = set()
    for row in rows:
        if not REQUIRED_DESEMBOLSO.issubset(row):
            raise ValueError('missing_desembolso_required_columns')
        disb_id = row['ID_DESEMBOLSO'].strip()
        nr = row['NR_CONVENIO'].strip()
        if not disb_id or not nr or nr not in crosswalk:
            continue
        try:
            cents = parse_brl_cents(row.get('VL_DESEMBOLSADO'))
        except ValueError:
            continue
        if cents <= 0:
            continue
        try:
            date_iso = parse_date_to_iso(row.get('DATA_DESEMBOLSO'))
        except ValueError:
            continue
        period = date_iso[:7] if len(date_iso) >= 7 else date_iso[:4]
        municipality_id, recipient = crosswalk[nr]
        event_id = f'transferegov:disbursement:{disb_id}'
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        yield MoneyEvent(
            id=event_id,
            source=source.model_copy(update={'record_id': event_id}),
            municipality_id=municipality_id,
            instrument_id=nr,
            phase='transferred',
            cents=cents,
            currency='BRL',
            period=period,
            recipient=recipient,
            perspective='federal',
            nature='event',
            facility_id=None,
            relation_state='territorial',
            evidence=None,
        )


def import_transferegov_financial(database: Database, events: Iterable[MoneyEvent], source: Source, *, batch_size: int = 500) -> dict:
    """Transactionally import normalized MoneyEvents into the finance table."""
    counts = {'agreed': 0, 'amendments': 0, 'transferred': 0, 'total': 0, 'unchanged': 0}
    if batch_size < 1:
        raise ValueError('batch_size_must_be_positive')
    with database.session() as session:
        seen = 0
        for event in events:
            payload = public_finance_payload(event)
            key = digest([event.source.dataset, event.id])
            existing = session.get(Finance, key)
            if existing:
                a = {k: v for k, v in existing.payload.items() if k != 'source'}
                b = {k: v for k, v in payload.items() if k != 'source'}
                if a != b:
                    raise ValueError(f'Financial correction requires explicit reconciliation for {event.id}')
                counts['unchanged'] += 1
            else:
                session.add(Finance(
                    key=key,
                    municipality_id=event.municipality_id,
                    facility_id=event.facility_id,
                    cents=event.cents,
                    payload=payload,
                ))
                if ':agreement:' in event.id:
                    counts['agreed'] += 1
                elif ':amendment:' in event.id:
                    counts['amendments'] += 1
                elif ':disbursement:' in event.id:
                    counts['transferred'] += 1
                counts['total'] += 1
            seen += 1
            if seen % batch_size == 0:
                session.flush()

        run_id = digest(['transferegov_financial_import', source.snapshot_sha256, now()])[:36]
        session.add(Ingestion(
            id=run_id,
            dataset='transferegov',
            started_at=now(),
            finished_at=now(),
            status='success',
            counts=dict(counts),
            source=source.model_dump(mode='json'),
        ))
    return counts

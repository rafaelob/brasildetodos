"""Reviewed official metadata profiles; no inferred facilities or paid events.

Schemas inspected from each publisher on 2026-09-06. A proposal is not a signed
instrument, buyer municipality is not execution location, and planned amounts
are never converted to disbursements. Unknown fields are not copied publicly.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlencode

from .domain import Source, cnpj, decimal_cents
from .evidence import ResourceInput, MAX_PNCP_OBJECT_CHARS
from .sync import PagePlan
from .resource_money import metadata_amount
from .resource_diagnostics import ResourceTextError

Profile = Literal['pncp_contracts', 'transferegov_special_plans', 'obrasgov_projects']
PROFILES = {
    'pncp_contracts': ('https://pncp.gov.br/api/consulta/v1/contratos', 'numeroControlePNCP'),
    'transferegov_special_plans': ('https://api-publica.transferegov.gestao.gov.br/especiais/planos-acao-especiais', 'id_plano_acao'),
    'obrasgov_projects': ('https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento', 'id_projeto_investimento'),
}
STATES = frozenset('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())


def text(value, *, limit=4000, required=False, field="unspecified"):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ResourceTextError(field, value, limit)
    return value.strip()


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('invalid_resource_identity')
    result = str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9._/-]{1,150}', result):
        raise ValueError('invalid_resource_identity')
    return result


def date_value(value, *, timestamp=False):
    if value is None:
        return None
    value = text(value, limit=80, required=True, field="timestamp")
    try:
        if timestamp:
            if 'T' not in value:
                raise ValueError()
            datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            date.fromisoformat(value)
    except ValueError:
        raise ValueError('invalid_resource_date') from None
    return value


def money(value):
    if value is None:
        return None
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError('money_requires_decimal_json_not_float')
    try:
        cents = decimal_cents(value)
    except (ValueError, InvalidOperation):
        raise ValueError('invalid_decimal_resource_amount') from None
    if cents < 0 or cents > 9_007_199_254_740_991:
        raise ValueError('resource_amount_out_of_range')
    return cents


def require(row, fields):
    if not isinstance(row, dict) or not set(fields).issubset(row):
        raise ValueError('resource_schema_changed')


def collection_plan(profile: Profile, *, start=None, end=None, year=None, identity=None,
                    updates=False, page_size=100, max_pages=100) -> PagePlan:
    if profile not in PROFILES:
        raise ValueError('unknown_resource_profile')
    base, key = PROFILES[profile]
    params = {}
    if profile == 'pncp_contracts':
        for value in (start, end):
            if not isinstance(value, str) or not re.fullmatch(r'\d{8}', value):
                raise ValueError('pncp_dates_require_yyyymmdd')
            datetime.strptime(value, '%Y%m%d')
        if start > end or (datetime.strptime(end, '%Y%m%d') - datetime.strptime(start, '%Y%m%d')).days > 31:
            raise ValueError('pncp_window_max_32_days')
        if year is not None or not 10 <= page_size <= 500:
            raise ValueError('invalid_pncp_parameters')
        if updates:
            base += '/atualizacao'
        params = {'dataInicial': start, 'dataFinal': end}
        if identity is not None:
            params['cnpjOrgao'] = cnpj(identity)
        names = ('tamanhoPagina', 'totalPaginas', 'totalRegistros', 'numeroPagina')
    else:
        if start or end or updates or not 1 <= page_size <= 200:
            raise ValueError('invalid_resource_parameters')
        if year is not None:
            if isinstance(year, bool) or not 2000 <= year <= 2100:
                raise ValueError('invalid_resource_year')
            params['ano_plano_acao' if profile == 'transferegov_special_plans' else 'ano_cadastro'] = str(year)
        if identity is not None:
            params[key] = identifier(identity)
        names = ('tamanho_da_pagina', 'total_pages', 'total_items', 'page_number')
    return PagePlan(dataset=profile, url=base, root='data', identity=key, start=1, step=1,
        page_size=page_size, max_pages=max_pages, size_parameter=names[0],
        total_pages_field=names[1], total_records_field=names[2], response_page_field=names[3],
        parameters=params, delay_seconds=.5)


def normalize_resource(profile: Profile, row: dict, source: Source, municipalities: dict) -> ResourceInput:
    base, identity_key = PROFILES[profile]
    require(row, [identity_key])
    identity = identifier(row[identity_key])
    attributes = {'profile': profile, 'financial_interpretation': 'not_payment', 'facility_id': None}
    municipality = None
    if profile == 'pncp_contracts':
        require(row, ['orgaoEntidade', 'unidadeOrgao', 'objetoContrato', 'anoContrato',
                      'sequencialContrato', 'dataAtualizacao', 'valorInicial'])
        buyer, unit = row['orgaoEntidade'], row['unidadeOrgao']
        require(buyer, ['cnpj']); require(unit, ['codigoIbge', 'ufSigla'])
        match = re.fullmatch(r'([A-Z0-9]{12}\d{2})-2-(\d{6})/(\d{4})', identity)
        if (not match or match[1] != cnpj(buyer['cnpj']) or isinstance(row['anoContrato'], bool)
                or isinstance(row['sequencialContrato'], bool)
                or str(row['anoContrato']) != match[3] or str(row['sequencialContrato']) != str(int(match[2]))):
            raise ValueError('pncp_identity_disagrees_with_fields')
        municipality = str(unit['codigoIbge'])
        if municipality not in municipalities or municipalities[municipality][1] != unit['ufSigla']:
            raise ValueError('unknown_or_conflicting_buyer_territory')
        title = text(row['objetoContrato'], limit=MAX_PNCP_OBJECT_CHARS, required=True, field='objetoContrato')
        updated = date_value(row['dataAtualizacao'], timestamp=True)
        if not updated:
            raise ValueError('pncp_update_timestamp_required')
        global_updated = date_value(row.get('dataAtualizacaoGlobal'), timestamp=True)
        if global_updated:
            try:
                updated = max([updated, global_updated], key=lambda x: datetime.fromisoformat(x.replace('Z', '+00:00')))
            except TypeError:
                raise ValueError('inconsistent_pncp_timestamp_timezones') from None
        fields = {'initial_cents': 'valorInicial', 'global_cents': 'valorGlobal', 'accumulated_cents': 'valorAcumulado'}
        amounts, precise = {}, {}
        for key, original in fields.items():
            cents, decimal = metadata_amount(row.get(original))
            amounts[key] = cents
            if decimal is not None:
                precise[key.removesuffix('_cents')] = decimal
        if row['valorInicial'] is None:
            raise ValueError('pncp_initial_amount_required')
        if precise:
            attributes['precise_amounts'] = precise
        revenue = row.get('receita')
        if revenue is not None and not isinstance(revenue, bool):
            raise ValueError('invalid_pncp_revenue_indicator')
        attributes.update(territorial_basis='buyer_registered_municipality_not_execution', state=unit['ufSigla'],
            budget_direction='revenue' if revenue is True else 'expense' if revenue is False else 'unknown',
            published_at=date_value(row.get('dataPublicacaoPncp'), timestamp=True),
            buyer_cnpj=match[1], buyer_name=text(buyer.get('razaoSocial'), field='orgaoEntidade.razaoSocial'), contract_number=text(row.get('numeroContratoEmpenho'), field='numeroContratoEmpenho'),
            source_control_number=identity, upstream_updated_at=updated,
            signed_on=date_value(row.get('dataAssinatura')), starts_on=date_value(row.get('dataVigenciaInicio')),
            ends_on=date_value(row.get('dataVigenciaFim')), **amounts)
        purchase = row.get('numeroControlePncpCompra')
        if purchase:
            attributes['purchase_control_number'] = identifier(purchase)
        source = Source(**(source.model_dump() | {'record_id': identity, 'reference_date': updated}))
        kind = 'contract'
    elif profile == 'transferegov_special_plans':
        require(row, ['codigo_plano_acao', 'ano_plano_acao', 'id_beneficiario', 'id_programa',
                      'valor_custeio_plano_acao', 'valor_investimento_plano_acao'])
        year = row['ano_plano_acao']
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
            raise ValueError('invalid_plan_year')
        code = text(row['codigo_plano_acao'], limit=100, field='codigo_plano_acao')
        title = text(row.get('nome_objeto'), field='nome_objeto') or f"Plano de ação {code or identity}"
        attributes.update(territorial_basis='beneficiary_municipality_not_resolved',
            plan_code=code, year=year, beneficiary_id=identifier(row['id_beneficiario']) if row['id_beneficiario'] is not None else None,
            program_id=identifier(row['id_programa']), declared_status=text(row.get('situacao_plano_acao'), field='situacao_plano_acao'),
            accepted_on=date_value(row.get('data_aceite_plano_acao')),
            planned_operating_cents=money(row['valor_custeio_plano_acao']),
            planned_investment_cents=money(row['valor_investimento_plano_acao']))
        source = Source(**(source.model_dump() | {'record_id': identity, 'reference_date': str(year)}))
        kind = 'proposal'
    else:
        require(row, ['desc_nome', 'situacao', 'uf_principal', 'investimentos_previstos'])
        title = text(row['desc_nome'], required=True, field='desc_nome')
        state = row['uf_principal']
        if state is not None and state not in STATES:
            raise ValueError('invalid_project_state')
        investments = row['investimentos_previstos'] or []
        if not isinstance(investments, list) or len(investments) > 100:
            raise ValueError('invalid_project_investments')
        entries = []
        for investment in investments:
            require(investment, ['vl_investimento_previsto', 'desc_nome_fonte_recurso'])
            entries.append({'planned_cents': money(investment['vl_investimento_previsto']),
                            'source_name': text(investment['desc_nome_fonte_recurso'], field='investimentos_previstos.desc_nome_fonte_recurso')})
        attributes.update(territorial_basis='state_only_municipality_unresolved', state=state,
            declared_status=text(row['situacao'], field='situacao'), planned_starts_on=date_value(row.get('dt_inicial_prevista')),
            planned_ends_on=date_value(row.get('dt_final_prevista')), planned_investments=entries)
        exec_perc = row.get('perc_execucao_fisica') or row.get('percentual_execucao') or row.get('execucao_fisica')
        if exec_perc is not None:
            try:
                attributes['physical_execution_percentage'] = float(exec_perc)
            except (ValueError, TypeError):
                pass
        exec_date = date_value(row.get('dt_medicao') or row.get('dt_ultima_medicao'))
        if exec_date:
            attributes['last_measurement_on'] = exec_date
        pins = row.get('pins') or row.get('geometrias') or row.get('pontos')
        if isinstance(pins, list) and len(pins) <= 100:
            parsed_pins = []
            for pin in pins:
                if isinstance(pin, dict) and 'latitude' in pin and 'longitude' in pin:
                    try:
                        lat = float(pin['latitude'])
                        lon = float(pin['longitude'])
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            parsed_pins.append({'latitude': lat, 'longitude': lon, 'kind': str(pin.get('tipo_geometria') or 'point')})
                    except (ValueError, TypeError):
                        pass
            if parsed_pins:
                attributes['project_geometries'] = parsed_pins
        source = Source(**(source.model_dump() | {'record_id': identity, 'reference_date': None}))
        kind = 'work'
    attributes['version_basis'] = 'publisher_update' if profile == 'pncp_contracts' else 'collection_snapshot'
    record_url = base + '?' + urlencode({identity_key: identity}) if profile != 'pncp_contracts' else source.url
    attributes['collection_page_url'] = source.url
    attributes['record_reference_url'] = record_url
    return ResourceInput(id=f'{profile}:{identity}', kind=kind, title=title,
                         municipality_id=municipality, source=source, attributes=attributes)

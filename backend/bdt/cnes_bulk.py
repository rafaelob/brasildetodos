"""Reviewed bulk-to-catalog profile, separate from the CNES REST profile.

Headers were observed in the official 56,121,369-byte distribution on
2026-09-06 UTC (SHA-256 2b09e0978553c05918d3b6ce97ee85819904b56526e1dc6bba385b8edf66c4e6).
Only textual SUS flags are interpreted; numeric code meanings are not guessed.
The file contains no per-record update date; collection time is not substituted.
"""
from __future__ import annotations
from .domain import fold

REQUIRED = frozenset({'CO_CNES','NO_FANTASIA','CO_IBGE','CO_AMBULATORIAL_SUS','CO_MOTIVO_DESAB'})
FIELD_MAP = {
    'CO_CNES':'codigo_cnes', 'NO_FANTASIA':'nome_fantasia', 'CO_IBGE':'codigo_municipio',
    'NO_LOGRADOURO':'endereco_estabelecimento', 'NU_ENDERECO':'numero_estabelecimento',
    'NO_BAIRRO':'bairro_estabelecimento', 'NU_TELEFONE':'numero_telefone_estabelecimento',
    'NU_LATITUDE':'latitude_estabelecimento_decimo_grau', 'NU_LONGITUDE':'longitude_estabelecimento_decimo_grau',
}


def convert(row: dict) -> dict:
    if not REQUIRED.issubset(row):
        raise ValueError('cnes_bulk_schema_changed')
    flag = fold(str(row['CO_AMBULATORIAL_SUS'] or '').strip())
    if flag in {'sim','s'}:
        sus = 'SIM'
    elif flag in {'nao','n','', 'null'}:
        sus = 'NAO'
    else:
        raise ValueError('cnes_bulk_sus_code_requires_dictionary_review')
    result = {target: row.get(original) for original,target in FIELD_MAP.items()}
    result['codigo_municipio'] = str(row['CO_IBGE']).strip()
    result['estabelecimento_faz_atendimento_ambulatorial_sus'] = sus
    disabled = str(row.get('CO_MOTIVO_DESAB') or '').strip()
    result['codigo_motivo_desabilitacao_estabelecimento'] = None if disabled.upper() in {'','NULL','NONE'} else disabled
    return result


def converted(rows):
    for row in rows:
        yield convert(row)

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for official IBGE CNEFE school geocoder."""
from __future__ import annotations

import csv
import io
import zipfile

import pytest
from sqlalchemy import select

from bdt.domain import Source, now
from bdt.school_geocoder import (
    find_cnefe_match,
    geocode_schools_for_state,
    normalize_school_name,
    parse_cnefe_schools,
)
from bdt.storage import Database, Municipality, Place, upsert_place
from bdt.domain import PlaceInput


def test_normalize_school_name():
    assert normalize_school_name('Escola Estadual Rui Barbosa') == 'RUI BARBOSA'
    assert normalize_school_name('Colégio Militar Sadoc Pereira') == 'MILITAR SADOC PEREIRA'
    assert normalize_school_name('E.M.E.F. Monteiro Lobato') == 'MONTEIRO LOBATO'
    assert normalize_school_name('') == ''
    # Pure stopwords must return empty to avoid collision between generic establishments
    assert normalize_school_name('CRECHE') == ''
    assert normalize_school_name('ESCOLA MUNICIPAL') == ''
    assert normalize_school_name('CENTRO EDUCACIONAL DE ENSINO') == ''


def test_find_cnefe_match():
    mun_cnefe = {
        'RUI BARBOSA': (-10.5, -37.2, 'ESCOLA RUI BARBOSA'),
        'MILITAR SADOC PEREIRA': (-10.6, -37.3, 'COLEGIO SADOC PEREIRA'),
        'SAO FRANCISCO': (-10.7, -37.4, 'ESCOLA SAO FRANCISCO'),
        'SAO FRANCISCO XAVIER': (-10.8, -37.5, 'ESCOLA SAO FRANCISCO XAVIER'),
    }
    match = find_cnefe_match('Escola Estadual Rui Barbosa', mun_cnefe)
    assert match is not None
    lat, lon, original = match
    assert lat == -10.5
    assert lon == -37.2
    assert original == 'ESCOLA RUI BARBOSA'

    # Unmatched
    assert find_cnefe_match('Escola Inexistente ABC', mun_cnefe) is None
    # Ambiguous candidate must not match (e.g. SAO FRANCISCO matches both SAO FRANCISCO and SAO FRANCISCO XAVIER)
    assert find_cnefe_match('Escola São Francisco', mun_cnefe) is not None  # exact match wins
    assert find_cnefe_match('Escola Francisco', mun_cnefe) is None  # ambiguous, matches multiple or none


def test_parse_cnefe_schools():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zf:
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, delimiter=';')
        writer.writerow([
            'COD_UNICO_ENDERECO', 'COD_UF', 'COD_MUNICIPIO', 'COD_DISTRITO',
            'COD_SUBDISTRITO', 'COD_SETOR', 'NUM_QUADRA', 'NUM_FACE', 'CEP',
            'DSC_LOCALIDADE', 'NOM_TIPO_SEGLOGR', 'NOM_TITULO_SEGLOGR',
            'NOM_SEGLOGR', 'NUM_ENDERECO', 'DSC_MODIFICADOR', 'NOM_COMP_ELEM1',
            'VAL_COMP_ELEM1', 'NOM_COMP_ELEM2', 'VAL_COMP_ELEM2', 'NOM_COMP_ELEM3',
            'VAL_COMP_ELEM3', 'NOM_COMP_ELEM4', 'VAL_COMP_ELEM4', 'NOM_COMP_ELEM5',
            'VAL_COMP_ELEM5', 'LATITUDE', 'LONGITUDE', 'NV_GEO_COORD', 'COD_ESPECIE',
            'DSC_ESTABELECIMENTO', 'COD_INDICADOR_ESTAB_ENDERECO',
            'COD_INDICADOR_CONST_ENDERECO', 'COD_INDICADOR_FINALIDADE_CONST', 'COD_TIPO_ESPECI'
        ])
        # Add school (COD_ESPECIE=4)
        writer.writerow([
            '1', '14', '1400100', '', '', '', '', '', '',
            '', '', '', 'RUA A', '100', '', '', '', '', '', '', '', '', '', '', '',
            '2.828012', '-60.702577', '1', '4', 'ANTONIO FERREIRA DE SOUZA', '', '', '', ''
        ])
        # Add residence (COD_ESPECIE=1) - should be ignored
        writer.writerow([
            '2', '14', '1400100', '', '', '', '', '', '',
            '', '', '', 'RUA B', '200', '', '', '', '', '', '', '', '', '', '', '',
            '2.830000', '-60.710000', '1', '1', '', '', '', '', ''
        ])
        # Add two schools with identical normalized names but conflicting coordinates in same municipality
        writer.writerow([
            '3', '14', '1400100', '', '', '', '', '', '',
            '', '', '', 'RUA C', '300', '', '', '', '', '', '', '', '', '', '', '',
            '2.810000', '-60.650000', '1', '4', 'ESCOLA AMBIGUA DE TESTE', '', '', '', ''
        ])
        writer.writerow([
            '4', '14', '1400100', '', '', '', '', '', '',
            '', '', '', 'RUA D', '400', '', '', '', '', '', '', '', '', '', '', '',
            '2.890000', '-60.750000', '1', '4', 'COLEGIO AMBIGUA DE TESTE', '', '', '', ''
        ])
        zf.writestr('14_RR.csv', csv_buffer.getvalue())

    parsed = parse_cnefe_schools(output.getvalue())
    assert '1400100' in parsed
    assert 'ANTONIO FERREIRA SOUZA' in parsed['1400100']
    lat, lon, name = parsed['1400100']['ANTONIO FERREIRA SOUZA']
    assert lat == 2.828012
    assert lon == -60.702577
    assert name == 'ANTONIO FERREIRA DE SOUZA'
    # The ambiguous establishment must have been discarded because coordinates conflicted
    assert 'AMBIGUA TESTE' not in parsed['1400100']


def test_geocode_schools_for_state_database():
    db = Database('sqlite:///:memory:')
    db.initialize()

    with db.session() as session:
        session.add(Municipality(id='1400100', name='Boa Vista', state='RR', source={'dataset': 'ibge'}))
        src = Source(dataset='inep-schools-2025', record_id='14000010', url='http://inep.gov.br',
                     reference_date='2025', collected_at=now(), snapshot_sha256='a'*64)
        school_input = PlaceInput(
            id='inep:14000010',
            kind='school',
            name='Escola Estadual Antonio Ferreira de Souza',
            municipality_id='1400100',
            state='RR',
            address='Rua A, 100',
            source=src,
        )
        upsert_place(session, school_input)
        session.commit()

    cnefe_data = {
        '1400100': {
            'ANTONIO FERREIRA SOUZA': (2.828012, -60.702577, 'ANTONIO FERREIRA DE SOUZA')
        }
    }

    stats = geocode_schools_for_state(db, 'RR', cnefe_data)
    assert stats['matched'] == 1
    assert stats['outcome_updated'] == 1

    with db.session() as session:
        updated = session.scalar(select(Place).where(Place.id == 'inep:14000010'))
        assert updated.latitude == 2.828012
        assert updated.longitude == -60.702577
        assert updated.payload['geo_source'] == 'IBGE-CNEFE-2022'

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for official IBGE CNEFE school geocoder."""
from __future__ import annotations

import csv
import io
import zipfile

import pytest
from sqlalchemy import select

from bdt.domain import PlaceInput, Source, now
from bdt.school_geocoder import (
    download_cnefe_state_zip,
    find_cnefe_match,
    geocode_schools_for_state,
    normalize_school_name,
    parse_cnefe_schools,
)
from bdt.storage import Database, Municipality, Place, upsert_place


def test_normalize_school_name():
    assert normalize_school_name('Escola Estadual Rui Barbosa') == 'RUI BARBOSA'
    assert normalize_school_name('Colégio Militar Sadoc Pereira') == 'MILITAR SADOC PEREIRA'
    assert normalize_school_name('E.M.E.F. Monteiro Lobato') == 'MONTEIRO LOBATO'
    assert normalize_school_name('') == ''
    # Pure stopwords must return empty to avoid collision between generic establishments
    assert normalize_school_name('CRECHE') == ''
    assert normalize_school_name('ESCOLA MUNICIPAL') == ''
    assert normalize_school_name('CENTRO EDUCACIONAL DE ENSINO') == ''


def test_find_cnefe_match_exact_unique_name():
    mun_cnefe = {
        'RUI BARBOSA': (-10.5, -37.2, 'ESCOLA RUI BARBOSA'),
        'MILITAR SADOC PEREIRA': (-10.6, -37.3, 'COLEGIO SADOC PEREIRA'),
        'SAO FRANCISCO': (-10.7, -37.4, 'ESCOLA SAO FRANCISCO'),
        'SAO FRANCISCO XAVIER': (-10.8, -37.5, 'ESCOLA SAO FRANCISCO XAVIER'),
    }
    match = find_cnefe_match('Escola Estadual Rui Barbosa', mun_cnefe)
    assert match == (-10.5, -37.2, 'ESCOLA RUI BARBOSA')
    # Exact match still wins when a longer name exists
    assert find_cnefe_match('Escola São Francisco', mun_cnefe) == (-10.7, -37.4, 'ESCOLA SAO FRANCISCO')
    assert find_cnefe_match('Escola Inexistente ABC', mun_cnefe) is None


def test_find_cnefe_match_rejects_token_subset():
    mun_cnefe = {
        'RUI BARBOSA SILVA': (-10.5, -37.2, 'ESCOLA RUI BARBOSA SILVA'),
        'SAO FRANCISCO XAVIER': (-10.8, -37.5, 'ESCOLA SAO FRANCISCO XAVIER'),
    }
    assert find_cnefe_match('Escola Estadual Rui Barbosa', mun_cnefe) is None
    assert find_cnefe_match('Escola Francisco', mun_cnefe) is None
    assert find_cnefe_match('Escola São Francisco', mun_cnefe) is None


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


def _memory_db_with_municipality() -> Database:
    db = Database('sqlite:///:memory:')
    db.initialize()
    with db.session() as session:
        session.add(Municipality(id='1400100', name='Boa Vista', state='RR', source={'dataset': 'ibge'}))
    return db


def _insert_school(db: Database, *, place_id: str, name: str, municipality_id: str = '1400100') -> None:
    with db.session() as session:
        src = Source(
            dataset='inep-schools-2025',
            record_id=place_id.split(':', 1)[1],
            url='http://inep.gov.br',
            reference_date='2025',
            collected_at=now(),
            snapshot_sha256='a' * 64,
        )
        upsert_place(session, PlaceInput(
            id=place_id,
            kind='school',
            name=name,
            municipality_id=municipality_id,
            state='RR',
            address='Rua A, 100',
            source=src,
        ))


def test_geocode_schools_for_state_does_not_publish_latitude():
    db = _memory_db_with_municipality()
    _insert_school(
        db,
        place_id='inep:14000010',
        name='Escola Estadual Antonio Ferreira de Souza',
    )

    cnefe_data = {
        '1400100': {
            'ANTONIO FERREIRA SOUZA': (2.828012, -60.702577, 'ANTONIO FERREIRA DE SOUZA')
        }
    }

    stats = geocode_schools_for_state(db, 'RR', cnefe_data)
    assert stats['matched'] == 1

    with db.session() as session:
        updated = session.scalar(select(Place).where(Place.id == 'inep:14000010'))
        assert updated.latitude is None
        assert updated.longitude is None
        assert updated.payload.get('geo_source') != 'IBGE-CNEFE-2022'
        assert updated.payload.get('latitude') is None
        assert updated.payload.get('longitude') is None
        assert updated.payload['cnefe_candidate'] == {
            'lat': 2.828012,
            'lon': -60.702577,
            'cnefe_name': 'ANTONIO FERREIRA DE SOUZA',
            'match': 'exact_name',
        }


def test_geocode_schools_for_state_increments_missing_municipality():
    db = _memory_db_with_municipality()
    _insert_school(db, place_id='inep:14000010', name='Escola Alpha')
    _insert_school(db, place_id='inep:14000011', name='Escola Beta')

    stats = geocode_schools_for_state(db, 'RR', {})
    assert stats['no_mun_cnefe'] == 2
    assert stats.get('matched', 0) == 0

    with db.session() as session:
        for place_id in ('inep:14000010', 'inep:14000011'):
            row = session.scalar(select(Place).where(Place.id == place_id))
            assert row.latitude is None
            assert 'cnefe_candidate' not in row.payload


def _block_network(monkeypatch):
    monkeypatch.delenv('BDT_CNEFE_OPERATOR_DOWNLOAD', raising=False)

    def boom(*args, **kwargs):
        raise AssertionError('ftp.ibge.gov.br must not be contacted')

    monkeypatch.setattr('bdt.school_geocoder.urllib.request.urlopen', boom)


def test_download_cnefe_prefers_cache(tmp_path, monkeypatch):
    _block_network(monkeypatch)
    archive = tmp_path / '14_RR.zip'
    archive.write_bytes(b'cached-cnefe-zip')
    assert download_cnefe_state_zip('RR', cache_dir=tmp_path) == b'cached-cnefe-zip'


def test_download_cnefe_cache_miss_names_file_without_ftp(tmp_path, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(ValueError, match=r'14_RR\.zip') as exc:
        download_cnefe_state_zip('RR', cache_dir=tmp_path)
    message = str(exc.value)
    assert 'HOSTS' in message
    assert 'BDT_CNEFE_OPERATOR_DOWNLOAD' in message


def test_download_cnefe_operator_exception_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv('BDT_CNEFE_OPERATOR_DOWNLOAD', '1')

    class _Resp:
        status = 200

        def read(self):
            return b'operator-zip'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr('bdt.school_geocoder.urllib.request.urlopen', lambda *a, **k: _Resp())
    data = download_cnefe_state_zip('RR', cache_dir=tmp_path)
    assert data == b'operator-zip'
    assert (tmp_path / '14_RR.zip').read_bytes() == b'operator-zip'

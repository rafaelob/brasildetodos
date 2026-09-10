# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from bdt.domain import Source
from bdt.storage import Database, Finance, Ingestion, Municipality
from bdt.transferegov_finance import (
    EXCLUDED_SENSITIVE_KEYS,
    REQUIRED_ADITIVO,
    REQUIRED_CONVENIO,
    REQUIRED_CROSSWALK,
    REQUIRED_DESEMBOLSO,
    parse_date_to_iso,
    parse_brl_cents,
    load_municipality_crosswalk,
    normalize_agreements,
    normalize_amendments,
    normalize_disbursements,
    import_transferegov_financial,
    public_finance_payload,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import transferegov_financial_download_and_ingest as tg_ops


@pytest.fixture
def fake_source():
    return Source(
        dataset='transferegov',
        url='https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_convenio.zip',
        record_id='test-run',
        collected_at='2026-09-08T00:00:00+00:00',
        snapshot_sha256='a' * 64,
        reference_date='2026',
    )


def test_parse_brl_cents():
    assert parse_brl_cents('1.200,50') == 120050
    assert parse_brl_cents('2606359,37') == 260635937
    assert parse_brl_cents('-32.400,55') == -3240055
    assert parse_brl_cents('-32400,55') == -3240055
    assert parse_brl_cents('23080') == 2308000
    assert parse_brl_cents('0') == 0
    assert parse_brl_cents('0,00') == 0
    assert parse_brl_cents('') == 0
    assert parse_brl_cents(None) == 0
    with pytest.raises(ValueError, match='ambiguous_brl_amount'):
        parse_brl_cents('invalid-amount')


def test_parse_date_to_iso():
    assert parse_date_to_iso('19/12/2023') == '2023-12-19'
    assert parse_date_to_iso('2023-12-19') == '2023-12-19'
    assert parse_date_to_iso('2023-12') == '2023-12'
    assert parse_date_to_iso('2023') == '2023-01-01'
    assert parse_date_to_iso('', fallback_year='2024') == '2024-01-01'
    with pytest.raises(ValueError, match='invalid_date_format'):
        parse_date_to_iso('invalid/date')


def test_crosswalk_loader():
    lookup = {'3550308': ('3550308', 'SP')}
    rows = [
        {'NR_CONVENIO': '948971', 'COD_MUNIC_IBGE': '3550308', 'NM_PROPONENTE': 'MUNICIPIO DE SAO PAULO'},
        {'NR_CONVENIO': '999999', 'COD_MUNIC_IBGE': '9999999', 'NM_PROPONENTE': 'UNKNOWN'},  # Not in lookup
    ]
    crosswalk = load_municipality_crosswalk(rows, lookup)
    assert '948971' in crosswalk
    assert crosswalk['948971'] == ('3550308', 'MUNICIPIO DE SAO PAULO')
    assert '999999' not in crosswalk


def test_normalize_agreements_signed_vs_preconvenio(fake_source):
    crosswalk = {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO'), '966185': ('3550308', 'PRE-CONVENIO')}
    rows = [
        {
            'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '2.606.359,37',
            'VL_REPASSE_CONV': '2.603.659,37', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
            'SIT_CONVENIO': 'Em execução'
        },
        {
            'NR_CONVENIO': '966185', 'IND_ASSINADO': 'NÃO', 'VL_GLOBAL_CONV': '1.912.000,00',
            'VL_REPASSE_CONV': '1.910.000,00', 'DIA_ASSIN_CONV': '', 'ANO': '2024',
            'SIT_CONVENIO': 'Proposta Aprovada'
        },
        {
            'NR_CONVENIO': '888888', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '500.000,00',
            'VL_REPASSE_CONV': '500.000,00', 'DIA_ASSIN_CONV': '01/01/2024', 'ANO': '2024',
            'SIT_CONVENIO': 'Em execução'
        }  # Orphan: not in crosswalk
    ]
    events = list(normalize_agreements(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:agreement:948971'
    assert ev.phase == 'agreed'
    assert ev.cents == 260635937
    assert ev.municipality_id == '3550308'
    assert ev.recipient == 'MUNICIPIO DE SAO PAULO'
    assert ev.nature == 'estimate'


def test_normalize_amendments_negative_supressao(fake_source):
    crosswalk = {'858176': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows = [
        {
            'NR_CONVENIO': '858176', 'NUMERO_TA': '2/2020', 'TIPO_TA': 'Supressão',
            'VL_GLOBAL_TA': '-32.400,55', 'DT_ASSINATURA_TA': '15/05/2020'
        },
        {
            'NR_CONVENIO': '858176', 'NUMERO_TA': '1/2020', 'TIPO_TA': 'Alteração da Vigência',
            'VL_GLOBAL_TA': '0,00', 'DT_ASSINATURA_TA': '10/01/2020'
        }
    ]
    events = list(normalize_amendments(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:amendment:858176:2-2020'
    assert ev.phase == 'agreed'
    assert ev.cents == -3240055  # Preserved negative adjustment!
    assert ev.nature == 'event'


def test_normalize_disbursements_transferred_phase(fake_source):
    crosswalk = {'946645': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows = [
        {
            'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '946645',
            'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91'
        },
        {
            'ID_DESEMBOLSO': '366483', 'NR_CONVENIO': '946645',
            'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '0,00'
        }
    ]
    events = list(normalize_disbursements(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:disbursement:366482'
    assert ev.phase == 'transferred'
    assert ev.cents == 28849791
    assert ev.instrument_id == '946645'


def test_import_transferegov_financial_transactional(database, fake_source):
    # Ensure municipality exists in database
    with database.session() as session:
        session.add(Municipality(
            id='3550308', name='São Paulo', state='SP',
            source=fake_source.model_dump()
        ))
    crosswalk = {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows_agreements = [{
        'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '2.606.359,37',
        'VL_REPASSE_CONV': '2.603.659,37', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
        'SIT_CONVENIO': 'Em execução'
    }]
    rows_amendments = [{
        'NR_CONVENIO': '948971', 'NUMERO_TA': '1/2024', 'TIPO_TA': 'Supressão',
        'VL_GLOBAL_TA': '-50.000,00', 'DT_ASSINATURA_TA': '10/06/2024'
    }]
    rows_disbursements = [{
        'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '948971',
        'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91'
    }]
    events = list(normalize_agreements(rows_agreements, crosswalk, fake_source)) + \
             list(normalize_amendments(rows_amendments, crosswalk, fake_source)) + \
             list(normalize_disbursements(rows_disbursements, crosswalk, fake_source))
    assert len(events) == 3

    counts = import_transferegov_financial(database, events, fake_source)
    assert counts['agreed'] == 1
    assert counts['amendments'] == 1
    assert counts['transferred'] == 1
    assert counts['total'] == 3

    with database.session() as session:
        finances = list(session.scalars(select(Finance).where(Finance.municipality_id == '3550308')))
        assert len(finances) == 3
        # Check that negative amendment was preserved
        amendment_rec = next(f for f in finances if ':amendment:' in f.payload['id'])
        assert amendment_rec.cents == -5000000
        assert amendment_rec.payload['phase'] == 'agreed'
        ingestion = session.scalar(select(Ingestion).where(Ingestion.dataset == 'transferegov'))
        assert ingestion is not None
        assert ingestion.status == 'success'
        assert ingestion.counts['total'] == 3

    # Idempotent re-import
    counts_re = import_transferegov_financial(database, events, fake_source)
    assert counts_re['unchanged'] == 3
    assert counts_re['total'] == 0


def test_public_finance_payload_excludes_sensitive_keys(fake_source):
    raw = {
        'id': 'transferegov:agreement:948971',
        'phase': 'agreed',
        'cents': 260635937,
        'NR_CONVENIO': '948971',
        'CPF': '00000000000',
        'CONTA': '12345-6',
        'BANCO': '001',
        'AGENCIA': '0001',
        'NR_SIAFI': 'siafi',
        'UG_EMITENTE_DH': 'ug',
        'OBSERVACAO_DH': 'secret-note',
        'CD_IDENTIF_PROPONENTE': 'ident',
        'cpf': 'also-secret',
    }
    payload = public_finance_payload(raw)
    assert EXCLUDED_SENSITIVE_KEYS.isdisjoint(payload)
    assert {key.upper() for key in payload}.isdisjoint({key.upper() for key in EXCLUDED_SENSITIVE_KEYS})
    assert payload['phase'] == 'agreed'
    assert payload['cents'] == 260635937
    assert 'financial_total' not in payload
    event_payload = public_finance_payload(next(iter(normalize_agreements(
        [{'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '10,00',
          'VL_REPASSE_CONV': '10,00', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
          'SIT_CONVENIO': 'Em execução'}],
        {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO')},
        fake_source,
    ))))
    assert EXCLUDED_SENSITIVE_KEYS.isdisjoint(event_payload)
    assert event_payload['phase'] == 'agreed'


def _write_archive(path: Path, member: str, header: list[str], rows: list[list[str]]) -> dict:
    body = ';'.join(header) + '\n' + ''.join(';'.join(row) + '\n' for row in rows)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(member, body.encode('utf-8'))
    data = path.read_bytes()
    return {
        'url': 'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/' + path.name,
        'path': str(path),
        'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'status': 'cached',
    }


def _cached_downloads(tmp_path: Path) -> Path:
    folder = tmp_path / 'transferegov'
    folder.mkdir()
    convenio_header = sorted(REQUIRED_CONVENIO)
    aditivo_header = sorted(REQUIRED_ADITIVO)
    desembolso_header = sorted(REQUIRED_DESEMBOLSO)
    crosswalk_header = sorted(REQUIRED_CROSSWALK)

    def cells(header, mapping):
        return [mapping.get(name, '') for name in header]

    receipts = {
        'siconv_prop_inst_indicadores_municipios.zip': _write_archive(
            folder / 'siconv_prop_inst_indicadores_municipios.zip',
            'siconv_prop_inst_indicadores_municipios.csv',
            crosswalk_header,
            [cells(crosswalk_header, {'NR_CONVENIO': '948971', 'COD_MUNIC_IBGE': '3550308',
                                      'NM_PROPONENTE': 'MUNICIPIO DE SAO PAULO'})],
        ),
        'siconv_convenio.zip': _write_archive(
            folder / 'siconv_convenio.zip',
            'siconv_convenio.csv',
            convenio_header,
            [
                cells(convenio_header, {'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM',
                                        'VL_GLOBAL_CONV': '2.606.359,37', 'VL_REPASSE_CONV': '2.603.659,37',
                                        'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
                                        'SIT_CONVENIO': 'Em execução'}),
                cells(convenio_header, {'NR_CONVENIO': '966185', 'IND_ASSINADO': 'NÃO',
                                        'VL_GLOBAL_CONV': '1.912.000,00', 'VL_REPASSE_CONV': '1.910.000,00',
                                        'DIA_ASSIN_CONV': '', 'ANO': '2024',
                                        'SIT_CONVENIO': 'Proposta Aprovada'}),
                cells(convenio_header, {'NR_CONVENIO': '888888', 'IND_ASSINADO': 'SIM',
                                        'VL_GLOBAL_CONV': '500.000,00', 'VL_REPASSE_CONV': '500.000,00',
                                        'DIA_ASSIN_CONV': '01/01/2024', 'ANO': '2024',
                                        'SIT_CONVENIO': 'Em execução'}),
            ],
        ),
        'siconv_termo_aditivo.zip': _write_archive(
            folder / 'siconv_termo_aditivo.zip',
            'siconv_termo_aditivo.csv',
            aditivo_header,
            [
                cells(aditivo_header, {'NR_CONVENIO': '948971', 'NUMERO_TA': '2/2020',
                                       'TIPO_TA': 'Supressão', 'VL_GLOBAL_TA': '-32.400,55',
                                       'DT_ASSINATURA_TA': '15/05/2020'}),
                cells(aditivo_header, {'NR_CONVENIO': '948971', 'NUMERO_TA': '1/2020',
                                       'TIPO_TA': 'Alteração da Vigência', 'VL_GLOBAL_TA': '0,00',
                                       'DT_ASSINATURA_TA': '10/01/2020'}),
            ],
        ),
        'siconv_desembolso.zip': _write_archive(
            folder / 'siconv_desembolso.zip',
            'siconv_desembolso.csv',
            desembolso_header,
            [cells(desembolso_header, {'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '948971',
                                      'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91'})],
        ),
    }
    (folder / 'receipts.json').write_text(json.dumps(receipts), encoding='utf-8')
    return folder


def _operator_finance_sqlite(tmp_path: Path, source: Source) -> Path:
    db_path = tmp_path / 'operator-finance.db'
    database = Database(f'sqlite:///{db_path.resolve()}')
    database.initialize()
    with database.session() as session:
        session.add(Municipality(
            id='3550308', name='São Paulo', state='SP',
            source=source.model_dump()
        ))
    database.engine.dispose()
    return db_path


def _ingest_archive_receipts(report: dict) -> list[dict]:
    raw = report.get('archives', report.get('receipts'))
    if isinstance(raw, dict):
        return [
            {'name': name, **(row if isinstance(row, dict) else {})}
            for name, row in raw.items()
        ]
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    return []


def _phase_counts(report: dict) -> dict:
    nested = report.get('counts')
    if isinstance(nested, dict) and {'agreed', 'amendments', 'transferred', 'total'} <= nested.keys():
        return nested
    if {'agreed', 'amendments', 'transferred', 'total'} <= report.keys():
        return report
    raise AssertionError('run_ingest receipt must include phase counts agreed/amendments/transferred/total')


def test_freeze_validator_not_certified_and_phases_not_summed(tmp_path):
    folder = _cached_downloads(tmp_path)
    report = tg_ops.freeze_cached_archives(folder, sample_limit=50)
    assert report['status'] == 'validated'
    assert report['national_catalog_certified'] is False
    assert report['financial_total_computed'] is False
    assert report['public_data_v1_unchanged'] is True
    assert report['records_imported'] == 0
    assert report['phases_summed'] is False
    assert 'total_cents' not in report
    assert 'combined_cents' not in report
    assert report['counts']['convenio']['signed'] == 2
    assert report['counts']['convenio']['preconvenio'] == 1
    assert report['counts']['convenio']['orphan_instruments'] == 2
    assert report['counts']['aditivo']['negative'] == 1
    assert report['counts']['aditivo']['zero'] == 1
    for bucket in report['counts'].values():
        if isinstance(bucket, dict):
            assert 'cents' not in bucket
            assert 'total_cents' not in bucket
    assert 'financial_total' not in report
    for archive in report['archives']:
        assert archive['status'] == 'validated'
        assert archive['sha256']
        assert archive['bytes'] > 0


def test_freeze_hash_mismatch_stays_uncertified(tmp_path):
    folder = _cached_downloads(tmp_path)
    receipts = json.loads((folder / 'receipts.json').read_text(encoding='utf-8'))
    receipts['siconv_convenio.zip']['sha256'] = '0' * 64
    (folder / 'receipts.json').write_text(json.dumps(receipts), encoding='utf-8')
    report = tg_ops.freeze_cached_archives(folder, sample_limit=10)
    assert report['national_catalog_certified'] is False
    assert report['financial_total_computed'] is False
    assert report['records_imported'] == 0
    assert report['status'] == 'failed'
    convenio = next(row for row in report['archives'] if row['name'] == 'siconv_convenio.zip')
    assert convenio['status'] == 'failed'
    assert convenio['reason'].startswith('archive_hash_mismatch')


def test_operator_ingest_refuses_live_app_db(tmp_path):
    with pytest.raises(ValueError, match='refuse_live_app_database'):
        tg_ops.refuse_live_app_database(Path('data/bdt.db'))
    with pytest.raises(ValueError, match='refuse_live_app_database'):
        tg_ops.run_ingest(tmp_path / 'bdt.db', tmp_path / 'missing')
    with pytest.raises(ValueError, match='database_required_for_ingest'):
        tg_ops.refuse_live_app_database(None)


def test_operator_ingest_writes_phases_to_new_sqlite(tmp_path, fake_source):
    db_path = _operator_finance_sqlite(tmp_path, fake_source)
    assert db_path.name != 'bdt.db'
    report = tg_ops.run_ingest(db_path, _cached_downloads(tmp_path))
    assert report.get('financial_total_computed') is not True
    assert 'total_cents' not in report
    assert 'combined_cents' not in report
    assert 'financial_total' not in report
    nested = report.get('counts')
    if isinstance(nested, dict):
        assert 'total_cents' not in nested
        assert 'combined_cents' not in nested
        assert 'financial_total' not in nested
    if 'national_catalog_certified' in report:
        assert report['national_catalog_certified'] is False

    database = Database(f'sqlite:///{db_path.resolve()}')
    try:
        with database.session() as session:
            finances = list(session.scalars(select(Finance).where(Finance.municipality_id == '3550308')))
        by_id = {row.payload['id']: row for row in finances}
        assert set(by_id) == {
            'transferegov:agreement:948971',
            'transferegov:amendment:948971:2-2020',
            'transferegov:disbursement:366482',
        }
        agreement = by_id['transferegov:agreement:948971']
        amendment = by_id['transferegov:amendment:948971:2-2020']
        disbursement = by_id['transferegov:disbursement:366482']
        assert agreement.cents == 260635937
        assert agreement.payload['phase'] == 'agreed'
        assert amendment.cents == -3240055
        assert amendment.payload['phase'] == 'agreed'
        assert disbursement.cents == 28849791
        assert disbursement.payload['phase'] == 'transferred'
        assert [row.payload['phase'] for row in finances].count('agreed') == 2
        assert [row.payload['phase'] for row in finances].count('transferred') == 1
        assert all(row.facility_id is None for row in finances)
        assert all(row.payload.get('facility_id') is None for row in finances)
    finally:
        database.engine.dispose()


def test_operator_ingest_receipt_has_provenance(tmp_path, fake_source):
    db_path = _operator_finance_sqlite(tmp_path, fake_source)
    downloads = _cached_downloads(tmp_path)
    report = tg_ops.run_ingest(db_path, downloads)
    counts = _phase_counts(report)
    assert counts['agreed'] == 1
    assert counts['amendments'] == 1
    assert counts['transferred'] == 1
    assert counts['total'] == 3
    assert counts['total'] == counts['agreed'] + counts['amendments'] + counts['transferred']
    for key in ('cents', 'total_cents', 'combined_cents', 'financial_total'):
        assert key not in counts

    rows = _ingest_archive_receipts(report)
    named = {}
    for row in rows:
        name = row.get('name') or Path(str(row.get('path', ''))).name
        named[name] = row
    assert named, 'run_ingest receipt must include per-archive url/bytes/sha256'
    for name in tg_ops.TARGET_FILES:
        row = named[name]
        assert isinstance(row.get('url'), str) and name in row['url']
        data = (downloads / name).read_bytes()
        assert isinstance(row['bytes'], int) and row['bytes'] == len(data)
        sha = row['sha256']
        assert isinstance(sha, str) and len(sha) == 64
        int(sha, 16)
        assert sha.lower() == hashlib.sha256(data).hexdigest()

    exclusions = report.get('exclusions')
    if exclusions is None:
        exclusions = next(
            (report[key] for key in ('excluded', 'not_imported', 'omitted') if key in report),
            None,
        )
    assert exclusions not in (None, '', [], {})
    text = exclusions if isinstance(exclusions, str) else json.dumps(exclusions, ensure_ascii=False)
    folded = (
        text.lower()
        .replace('á', 'a').replace('é', 'e').replace('í', 'i')
        .replace('ó', 'o').replace('ú', 'u').replace('â', 'a')
        .replace('ê', 'e').replace('ô', 'o').replace('ã', 'a')
        .replace('õ', 'o').replace('ç', 'c')
    )
    compact = folded.replace('-', '').replace(' ', '')
    assert 'preconvenio' in compact
    assert 'sensitive' in folded or any(key.lower() in folded for key in EXCLUDED_SENSITIVE_KEYS)


def test_operator_ingest_limit_zero_imports_no_rows(tmp_path, fake_source):
    db_path = _operator_finance_sqlite(tmp_path, fake_source)
    report = tg_ops.run_ingest(
        db_path, _cached_downloads(tmp_path),
        limit_agreements=0, limit_amendments=0, limit_disbursements=0,
    )
    assert report['records_imported'] == 0
    assert report['counts']['agreed'] == 0
    assert report['counts']['amendments'] == 0
    assert report['counts']['transferred'] == 0
    assert report['limits'] == {'agreements': 0, 'amendments': 0, 'disbursements': 0}
    assert report['financial_total_computed'] is False
    assert report['national_catalog_certified'] is False
    database = Database(f'sqlite:///{db_path.resolve()}')
    try:
        with database.session() as session:
            assert list(session.scalars(select(Finance))) == []
    finally:
        database.engine.dispose()


def test_committed_operator_ingest_receipt_is_not_a_national_total():
    root = Path(__file__).resolve().parents[2]
    ingest = json.loads((root / 'docs' / 'reports' / '20260909-transferegov-ingest.json').read_text(encoding='utf-8'))
    freeze = json.loads((root / 'docs' / 'reports' / '20260909-transferegov-freeze.json').read_text(encoding='utf-8'))
    assert ingest['schema'] == 'bdt.transferegov-finance-ingest.v1'
    assert ingest['national_catalog_certified'] is False
    assert ingest['financial_total_computed'] is False
    assert ingest['phases_summed'] is False
    assert ingest['live_app_database_refused'] == 'data/bdt.db'
    assert ingest['database'] != 'data/bdt.db'
    assert ingest['records_imported'] == ingest['counts']['total']
    assert ingest['records_imported'] == (
        ingest['counts']['agreed'] + ingest['counts']['amendments'] + ingest['counts']['transferred']
    )
    assert 'total_cents' not in ingest
    assert ingest['limits'] == {'agreements': 2000, 'amendments': 2000, 'disbursements': 2000}
    freeze_hash = {row['name']: row['sha256'] for row in freeze['archives']}
    for archive in ingest['archives']:
        assert archive['url'].startswith('https://api-publica.transferegov.gestao.gov.br/')
        assert archive['bytes'] > 0
        assert archive['sha256'] == freeze_hash[archive['name']]
        assert len(archive['sha256']) == 64


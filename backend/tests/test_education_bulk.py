"""Synthetic fixtures validate behavior; they are never startup data."""
import csv
import io
import zipfile
from dataclasses import replace

import pytest
from sqlalchemy import select

from bdt.education_bulk import (ANCHOR, Limits, STATES, discover_distribution, import_school_archive,
                                inspect_archive, school_rows, validate_rows)
from bdt.ingest import file_source, municipality_lookup
from bdt.storage import Place

FIELDS = ['CO_ENTIDADE', 'NO_ENTIDADE', 'CO_MUNICIPIO', 'TP_DEPENDENCIA',
          'TP_SITUACAO_FUNCIONAMENTO', 'NU_ANO_CENSO', 'SG_UF', 'IN_INF_CRE',
          'DS_ENDERECO', 'NU_LATITUDE', 'NU_LONGITUDE']


def row(**changes):
    return {'CO_ENTIDADE':'12345678', 'NO_ENTIDADE':'Escola Sintética João',
            'CO_MUNICIPIO':'1234567', 'TP_DEPENDENCIA':'3', 'TP_SITUACAO_FUNCIONAMENTO':'1',
            'NU_ANO_CENSO':'2025', 'SG_UF':'BA', 'IN_INF_CRE':'1',
            'DS_ENDERECO':'Rua sintética', 'NU_LATITUDE':'', 'NU_LONGITUDE':'', **changes}


def archive(tmp_path, rows=None, *, encoding='utf-8-sig', filename='dados/Tabela_Escola_2025.csv',
            fields=FIELDS, extra=None):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields, delimiter=";")
    writer.writeheader()
    writer.writerows(rows if rows is not None else [row()])
    path = tmp_path/'schools.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, out.getvalue().encode(encoding))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


def source_for(path):
    return file_source(path, 'inep-school-test-only', 'https://example.org/test-only.zip', '2025')


def validate(database, source, rows, **kwargs):
    return validate_rows(rows, source, municipality_lookup(database), year=2025,
                         required_states=frozenset({'BA'}), **kwargs)


def test_discover_one_current_official_link_only():
    url='https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025.zip'
    html=f'<a href="{url}">current</a><a href="{url}">duplicate navigation</a>'
    assert discover_distribution(html,2025)==url


@pytest.mark.parametrize('href',[
    'http://download.inep.gov.br/2025.zip',
    'https://download.inep.gov.br.evil.test/2025.zip',
    'https://user@download.inep.gov.br/2025.zip',
    'https://download.inep.gov.br:444/2025.zip',
    'https://download.inep.gov.br/120250.zip',
    'https://download.inep.gov.br/2025.zip?redirect=x',
    'https://download.inep.gov.br/2024.zip',
    'https://example.org/2025.zip'])
def test_unreviewed_or_wrong_year_link_rejected(href):
    with pytest.raises(ValueError,match='requires_review'):
        discover_distribution(f'<a href="{href}">x</a>',2025)


def test_ambiguous_distribution_requires_operator_review():
    with pytest.raises(ValueError,match='requires_review:2'):
        discover_distribution('<a href="https://download.inep.gov.br/a2025.zip">a</a>'
                              '<a href="https://download.inep.gov.br/b2025.zip">b</a>',2025)


def test_invalid_discovery_limits():
    with pytest.raises(ValueError): discover_distribution('',1999)
    with pytest.raises(ValueError): discover_distribution('x'*(8*1024**2+1),2025)


@pytest.mark.parametrize('encoding',['utf-8-sig','cp1252'])
def test_full_body_encoding_and_native_unicode(tmp_path,encoding):
    path=archive(tmp_path,encoding=encoding,extra={'dados/Tabela_Matricula_2025.csv':b'NEVER READ\x81'})
    tables=inspect_archive(path)
    assert len(tables)==1
    assert list(school_rows(path,tables))[0]['NO_ENTIDADE']=='Escola Sintética João'
    assert tables[0].encoding==encoding
    assert len(tables[0].sha256)==64


def test_no_individual_or_unreviewed_schema(tmp_path):
    path=archive(tmp_path,filename='dados/Tabela_Matricula_2025.csv')
    with pytest.raises(ValueError,match='schema_not_found'): inspect_archive(path)
    path=archive(tmp_path,rows=[{'other':'x'}],fields=['other'])
    with pytest.raises(ValueError,match='schema_not_found'): inspect_archive(path)


@pytest.mark.parametrize('name',['../Tabela_Escola.csv','/Tabela_Escola.csv','folder\\Tabela_Escola.csv'])
def test_unsafe_archive_names(tmp_path,name):
    with pytest.raises(ValueError,match='unsafe_or_encrypted'):
        inspect_archive(archive(tmp_path,filename=name))


@pytest.mark.parametrize('limits',[
    Limits(archive_bytes=1), Limits(member_bytes=1), Limits(total_school_bytes=1),
    Limits(members=0), Limits(compression_ratio=1), Limits(header_bytes=5)])
def test_archive_budgets(tmp_path,limits):
    with pytest.raises(ValueError): inspect_archive(archive(tmp_path),limits=limits)


def test_duplicate_zip_entries(tmp_path):
    path=archive(tmp_path)
    with pytest.warns(UserWarning),zipfile.ZipFile(path,'a') as z:
        z.writestr('dados/Tabela_Escola_2025.csv',b'a')
    with pytest.raises(ValueError,match='entries_invalid'): inspect_archive(path)


def test_duplicate_csv_headers(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('escolas.csv',';'.join(FIELDS+['CO_ENTIDADE'])+'\n')
    with pytest.raises(ValueError,match='ambiguous_columns'): inspect_archive(path)


def test_invalid_encoding_does_not_replace_characters(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('escolas.csv',b'\x81')
    with pytest.raises(ValueError,match='encoding_requires_review'): inspect_archive(path)


def test_csv_width_and_changed_header(tmp_path):
    path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('escolas.csv',';'.join(FIELDS)+'\n1;2\n')
    tables=inspect_archive(path)
    with pytest.raises(ValueError,match='row_width'): list(school_rows(path,tables))
    with pytest.raises(ValueError,match='header_changed'):
        list(school_rows(path,[replace(tables[0],columns=tuple(reversed(FIELDS)))]))


def test_counts_exclusions_and_no_invented_geometry(database,source):
    rows=[row(),row(CO_ENTIDADE='12345679',TP_DEPENDENCIA='4'),
          row(CO_ENTIDADE='12345680',TP_SITUACAO_FUNCIONAMENTO='2'),
          row(CO_ENTIDADE='12345681',NU_LATITUDE='-12,9',NU_LONGITUDE='-38,5')]
    result=validate(database,source,rows)
    assert result['counts']=={'read':4,'eligible':2,'without_geometry':1,'excluded':2,'with_geometry':1}
    assert result['partition_check_passed'] is True
    assert result['national_catalog_certified'] is False


@pytest.mark.parametrize('changes,reason',[
    ({'CO_ENTIDADE':'123'},'invalid_or_duplicate_identity'),
    ({'CO_ENTIDADE':'12345678 '},'identity_whitespace'),
    ({'CO_MUNICIPIO':'123456'},'unknown_municipality'),
    ({'CO_MUNICIPIO':'7654321'},'unknown_municipality'),
    ({'TP_DEPENDENCIA':'5'},'eligibility_code'),
    ({'TP_SITUACAO_FUNCIONAMENTO':'UNKNOWN'},'eligibility_code'),
    ({'NU_ANO_CENSO':'2024'},'reference_year_mismatch'),
    ({'SG_UF':'SP'},'state_mismatch'),
    ({'NO_ENTIDADE':False},'required_fields')])
def test_invalid_fields_abort_validation(database,source,changes,reason):
    with pytest.raises(ValueError,match=reason): validate(database,source,[row(**changes)])


def test_invalid_excluded_row_is_not_silently_ignored(database,source):
    with pytest.raises(ValueError,match='unknown_municipality'):
        validate(database,source,[row(CO_MUNICIPIO='7654321',TP_DEPENDENCIA='4')])


def test_duplicate_identity_across_tables_aborts_before_any_write(database,tmp_path):
    path=archive(tmp_path)
    with zipfile.ZipFile(path,'a') as z:
        z.writestr('dados/Outra_Escola.csv',z.read('dados/Tabela_Escola_2025.csv'))
    with pytest.raises(ValueError,match='duplicate_identity'):
        import_school_archive(database,path,source_for(path),year=2025,required_states=frozenset({'BA'}))
    with database.session() as s: assert s.scalar(select(Place)) is None


def test_national_scope_refuses_single_state_publication(database,tmp_path):
    path=archive(tmp_path)
    result=import_school_archive(database,path,source_for(path),year=2025)
    assert result['status']=='partition_review_required'
    assert len(result['missing_eligible_states'])==26
    with database.session() as s: assert s.scalar(select(Place)) is None


def test_real_transactional_import_and_idempotency(database,tmp_path):
    path=archive(tmp_path)
    source=source_for(path)
    first=import_school_archive(database,path,source,year=2025,required_states=frozenset({'BA'}))
    second=import_school_archive(database,path,source,year=2025,required_states=frozenset({'BA'}))
    assert first['status']=='imported'
    assert first['import']['counts']['inserted']==1
    assert second['import']['counts']['unchanged']==1
    with database.session() as s:
        place=s.get(Place,'inep:12345678')
        assert place.latitude is None
        assert place.payload['declared_services']==['nursery']
        assert place.payload['source']['snapshot_sha256']==source.snapshot_sha256


def test_hash_and_year_bind_to_input(database,tmp_path):
    path=archive(tmp_path)
    source=source_for(path)
    for wrong in [source.model_copy(update={'snapshot_sha256':'0'*64}),source.model_copy(update={'reference_date':'2024'})]:
        with pytest.raises(ValueError,match='hash_or_year_mismatch'):
            import_school_archive(database,path,wrong,year=2025)


def test_empty_budget_and_invalid_scope(database,source):
    with pytest.raises(ValueError,match='empty_school_table'): validate(database,source,[])
    with pytest.raises(ValueError,match='row_budget'): validate(database,source,[row(),row(CO_ENTIDADE='12345679')],max_rows=1)
    with pytest.raises(ValueError,match='invalid_school_validation_scope'):
        validate_rows([],source,{},year=2025,required_states=frozenset({'XX'}))


def test_year_from_distribution_is_disclosed(database,source):
    value=row();del value['NU_ANO_CENSO']
    result=validate(database,source,[value])
    assert result['counts']['reference_year_from_distribution_only']==1

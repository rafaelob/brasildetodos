import json
import zipfile
from decimal import Decimal
import pytest
from sqlalchemy import func, select
from bdt.domain import now
from bdt.ingest import HOSTS, cnes_record, csv_records, file_source, import_finance, import_ibge, import_places, inep_record, json_records, municipality_lookup, pncp_contracts, safe_download, transferegov_rows
from bdt.storage import Change, Finance, Ingestion, Place, upsert_place


def inep():return {'CO_ENTIDADE':'12345678','NO_ENTIDADE':'Escola Sintética','CO_MUNICIPIO':'1234567','TP_DEPENDENCIA':'3','TP_SITUACAO_FUNCIONAMENTO':'1','IN_INF_CRE':'1'}
def cnes():return {'codigo_cnes':123,'nome_fantasia':'Unidade Sintética','codigo_municipio':123456,'estabelecimento_faz_atendimento_ambulatorial_sus':'SIM','data_atualizacao':'2025-09-03'}

def test_cnes_real_observed_field(source):
    row=cnes();item=cnes_record(row,source,{'123456':('1234567','BA')})
    assert item.id=='cnes:0000123' and item.source.reference_date=='2025-09-03'

def test_municipal_management_does_not_imply_sus(source):
    row=cnes()|{'estabelecimento_faz_atendimento_ambulatorial_sus':'NAO','descricao_esfera_administrativa':'MUNICIPAL'}
    assert cnes_record(row,source,{}) is None

def test_disabled_health_unit_excluded(source):assert cnes_record(cnes()|{'codigo_motivo_desabilitacao_estabelecimento':'04'},source,{}) is None

def test_wrong_cnes_schema_fails(source):
    row=cnes();row['estabelecimento_possui_atendimento_ambulatorial_sus']=row.pop('estabelecimento_faz_atendimento_ambulatorial_sus')
    with pytest.raises(ValueError):cnes_record(row,source,{})

def test_inep_filter_and_services(source,database):
    assert inep_record(inep(),source,municipality_lookup(database)).declared_services==['nursery']
    assert inep_record(inep()|{'TP_DEPENDENCIA':'4'},source,{}) is None
    assert inep_record(inep()|{'TP_SITUACAO_FUNCIONAMENTO':'2'},source,{}) is None

def test_bad_geo_not_invented(source,database):
    item=inep_record(inep()|{'NU_LATITUDE':'0','NU_LONGITUDE':'0'},source,municipality_lookup(database))
    assert item.latitude is None and item.longitude is None

def test_source_is_hashed_from_bytes(tmp_path):
    p=tmp_path/'x.csv';p.write_bytes(b'abc')
    result=file_source(p,'test','https://example.org/x','2025')
    assert result.snapshot_sha256=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

def test_json_file_refuses_ambiguous_records(tmp_path):
    path=tmp_path/'records.json';path.write_bytes(b'[{"id":"valid"}]')
    assert json_records(path)==[{'id':'valid'}]
    path.write_bytes(b'[{"id":"wrong","id":"valid"}]')
    with pytest.raises(ValueError,match='duplicate_json_key'):json_records(path)

def test_place_idempotency_and_meaningful_changes(database,place):
    with database.session() as s:assert upsert_place(s,place)=='inserted'
    other=place.model_copy(update={'source':place.source.model_copy(update={'collected_at':now(),'snapshot_sha256':'b'*64})})
    with database.session() as s:assert upsert_place(s,other)=='unchanged'
    changed=other.model_copy(update={'name':'Escola Sintética Renomeada'})
    with database.session() as s:assert upsert_place(s,changed)=='updated'
    with database.session() as s:
        history=list(s.scalars(select(Change).order_by(Change.at)))
        assert len(history)==2 and history[0].before is None
        assert history[1].fields==['name']

def test_failed_import_rolls_back_entire_file(database,source):
    with pytest.raises(ValueError):import_places(database,[inep(),{'wrong':'schema'}],source,'inep')
    with database.session() as s:
        assert s.scalar(select(func.count()).select_from(Place))==0
        assert s.scalar(select(Ingestion)).status=='failed'

def test_duplicate_input_rollback(database,source):
    with pytest.raises(ValueError):import_places(database,[inep(),inep()],source,'inep')
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Place))==0

def test_empty_file_not_success(database,source):
    with pytest.raises(ValueError):import_places(database,[],source,'inep')

def test_file_success_not_claim_national(database,source):
    result=import_places(database,[inep()],source,'inep')
    assert result['coverage']=='provided_file_only' and result['counts']['inserted']==1

def test_explicit_ineligibility_withdraws_search_without_destroying_history(database,source):
    import_places(database,[inep()],source,'inep')
    result=import_places(database,[inep()|{'TP_SITUACAO_FUNCIONAMENTO':'2'}],source,'inep')
    assert result['counts']['withdrawn']==1
    with database.session() as s:
        assert not s.get(Place,'inep:12345678').catalogue_eligible
        assert s.scalar(select(func.count()).select_from(Change))==2

def test_normalized_work_import(database,source):
    row={'id':'works:synthetic','kind':'work','name':'Obra Sintética','municipality_id':'1234567','state':'BA'}
    assert import_places(database,[row],source,'places')['counts']['inserted']==1

def test_zip_csv_stream(tmp_path):
    p=tmp_path/'sample.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('nested/file.csv','id;name\n1;Teste\n')
    assert list(csv_records(p,'nested/file.csv'))==[{'id':'1','name':'Teste'}]
    assert not (tmp_path/'nested').exists()

def test_ibge_crosswalk(tmp_path,database,source):
    p=tmp_path/'ibge.json';p.write_text(json.dumps([{'id':7654321,'nome':'Outro Sintético','microrregiao':{'mesorregiao':{'UF':{'sigla':'SP'}}}}]))
    assert import_ibge(database,p,source)==1
    assert municipality_lookup(database)['765432']==('7654321','SP')

def test_unknown_municipality_rejected(database,source):
    with pytest.raises(KeyError):import_places(database,[inep()|{'CO_MUNICIPIO':'0000000'}],source,'inep')

def test_finance_import_idempotent_and_rejects_correction(database,source):
    row={'id':'synthetic1','municipality_id':'1234567','instrument_id':'test','phase':'paid','cents':123,'period':'2025','recipient':'Fund','perspective':'federal'}
    assert import_finance(database,[row,row],source)==1
    assert import_finance(database,[row],source)==0
    with pytest.raises(ValueError):import_finance(database,[row|{'cents':124}],source)
    with database.session() as s:assert s.scalar(select(Finance)).cents==123

def test_transferegov_requires_reviewed_profile():
    columns={k:k.upper() for k in ('id','municipality_id','instrument_id','recipient','period','amount')}
    row={'ID':'1','MUNICIPALITY_ID':'1234567','INSTRUMENT_ID':'Test','RECIPIENT':'Fund','PERIOD':'2025','AMOUNT':'1.200,00'}
    args={'columns':columns,'phase':'transferred','nature':'event','perspective':'federal'}
    assert list(transferegov_rows([row],**args))[0]['cents']==120000
    with pytest.raises(ValueError):list(transferegov_rows([{'bad':1}],**args))

def test_pncp_is_contract_not_payment():
    rows=pncp_contracts({'data':[{'numeroControlePNCP':'synthetic','objetoContrato':'Objeto de teste','valorInicial':Decimal('120.50'),'unidadeOrgao':{'codigoIbge':'1234567'}}]})
    assert rows[0]['phase']=='contracted' and rows[0]['cents']==12050 and rows[0]['place_id'] is None

@pytest.mark.parametrize('url',['http://pncp.gov.br/x','https://example.org','https://pncp.gov.br:8443/x','https://u:p@pncp.gov.br','https://pncp.gov.br.evil.example/x','file:///tmp/x','https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/x'])
def test_operator_downloader_rejects_unreviewed_sources(url,tmp_path):
    with pytest.raises(ValueError):safe_download(url,tmp_path/'x')

def test_ftp_ibge_host_is_not_in_allowlist():
    assert 'ftp.ibge.gov.br' not in HOSTS
    assert 'servicodados.ibge.gov.br' in HOSTS

def test_private_resolution_rejected(monkeypatch,tmp_path):
    monkeypatch.setattr('bdt.ingest.socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(ValueError):safe_download('https://pncp.gov.br/x',tmp_path/'x')

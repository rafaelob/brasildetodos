import pytest
from decimal import Decimal
from pydantic import ValidationError
from bdt.domain import MoneyEvent, ObservationInput, Source, brl, cnpj, decimal_cents, financial_cells, fold

@pytest.mark.parametrize('value,expected',[('R$ 1.234,56',123456),('0,00',0),('-1,00',-100),('R$\u00a010,50',1050)])
def test_brl(value,expected):assert brl(value)==expected

@pytest.mark.parametrize('value',['1.000','1,234.56','12,3','1e5',1.2,'NaN','R$ 10'])
def test_ambiguous_money_rejected(value):
    with pytest.raises((ValueError,TypeError)):brl(value)

@pytest.mark.parametrize('value',[1.2,True,'NaN','Infinity','0.001'])
def test_fractional_binary_nonfinite_rejected(value):
    with pytest.raises(ValueError):decimal_cents(value)

def test_exact_money():assert decimal_cents(Decimal('300.21'))==30021

def test_alphanumeric_cnpj_not_destroyed():assert cnpj('12.ABC.345/01DE-35')=='12ABC34501DE35'

@pytest.mark.parametrize('value',[1234,'123','12.ABC.345/01DE-AA'])
def test_cnpj_bad_format(value):
    with pytest.raises(ValueError):cnpj(value)

def test_folding():assert fold('Educação ÁRVORE')=='educacao arvore'

def event(source,**changes):
    return dict(id='e1',source=source.model_dump(),municipality_id='1234567',instrument_id='test-2025',phase='transferred',cents=10000,period='2025',recipient='synthetic recipient',perspective='federal',**changes)

def test_financial_phases_are_not_one_total(source):
    rows=[]
    for i,(phase,amount) in enumerate([('agreed',100000000),('transferred',80000000),('contracted',95000000),('paid',30000000)]):
        row=event(source);row.update(id=str(i),phase=phase,cents=amount);rows.append(row)
    cells=financial_cells(rows)
    assert len(cells)==4
    assert {c['phase']:c['cents'] for c in cells}=={r['phase']:r['cents'] for r in rows}

def test_duplicate_event_not_counted_twice(source):assert financial_cells([event(source),event(source)])[0]['cents']==10000

def test_conflicting_duplicate_rejected(source):
    row=event(source);other=row|{'cents':20000}
    with pytest.raises(ValueError):financial_cells([row,other])

def test_snapshots_not_accumulated(source):
    a=event(source,nature='cumulative');b=a|{'id':'e2'}
    assert len(financial_cells([a,b]))==2

def test_cross_source_amounts_separated(source):
    a=event(source);b=a|{'source':source.model_copy(update={'dataset':'other'}).model_dump()}
    assert len(financial_cells([a,b]))==2

def test_instrument_scope_separated(source):
    a=event(source);b=a|{'id':'e2','instrument_id':'another'}
    assert len(financial_cells([a,b]))==2

@pytest.mark.parametrize('changes',[{'facility_id':'test:school'},{'relation_state':'direct'},{'cents':10.5},{'period':'2025-15'},{'period':'2025-02-30'}])
def test_invalid_finance_rejected(source,changes):
    with pytest.raises(ValidationError):MoneyEvent.model_validate(event(source)|changes)

def test_confirmed_link_requires_evidence(source):
    assert MoneyEvent.model_validate(event(source)|{'facility_id':'test:school','relation_state':'direct','evidence':'Document explicitly identifies this school'}).facility_id

@pytest.mark.parametrize('changes',[{'latitude':-10},{'latitude':-10,'longitude':-40},{'latitude':float('nan'),'longitude':-40,'geo_source':'test'}])
def test_bad_coordinates(place,changes):
    with pytest.raises(ValidationError):type(place).model_validate(place.model_dump()|changes)

def test_missing_geometry_valid(place):assert place.latitude is None

@pytest.mark.parametrize('url',['javascript:alert(1)','file:///etc/passwd','https://user:password@example.org','data:text/plain,hello'])
def test_source_links_schemes(source,url):
    with pytest.raises(ValidationError):Source.model_validate(source.model_dump()|{'url':url})

def test_source_timestamp_requires_zone(source):
    with pytest.raises(ValidationError):Source.model_validate(source.model_dump()|{'collected_at':'2025-01-01T12:00:00'})

@pytest.mark.parametrize('patch',[{'mode':'document'},{'consent':False},{'observed_on':'2999-01-01'},{'body':'too short'},{'reference_url':'javascript:bad()'}])
def test_observation_validation(patch):
    data={'place_id':'test:school','mode':'field','observed_on':'2025-01-01','body':'Synthetic observation of an exterior sign.','consent':True}|patch
    with pytest.raises(ValidationError):ObservationInput.model_validate(data)

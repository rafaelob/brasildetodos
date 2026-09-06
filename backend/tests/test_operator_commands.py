import json
from pathlib import Path
import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import select
from bdt.document_job import ingest_document, main
from bdt.evidence import Document
from bdt.storage import Database, Municipality, User
from bdt.territory import import_territory_snapshot


def pdf_file(tmp_path):
    path=tmp_path/'synthetic.pdf'
    document=canvas.Canvas(str(path));document.drawString(40,700,'CONVENIO 123456/2025 - synthetic test only.');document.save()
    return path


def test_native_operator_command_is_private(database,source,tmp_path,capsys):
    with database.session() as session:
        session.add(User(username='operator',password_hash='disabled',role='reviewer'))
    path=pdf_file(tmp_path);original=path.read_bytes()
    result=ingest_document(database,path,operator='operator',title='Synthetic agreement',dataset='synthetic-test',url='https://example.org/test.pdf')
    assert result['public'] is False and result['pages']==1 and path.read_bytes()==original
    main([str(path),'--database',str(database.engine.url),'--operator','operator','--title','Synthetic agreement','--dataset','synthetic-test','--url','https://example.org/test.pdf'])
    assert json.loads(capsys.readouterr().out)['document_id']==result['document_id']
    with database.session() as session:
        docs=list(session.scalars(select(Document)))
        assert len(docs)==1 and docs[0].state=='extracted' and 'CONVENIO 123456/2025' in docs[0].extraction['pages'][0]['text']


def test_operator_restriction_and_input_file(database,tmp_path):
    with pytest.raises(ValueError,match='file_missing'):
        ingest_document(database,tmp_path/'missing',operator='nobody',title='Synthetic document',dataset='test',url='https://example.org/test.pdf')
    with pytest.raises(ValueError,match='reviewer_operator_required'):
        ingest_document(database,pdf_file(tmp_path),operator='nobody',title='Synthetic document',dataset='test',url='https://example.org/test.pdf')
    with pytest.raises(SystemExit):
        main(['--help'])


def territory_snapshot(tmp_path,source,changes=None):
    path=tmp_path/'territory.db'
    db=Database('sqlite:///'+str(path));db.initialize()
    src=source.model_copy(update={'dataset':'ibge','record_id':'7654321','url':'https://servicodados.ibge.gov.br/api/v1/localidades/municipios'}).model_dump(mode='json')
    row={'id':'7654321','name':'Synthetic municipality','state':'BA','source':src}
    row.update(changes or {})
    with db.session() as session:
        session.add(Municipality(**row));session.add(User(username='never-copy-this-user',password_hash='disabled',role='contributor'))
    with db.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
    db.engine.dispose()
    return path,src


def test_territory_snapshot_preserves_dates_and_copies_no_accounts(database,tmp_path,source):
    path,src=territory_snapshot(tmp_path,source)
    result=import_territory_snapshot(database,path)
    assert result['records']==1 and result['fresh_upstream_request'] is False
    assert result['tables_copied']==['municipalities']
    assert result['original_collection_dates']==[src['collected_at']]
    with database.session() as session:
        assert session.get(Municipality,'7654321').source==src
        assert not list(session.scalars(select(User)))
    assert import_territory_snapshot(database,path)['records']==1
    with database.session() as session:
        session.get(Municipality,'7654321').name='A different existing record'
    with pytest.raises(ValueError,match='conflicts'):
        import_territory_snapshot(database,path)


@pytest.mark.parametrize('changes',[{'id':'123'},{'state':'XX'},{'name':''}])
def test_invalid_territory_snapshot_is_not_published(database,tmp_path,source,changes):
    path,_=territory_snapshot(tmp_path,source,changes)
    with pytest.raises(ValueError):
        import_territory_snapshot(database,path)
    with database.session() as session:
        assert session.get(Municipality,'7654321') is None


def test_territory_snapshot_requires_original_source(database,tmp_path,source):
    path,_=territory_snapshot(tmp_path,source,{'source':source.model_dump(mode='json')})
    with pytest.raises(ValueError,match='original_ibge_provenance'):
        import_territory_snapshot(database,path)
    with pytest.raises(ValueError,match='missing_or_too_large'):
        import_territory_snapshot(database,tmp_path/'missing.db')
    empty=tmp_path/'empty.db';db=Database('sqlite:///'+str(empty));db.initialize();db.engine.dispose()
    with pytest.raises(ValueError,match='snapshot_size'):
        import_territory_snapshot(database,empty)

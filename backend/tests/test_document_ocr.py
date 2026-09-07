"""OCR integration contract tests use a stub engine, never repeated OCR calls."""
import copy
import hashlib
import json

import pytest
from sqlalchemy import select

from bdt.document_ocr import main, process_ocr, recover_lease
from bdt.evidence import Audit, Document, DocumentInput, initialize_extensions, register_document, validate_excerpt
from bdt.storage import User


@pytest.fixture
def document(database,source,tmp_path):
    initialize_extensions(database)
    path=tmp_path/'synthetic-not-for-rendering.pdf'
    path.write_bytes(b'%PDF-synthetic-byte-fixture-not-a-real-rendered-document')
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    with database.session() as session:
        user=User(username='ocr_operator',password_hash='not-a-login',role='reviewer')
        session.add(user);session.flush()
        doc=register_document(session,DocumentInput(title='Synthetic OCR contract fixture',
            source=source.model_copy(update={'snapshot_sha256':sha})),user.id)
        doc.state='extracted'
        doc.extraction={'sha256':sha,'original_preserved':True,'pages':[
            {'page':1,'route':'native','text':'Native text stays intact','words':[],'tables':[]},
            {'page':2,'route':'ocr_candidate','text':'Native stamp','words':[],'tables':[]},
            {'page':3,'route':'ocr_candidate','text':'','words':[],'tables':[]}]}
        identity=doc.id
    return identity,path


def call(database,document,**kwargs):
    identity,path=document
    return process_ocr(database,identity,path,operator='ocr_operator',pages=[2],**kwargs)


def test_selected_ocr_is_private_preserves_native_and_original(database,document):
    identity,path=document;before=path.read_bytes();calls=[]
    def engine(path,number,**kwargs):
        calls.append((number,kwargs))
        return 'CONVENIO 123456/2025. Documento sintético.'
    result=call(database,document,engine=engine)
    assert calls==[(2,{'language':'por','timeout':90})]
    assert result['public'] is False and result['review_required'] is True
    assert before==path.read_bytes()
    with database.session() as session:
        doc=session.get(Document,identity)
        first,second,third=doc.extraction['pages']
        assert doc.state=='extracted'
        assert first['text']=='Native text stays intact' and 'ocr_candidate_text' not in first
        assert second['text']=='Native stamp'
        assert second['ocr_provenance']['original_sha256']==result['original_sha256']
        assert second['ocr_candidates'][0]['publication_allowed'] is False
        assert 'ocr_candidate_text' not in third
        validate_excerpt(doc,2,'CONVENIO 123456/2025')
        assert {a.action for a in session.scalars(select(Audit))}>={'ocr_started','ocr_completed'}


@pytest.mark.parametrize('pages',[[],[2,2],[True],[0],[1001],list(range(1,12))])
def test_invalid_page_selection(database,document,pages):
    identity,path=document
    with pytest.raises(ValueError,match='unique_ocr_pages'):
        process_ocr(database,identity,path,operator='ocr_operator',pages=pages)


@pytest.mark.parametrize('kwargs',[{'language':'pt-BR'},{'language':'por;cmd'}, {'timeout':0},{'timeout':301},{'timeout':True}])
def test_invalid_language_or_budget(database,document,kwargs):
    with pytest.raises(ValueError,match='language_or_timeout'): call(database,document,**kwargs)


def test_missing_file_and_operator(database,document):
    identity,path=document
    with pytest.raises(ValueError,match='reviewer_operator'):
        process_ocr(database,identity,path,operator='unknown',pages=[2])
    path.unlink()
    with pytest.raises(ValueError,match='input_missing'): call(database,document)


def test_non_candidate_pages_do_not_call_engine(database,document):
    identity,path=document
    for pages in ([1],[4]):
        with pytest.raises(ValueError,match='not_an_inspected_ocr_candidate'):
            process_ocr(database,identity,path,operator='ocr_operator',pages=pages,engine=lambda *a,**k:pytest.fail('must not OCR'))


def test_second_ocr_requires_explicit_review(database,document):
    call(database,document,engine=lambda *a,**k:'first reviewed later')
    with pytest.raises(ValueError,match='already_has_ocr'): call(database,document)


@pytest.mark.parametrize('value', [None, '', 'x'*200001], ids=['none', 'empty', 'oversized'])
def test_unusable_text_rolls_back_and_releases_lease(database,document,value):
    with pytest.raises(ValueError,match='text_missing_or_budget'):
        call(database,document,engine=lambda *a,**k:value)
    with database.session() as session:
        doc=session.get(Document,document[0]);assert doc.state=='extracted'
        assert 'ocr_candidate_text' not in doc.extraction['pages'][1]


def test_all_selected_pages_are_atomic(database,document):
    def engine(path,number,**kwargs):
        if number==3:raise RuntimeError('private arbitrary engine error must not enter audit')
        return 'valid first candidate'
    with pytest.raises(RuntimeError):
        process_ocr(database,document[0],document[1],operator='ocr_operator',pages=[2,3],engine=engine)
    with database.session() as session:
        doc=session.get(Document,document[0]);assert doc.state=='extracted'
        assert 'ocr_candidate_text' not in doc.extraction['pages'][1]
        entry=session.scalar(select(Audit).where(Audit.action=='ocr_failed'))
        assert entry.detail=={'error_type':'RuntimeError'}


def test_hash_change_aborts_without_overwrite(database,document):
    document[1].write_bytes(document[1].read_bytes()+b'changed')
    with pytest.raises(ValueError,match='hash_mismatch'): call(database,document)


def test_file_change_during_ocr_is_not_committed(database,document):
    def engine(path,*args,**kwargs):
        path.write_bytes(path.read_bytes()+b'changed')
        return 'apparently usable text'
    with pytest.raises(ValueError,match='changed_during_ocr'): call(database,document,engine=engine)
    with database.session() as session:
        assert 'ocr_candidate_text' not in session.get(Document,document[0]).extraction['pages'][1]


def test_competing_run_cannot_claim_same_document(database,document):
    def engine(*a,**k):
        with pytest.raises(ValueError,match='completed_native_inspection'):
            call(database,document,engine=lambda *a,**k:pytest.fail('concurrent engine started'))
        return 'first run wins'
    call(database,document,engine=engine)


def test_revoked_operator_cannot_complete(database,document):
    def engine(*a,**k):
        with database.session() as session:
            session.scalar(select(User).where(User.username=='ocr_operator')).role='disabled'
        return 'candidate must stay uncommitted'
    with pytest.raises(ValueError,match='reviewer_operator'): call(database,document,engine=engine)
    with database.session() as session:
        doc=session.get(Document,document[0]);assert doc.state=='extracted'
        assert 'ocr_candidate_text' not in doc.extraction['pages'][1]


def test_lease_lost_does_not_overwrite_new_extraction(database,document):
    def engine(*a,**k):
        with database.session() as session:
            doc=session.get(Document,document[0]);doc.state='extracted'
            doc.extraction={'sha256':doc.source['snapshot_sha256'],'pages':[],'new_version':True}
        return 'obsolete candidate'
    with pytest.raises(ValueError,match='lease_lost'): call(database,document,engine=engine)
    with database.session() as session:
        assert session.get(Document,document[0]).extraction['new_version'] is True


def test_recover_exact_abandoned_lease(database,document,capsys):
    identity,_=document;lease='ocr_'+'a'*12
    with database.session() as session:session.get(Document,identity).state=lease
    with pytest.raises(ValueError,match='not_current'):
        recover_lease(database,identity,operator='ocr_operator',expected_lease='ocr_'+'b'*12)
    with pytest.raises(ValueError,match='invalid_expected'):
        recover_lease(database,identity,operator='ocr_operator',expected_lease='any')
    main(['--database',str(database.engine.url),'--document',identity,'--operator','ocr_operator','--recover-lease',lease])
    assert json.loads(capsys.readouterr().out)['public'] is False
    with database.session() as session:assert session.get(Document,identity).state=='extracted'


@pytest.mark.parametrize('tail',[[],['--path','test.pdf'],['--recover-lease','ocr_'+'a'*12,'--pages','2']])
def test_cli_requires_exclusive_explicit_mode(tail):
    with pytest.raises(SystemExit):main(['--database','sqlite://','--document','x','--operator','x',*tail])

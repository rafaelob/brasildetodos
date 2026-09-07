# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import transferegov_catalog_probe as probe


def test_only_referenced_same_origin_scripts_and_public_links():
    result=probe.inspect_index('''<script src="/static/index.js"></script><script src="https://elsewhere.invalid/x.js"></script>
    <script>fetch('/downloads/list');</script><a href="/downloads/sample.csv.zip">Data</a>''')
    assert result['script_urls']==[probe.BASE+'/static/index.js']
    assert result['download_links']==[probe.BASE+'/downloads/sample.csv.zip']
    assert result['inline_summary']['static_reference_candidates']==['/downloads/list']


@pytest.mark.parametrize('url',['http://api-publica.transferegov.gestao.gov.br/a',
 'https://api-publica.transferegov.gestao.gov.br.evil.invalid/a','//elsewhere.invalid/a',
 'https://person:password@api-publica.transferegov.gestao.gov.br/a','/x?q=secret','/x#fragment','/x\nheader'])
def test_unreviewed_reference_refused(url):
    with pytest.raises(ValueError):probe.reviewed_reference(url)


def test_preserves_get_schema_without_executing_operations():
    data={'openapi':'3.1.0','paths':{'/instruments':{'get':{'summary':'test','parameters':[]},'post':{'summary':'no'}}},
          'components':{'schemas':{'test':{'type':'object'}}}}
    result=probe.inspect_schema(data)
    assert result['paths']['/instruments']=={'summary':'test','parameters':[]}
    assert result['schemas']==data['components']['schemas']
    with pytest.raises(ValueError):probe.inspect_schema({'paths':[]})


def test_actual_files_and_failures_do_not_become_success(tmp_path):
    def loader(url,path,max_bytes):
        if url==probe.INDEX:text='<script>fetch("/downloads/list")</script>'
        elif '/parcerias/' in url:text=json.dumps({'openapi':'3.1','paths':{'/test':{'get':{}}}})
        else:raise ConnectionError('private transport string never exported')
        path.write_text(text)
        return {'url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'bytes':len(text)}
    report=probe.run(tmp_path/'out',loader=loader)
    assert [x['status'] for x in report['sources']]==['inspected','schema_received','failed']
    assert report['records_imported']==0
    assert 'private transport string' not in json.dumps(report)
    assert (tmp_path/'out/parcerias-schema.json').is_file()
    with pytest.raises(FileExistsError):probe.run(tmp_path/'out',loader=loader)

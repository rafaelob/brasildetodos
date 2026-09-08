import json
import sys
from bdt.cli import main


def test_cli_local_import_lifecycle(tmp_path,monkeypatch,capsys):
    url=f"sqlite:///{tmp_path/'cli.db'}"
    def run(*args):
        monkeypatch.setattr(sys,'argv',['bdt','--database',url,*map(str,args)]);main();return capsys.readouterr().out
    assert 'schema_version' in run('init-db')
    p=tmp_path/'ibge.json';p.write_text(json.dumps([{'id':1234567,'nome':'Synthetic','microrregiao':{'mesorregiao':{'UF':{'sigla':'BA'}}}}]))
    assert 'municipalities' in run('import-ibge',p,'--url','https://example.org/test','--reference-date','2025')
    p=tmp_path/'places.json';p.write_text(json.dumps([{'id':'test:cli','kind':'school','name':'Synthetic School','municipality_id':'1234567','state':'BA'}]))
    assert 'inserted' in run('import-places',p,'--url','https://example.org/test','--reference-date','2025')
    monkeypatch.setattr('bdt.cli.getpass.getpass',lambda *a:'synthetic-test-password')
    assert 'reviewer' in run('create-user','reviewer','--role','reviewer')


def test_cli_subparsers_registered(monkeypatch, capsys):
    import pytest
    monkeypatch.setattr(sys, 'argv', ['bdt', '--help'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'import-transferegov-finance' in out
    assert 'sync-resources' in out


# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checklist fixtures test the auditor, never seed the application catalog."""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('bdt_plan_inventory', ROOT / 'ops/plan_inventory.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_current_history_and_exact_document_hash_are_separate(tmp_path):
    current = write(tmp_path, 'TODO.md', '# Dados\n- [x] D01 Coletar\n- [ ] D02 Validar\n')
    write(tmp_path, 'docs/history/old.md', '- [ ] D01 Coletar\n')
    report = audit.inventory(tmp_path)
    assert report['summary'] == {
        'documents_scanned': 2, 'checkbox_occurrences': 3,
        'active_checked': 1, 'active_unchecked': 1,
        'historical_checked': 0, 'historical_unchecked': 1,
        'opposing_active_checkboxes': 0, 'reused_identifiers_with_different_text': 0,
    }
    entry = next(item for item in report['documents'] if item['path'] == 'TODO.md')
    assert entry['sha256'] == hashlib.sha256(current.read_bytes()).hexdigest()
    assert report['feature_completion_certified'] is False
    assert report['repository_modified'] is False


@pytest.mark.parametrize('fence', ['```', '~~~', '````'])
def test_code_examples_do_not_become_backlog(fence):
    text = f'{fence}markdown\n- [x] Not a real task\n{fence}\n- [ ] Real task\n'
    tasks = audit.parse_tasks(text, 'TODO.md')
    assert [task['text'] for task in tasks] == ['Real task']
    assert tasks[0]['line'] == 4


def test_shorter_or_wrong_fence_does_not_close_block():
    tasks = audit.parse_tasks('````\n```\n- [ ] hidden\n~~~\n- [ ] hidden too\n````\n- [ ] shown', 'TODO.md')
    assert [task['text'] for task in tasks] == ['shown']


def test_unclosed_fence_is_not_interpreted_as_tasks():
    assert audit.parse_tasks('```text\n- [x] example', 'TODO.md') == []


def test_headings_locations_identifiers_and_unicode_are_preserved():
    tasks = audit.parse_tasks('# Brasil\n## Saúde\n- [X] **D01** Validar município\n# Operação\n1. [ ] P02.1 Restaurar', 'docs/PLAN.md')
    assert tasks[0]['headings'] == ['Brasil', 'Saúde']
    assert tasks[0]['identifier'] == 'D01'
    assert tasks[0]['checked'] is True
    assert tasks[0]['text'] == '**D01** Validar município'
    assert tasks[1]['headings'] == ['Operação']
    assert tasks[1]['identifier'] == 'P02.1'


def test_conflicting_checkboxes_are_reported_not_resolved(tmp_path):
    write(tmp_path, 'TODO.md', '- [ ] D01 Conferir fonte\n')
    write(tmp_path, 'docs/ROADMAP.md', '- [x] D01 Conferir fonte\n')
    report = audit.inventory(tmp_path)
    assert report['summary']['opposing_active_checkboxes'] == 1
    assert [item['checked'] for item in report['tasks']] == [False, True]
    assert len(report['opposing_active_checkboxes'][0]['occurrences']) == 2
    assert not report['feature_completion_certified']


def test_reused_identifier_does_not_silently_merge_different_scope(tmp_path):
    write(tmp_path, 'TODO.md', '- [x] D01 Download\n- [ ] D01 Publicação\n')
    result = audit.inventory(tmp_path)
    assert result['summary']['checkbox_occurrences'] == 2
    assert result['summary']['opposing_active_checkboxes'] == 0
    assert result['reused_identifiers'][0]['identifier'] == 'D01'


def test_only_declared_markdown_scope_is_read(tmp_path):
    write(tmp_path, 'README.md', '- [ ] Documentation\n')
    write(tmp_path, 'docs/STATUS.md', '- [ ] Status\n')
    write(tmp_path, 'secrets.md', '- [ ] not in scan\n')
    write(tmp_path, '.env', '- [ ] not in scan\n')
    write(tmp_path, 'docs/config.json', '{"secret":"not in scan"}')
    report = audit.inventory(tmp_path)
    assert [item['path'] for item in report['documents']] == ['README.md', 'docs/STATUS.md']
    assert 'not in scan' not in json.dumps(report)
    assert str(tmp_path) not in json.dumps(report)


def test_nested_directory_links_are_not_traversed(tmp_path):
    external = tmp_path / 'outside'
    write(external, 'private.md', '- [ ] outside record\n')
    root = tmp_path / 'repository'
    (root / 'docs').mkdir(parents=True)
    (root / 'docs/linked').symlink_to(external, target_is_directory=True)
    assert audit.inventory(root)['documents'] == []


def test_markdown_symlink_is_rejected(tmp_path):
    external = write(tmp_path, 'outside.txt', '- [ ] outside\n')
    root = tmp_path / 'repository'
    (root / 'docs').mkdir(parents=True)
    (root / 'docs/linked.md').symlink_to(external)
    with pytest.raises(ValueError, match='symlink'):
        audit.inventory(root)


def test_document_limit_is_enforced(tmp_path, monkeypatch):
    write(tmp_path, 'TODO.md', '- [ ] ' + 'a' * 100)
    monkeypatch.setattr(audit, 'MAX_DOCUMENT_BYTES', 32)
    with pytest.raises(ValueError, match='too_large'):
        audit.inventory(tmp_path)


def test_invalid_encoding_is_not_silently_replaced(tmp_path):
    (tmp_path / 'TODO.md').write_bytes(b'- [ ] \xff\n')
    with pytest.raises(ValueError, match='invalid_utf8'):
        audit.inventory(tmp_path)


def test_bom_and_repeatable_order(tmp_path):
    (tmp_path / 'TODO.md').write_bytes(b'\xef\xbb\xbf- [ ] D01 First\n')
    write(tmp_path, 'docs/Z.md', '- [ ] Z02 Last\n')
    write(tmp_path, 'docs/A.md', '- [x] A03 Second\n')
    before = {path: path.read_bytes() for path in tmp_path.rglob('*.md')}
    assert audit.inventory(tmp_path) == audit.inventory(tmp_path)
    assert before == {path: path.read_bytes() for path in tmp_path.rglob('*.md')}
    assert audit.inventory(tmp_path)['tasks'][0]['identifier'] == 'D01'


def test_cli_creates_report_but_refuses_to_overwrite(tmp_path, capsys):
    write(tmp_path, 'TODO.md', '- [ ] Actual task\n')
    target = tmp_path / 'report.json'
    args = ['--root', str(tmp_path), '--output', str(target)]
    assert audit.main(args) == 0
    original = target.read_bytes()
    assert json.loads(original)['summary']['checkbox_occurrences'] == 1
    assert audit.main(args) == 1
    assert target.read_bytes() == original
    error = json.loads(capsys.readouterr().err)
    assert error == {'status': 'failed', 'error': 'FileExistsError'}
    assert str(tmp_path) not in json.dumps(error)


def test_nonexistent_root_fails_explicitly(tmp_path, capsys):
    assert audit.main(['--root', str(tmp_path / 'missing')]) == 1
    assert json.loads(capsys.readouterr().err)['error'] == 'plan_root_not_directory'


def test_empty_repository_does_not_claim_completion(tmp_path):
    report = audit.inventory(tmp_path)
    assert report['summary']['checkbox_occurrences'] == 0
    assert report['feature_completion_certified'] is False
    assert 'completion_percentage' not in report

"""Operator CLI for the persistent OCR queue."""
import hashlib
import json
import sys

import pytest

from bdt.cli import main
from bdt.evidence import DocumentInput, initialize_extensions, register_document
from bdt.storage import Database, User


@pytest.fixture
def seeded(tmp_path, source):
    url = f"sqlite:///{tmp_path / 'ocr-cli.db'}"
    database = Database(url)
    database.initialize()
    initialize_extensions(database)
    sha = hashlib.sha256(b'synthetic-ocr-cli-fixture-not-a-real-document').hexdigest()
    with database.session() as session:
        user = User(username='cli_operator', password_hash='not-a-login', role='reviewer')
        session.add(user)
        session.flush()
        document = register_document(session, DocumentInput(
            title='Synthetic CLI OCR fixture',
            source=source.model_copy(update={'snapshot_sha256': sha})), user.id)
        document.state = 'extracted'
        document.extraction = {'sha256': sha, 'extractor_version': 'synthetic-v1', 'pages': [
            {'page': 1, 'route': 'native', 'text': 'native', 'words': [], 'tables': []},
            {'page': 2, 'route': 'ocr_candidate', 'text': '', 'words': [], 'tables': []}]}
        identity = document.id
    database.engine.dispose()
    return url, identity


def run(monkeypatch, capsys, url, *args):
    monkeypatch.setattr(sys, 'argv', ['bdt', '--database', url, *map(str, args)])
    main()
    return json.loads(capsys.readouterr().out)


def test_cli_enqueue_list_cancel_retry_purge(seeded, monkeypatch, capsys):
    url, identity = seeded
    created = run(monkeypatch, capsys, url, 'ocr-queue', 'enqueue', identity,
                  '--operator', 'cli_operator', '--pages', '2')
    assert created['status'] == 'queued' and created['pages'] == [2]

    listed = run(monkeypatch, capsys, url, 'ocr-queue', 'list')
    assert [row['id'] for row in listed] == [created['id']]
    assert 'original_sha256' not in listed[0]

    cancelled = run(monkeypatch, capsys, url, 'ocr-queue', 'cancel', created['id'],
                    '--operator', 'cli_operator')
    assert cancelled['status'] == 'cancelled'
    retried = run(monkeypatch, capsys, url, 'ocr-queue', 'retry', created['id'],
                  '--operator', 'cli_operator')
    assert retried['status'] == 'queued'

    preview = run(monkeypatch, capsys, url, 'ocr-queue', 'purge', '--dry-run')
    assert preview['dry_run'] is True and preview['deleted'] == 0
    assert run(monkeypatch, capsys, url, 'ocr-queue', 'reap') == {'requeued': 0, 'failed': 0}


def test_cli_requires_a_reviewer_operator(seeded, monkeypatch, capsys):
    url, identity = seeded
    with pytest.raises(ValueError, match='active_reviewer_operator_required'):
        run(monkeypatch, capsys, url, 'ocr-queue', 'enqueue', identity,
            '--operator', 'missing', '--pages', '2')

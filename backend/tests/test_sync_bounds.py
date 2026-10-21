"""Synthetic local pages: transport success is not a completeness certificate."""
import hashlib
import json

import pytest

from bdt.sync import collect, collected_rows
from test_sync import loader_for, payload, plan


def failed(folder):
    report = json.loads((folder / 'collection.json').read_text())
    assert report['status'] == 'failed'
    assert report['national_catalog_certified'] is False


@pytest.mark.parametrize('page', [False, 0.0])
def test_collect_requires_integer_response_page(tmp_path, page):
    with pytest.raises(ValueError, match='unexpected_response_page'):
        collect(plan(response_page_field='page'), tmp_path,
                loader=loader_for([payload(1, page=page), payload(page=2)]))
    failed(tmp_path)


def test_collect_enforces_record_budget(tmp_path):
    with pytest.raises(ValueError, match='response_page_size_exceeded'):
        collect(plan(), tmp_path, loader=loader_for([payload(1, 2, 3), payload()]))
    failed(tmp_path)


def test_collect_checks_byte_budget_before_hashing(tmp_path, monkeypatch):
    import bdt.sync as sync
    hashed = []
    real_hash = sync.file_hash
    monkeypatch.setattr(sync, 'file_hash', lambda path: hashed.append(path) or real_hash(path))
    with pytest.raises(ValueError, match='collection_page_not_regular_or_too_large'):
        collect(plan(max_bytes_per_page=10), tmp_path, loader=loader_for([payload(1), payload()]))
    assert hashed == []
    failed(tmp_path)


@pytest.mark.parametrize('cached', [False, True])
def test_collect_refuses_symlink_pages(tmp_path, cached):
    folder = tmp_path / 'collection'
    folder.mkdir()
    target = tmp_path / 'outside.json'
    target.write_text(json.dumps(payload(1), sort_keys=True))
    if cached:
        collect(plan(), folder, loader=loader_for([payload(1), payload()]))
        (folder / 'page-000000.json').unlink()
    (folder / 'page-000000.json').symlink_to(target)
    original = target.read_bytes()
    with pytest.raises(ValueError, match='collection_page_not_regular_or_too_large'):
        collect(plan(), folder, loader=loader_for([payload(1), payload()]))
    assert target.read_bytes() == original
    failed(folder)


@pytest.mark.parametrize('status', [200.0, '200', True])
def test_collect_requires_integer_http_status(tmp_path, status):
    loader = loader_for([payload(1), payload()])
    def with_status(url, path, max_bytes):
        return loader(url, path, max_bytes) | {'status_code': status}
    with pytest.raises(ValueError, match='unexpected_page_http_status'):
        collect(plan(), tmp_path, loader=with_status)
    failed(tmp_path)


def rewrite_first_page(folder, report, value):
    raw = json.dumps(value, sort_keys=True).encode()
    (folder / 'page-000000.json').write_bytes(raw)
    count = len(value['estabelecimentos'])
    report['pages'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), records=count)
    report['records'] = count


@pytest.mark.parametrize('page', [False, 0.0])
def test_revalidation_requires_integer_response_page(tmp_path, page):
    report = collect(plan(response_page_field='page'), tmp_path,
                     loader=loader_for([payload(1, page=0), payload(page=2)]))
    rewrite_first_page(tmp_path, report, payload(1, page=page))
    with pytest.raises(ValueError, match='collection_response_page_mismatch'):
        list(collected_rows(tmp_path, report))


def test_revalidation_enforces_record_budget(tmp_path):
    report = collect(plan(), tmp_path, loader=loader_for([payload(1), payload()]))
    rewrite_first_page(tmp_path, report, payload(1, 2, 3))
    with pytest.raises(ValueError, match='collection_page_size_exceeded'):
        list(collected_rows(tmp_path, report))

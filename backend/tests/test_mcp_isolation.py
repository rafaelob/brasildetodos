# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP staging stays off the public API and never certifies a national catalog."""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.abc
import json
import sys
import tomllib
from pathlib import Path

import httpx
import pytest

from bdt.ingest import HOSTS
from bdt_mcp import staging as staging_mod
from bdt_mcp.staging import (
    cnes_rest_index_0,
    describe_tools,
    ibge_download_municipios,
    inep_describe_schema,
    inep_download_file,
    inep_search_dataset,
    obrasgov_fetch_page,
    pncp_fetch_page,
    tool_result,
    transferegov_fetch_page,
)

ROOT = Path(__file__).resolve().parents[2]
BDT = ROOT / 'backend' / 'bdt'


def _fake_payload(url: str) -> dict | list:
    if 'localidades/municipios' in url:
        return [{'id': 1234567, 'nome': 'Synthetic'}]
    if 'cnes/estabelecimentos' in url:
        return {'estabelecimentos': [{'codigo_cnes': '1'}]}
    return {'data': [{'id': 'synthetic'}], 'totalPaginas': 9, 'totalRegistros': 99,
            'numeroPagina': 1, 'total_pages': 9, 'total_items': 99, 'page_number': 1}


@pytest.fixture(autouse=True)
def staging_isolation(tmp_path, monkeypatch):
    jail = tmp_path / 'mcp-jail'
    jail.mkdir()
    monkeypatch.setenv('BDT_MCP_JAIL', str(jail))

    def fake(url, target, max_bytes=None, **kwargs):
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname
        if host not in HOSTS:
            raise ValueError('Download source is not in the reviewed HTTPS allowlist')
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(_fake_payload(url)).encode()
        path.write_bytes(raw)
        return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                'collected_at': '2026-09-09T00:00:00+00:00', 'status_code': 200}

    monkeypatch.setattr(staging_mod, 'DOWNLOADER', fake)

    def blocked(*_a, **_k):
        raise AssertionError('zero live government HTTP in MCP tests')

    monkeypatch.setattr('bdt.ingest.httpx.Client', blocked)
    monkeypatch.setattr('httpx.Client', blocked)
    return jail


def _imported_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def _follow_relative(path: Path, node: ast.ImportFrom) -> Path | None:
    current = path.parent
    for _ in range(node.level - 1):
        current = current.parent
    if node.module:
        current = current.joinpath(*node.module.split('.'))
    py, pkg = current.with_suffix('.py'), current / '__init__.py'
    if py.is_file():
        return py
    if pkg.is_file():
        return pkg
    return None


def api_import_graph() -> set[Path]:
    start = BDT / 'api.py'
    seen: set[Path] = set()
    stack = [start]
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        if path.parent != BDT and BDT not in path.parents:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                target = _follow_relative(path, node)
                if target is not None:
                    stack.append(target)
    return seen


def test_api_source_and_import_graph_never_mention_bdt_mcp():
    graph = api_import_graph()
    assert BDT / 'api.py' in graph
    for path in graph:
        text = path.read_text(encoding='utf-8')
        assert 'bdt_mcp' not in text
        names = _imported_names(ast.parse(text, filename=str(path)))
        assert not any(name == 'bdt_mcp' or name.startswith('bdt_mcp.') for name in names)


def test_cli_default_path_and_web_do_not_import_bdt_mcp():
    cli = (BDT / 'cli.py').read_text(encoding='utf-8')
    assert 'bdt_mcp' not in cli
    names = _imported_names(ast.parse(cli, filename='cli.py'))
    assert not any(name == 'bdt_mcp' or name.startswith('bdt_mcp.') for name in names)
    web = ROOT / 'web'
    for path in web.rglob('*'):
        if path.suffix.lower() not in {'.mjs', '.ts', '.tsx', '.js', '.json'} or 'node_modules' in path.parts:
            continue
        assert 'bdt_mcp' not in path.read_text(encoding='utf-8', errors='ignore')


def test_cli_imports_without_mcp_package(monkeypatch):
    class BlockMcp(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == 'mcp' or fullname.startswith('mcp.'):
                raise ImportError('mcp extra is not installed')
            return None

    for name in list(sys.modules):
        if name == 'mcp' or name.startswith('mcp.') or name == 'bdt.cli':
            sys.modules.pop(name, None)
    monkeypatch.setattr(sys, 'meta_path', [BlockMcp(), *sys.meta_path])
    import bdt.cli
    assert callable(bdt.cli.main)
    assert 'bdt_mcp' not in getattr(bdt.cli, '__dict__', {})


def test_mcp_is_optional_extra_not_core_dependency():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    core = [item.split('==')[0].split('[')[0].strip().lower() for item in project['project']['dependencies']]
    assert 'mcp' not in core
    assert project['project']['optional-dependencies']['mcp-sources'] == ['mcp==1.13.1']
    assert project['project']['scripts']['bdt-mcp'] == 'bdt_mcp.server:main'
    example = json.loads((ROOT / '.mcp.json.example').read_text(encoding='utf-8'))
    assert example['mcpServers']['brasildetodos-sources']['command'] == 'bdt-mcp'


def test_console_script_requires_extra(monkeypatch):
    from bdt_mcp import server

    def missing():
        raise ImportError(server.OPERATOR_INSTALL)

    monkeypatch.setattr(server, '_load_fastmcp', missing)
    with pytest.raises(ImportError, match='mcp-sources'):
        server.main()


def test_every_tool_result_is_not_nationally_certified(staging_isolation):
    csv_path = staging_isolation / 'escola.csv'
    csv_path.write_text('CO_ENTIDADE;NO_ENTIDADE;CO_MUNICIPIO;TP_DEPENDENCIA;TP_SITUACAO_FUNCIONAMENTO\n', encoding='utf-8')
    results = [
        describe_tools(),
        ibge_download_municipios(),
        pncp_fetch_page(start='20260904', end='20260904'),
        transferegov_fetch_page(),
        obrasgov_fetch_page(),
        cnes_rest_index_0(),
        inep_search_dataset(query='censo'),
        inep_describe_schema(path='escola.csv'),
    ]
    for row in results:
        assert row['national_catalog_certified'] is False
        assert row['catalog_written'] is False
    with pytest.raises(ValueError, match='national_catalog_certified_must_be_false'):
        tool_result(national_catalog_certified=True)


def test_cnes_index_zero_refuses_national_pretence():
    row = cnes_rest_index_0()
    assert row['offset'] == 0 and row['page_index'] == 0
    assert row['national_catalog_certified'] is False
    assert 'not_brazil' in row['scope']
    with pytest.raises(ValueError, match='index_0_only'):
        cnes_rest_index_0(offset=20)
    with pytest.raises(ValueError, match='index_0_only'):
        cnes_rest_index_0(offset=1)
    with pytest.raises(ValueError):
        pncp_fetch_page(start='20260904', end='20260904', page=2)


def test_inep_download_file_refuses_zip(staging_isolation):
    archive = staging_isolation / 'microdados.zip'
    archive.write_bytes(b'PK\x03\x04not-a-real-zip')
    with pytest.raises(ValueError, match='inep_zip_download_refused'):
        inep_download_file(url='https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025.zip')
    with pytest.raises(ValueError, match='inep_zip_download_refused'):
        inep_download_file(path='microdados.zip')
    with pytest.raises(ValueError, match='inep_zip_download_refused'):
        inep_describe_schema(path='microdados.zip')


def test_path_jail_and_hosts_allowlist(tmp_path, staging_isolation):
    outside = tmp_path / 'secret.csv'
    outside.write_text('CO_ENTIDADE;NO_ENTIDADE;CO_MUNICIPIO;TP_DEPENDENCIA;TP_SITUACAO_FUNCIONAMENTO\n')
    with pytest.raises(ValueError, match='path_outside_operator_jail'):
        inep_describe_schema(path=str(outside))
    with pytest.raises(ValueError, match='path_outside_operator_jail'):
        inep_describe_schema(path='../secret.csv')
    with pytest.raises(ValueError, match='allowlist'):
        inep_download_file(url='https://example.org/censo.csv')
    assert staging_mod.HOSTS is HOSTS


def test_timeout_and_malformed_page_are_not_certified(monkeypatch, staging_isolation):
    def timeout(*_a, **_k):
        raise httpx.TimeoutException('synthetic')

    monkeypatch.setattr(staging_mod, 'DOWNLOADER', timeout)
    with pytest.raises(httpx.TimeoutException):
        pncp_fetch_page(start='20260904', end='20260904')

    def malformed(url, target, max_bytes=None, **kwargs):
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{')
        return {'url': url, 'sha256': 'a' * 64, 'bytes': 1,
                'collected_at': '2026-09-09T00:00:00+00:00', 'status_code': 200}

    monkeypatch.setattr(staging_mod, 'DOWNLOADER', malformed)
    with pytest.raises(ValueError, match='unreadable'):
        transferegov_fetch_page()
    with pytest.raises(ValueError, match='unreadable'):
        obrasgov_fetch_page()


def test_ibge_describe_only_without_sdk(monkeypatch, staging_isolation):
    monkeypatch.setattr(staging_mod, 'DOWNLOADER', None)
    monkeypatch.setattr(staging_mod, 'mcp_sdk_available', lambda: False)
    row = ibge_download_municipios()
    assert row['mode'] == 'describe'
    assert row['national_catalog_certified'] is False
    assert row['url'].startswith('https://servicodados.ibge.gov.br/')


def test_redelivered_probe_stays_uncertified():
    first = pncp_fetch_page(start='20260904', end='20260904')
    second = pncp_fetch_page(start='20260904', end='20260904')
    assert first['national_catalog_certified'] is False
    assert second['national_catalog_certified'] is False
    assert first['records'] == second['records']

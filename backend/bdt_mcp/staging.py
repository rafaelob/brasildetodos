# SPDX-License-Identifier: AGPL-3.0-or-later
"""One-page operator probes. Never a certified national catalog and never live in tests."""
from __future__ import annotations

import csv
import importlib.util
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from bdt.education_bulk import ANCHOR, REQUIRED
from bdt.ingest import CNES_URL, HOSTS, IBGE_URL
from bdt.resource_profiles import collection_plan
from bdt.sync import PagePlan, page_url

log = logging.getLogger('bdt_mcp')
DOWNLOADER = None
HEADER_BYTES = 256 * 1024
LOCAL_CSV_CAP = 1000
OPERATOR_INSTALL = (
    "bdt-mcp requires the optional extra mcp-sources: pip install -e '.[mcp-sources]'. "
    "Operator staging only; not the public API and not citizen IA querying the government."
)
INEP_CATALOG = (
    {
        'id': 'censo-escolar',
        'title': 'Microdados do Censo Escolar',
        'anchor': ANCHOR,
        'download_host': 'download.inep.gov.br',
        'mcp': 'ZIP download refused; use operator CLI import-inep',
    },
)


def mcp_sdk_available() -> bool:
    return importlib.util.find_spec('mcp') is not None


def tool_result(**fields):
    if fields.get('national_catalog_certified') not in (None, False):
        raise ValueError('national_catalog_certified_must_be_false')
    if fields.get('catalog_written') not in (None, False):
        raise ValueError('mcp_staging_must_not_write_catalog')
    payload = dict(fields)
    payload['national_catalog_certified'] = False
    payload['catalog_written'] = False
    return payload


def jail_root() -> Path:
    raw = os.environ.get('BDT_MCP_JAIL')
    root = Path(raw) if raw else Path(os.environ.get('BDT_DATA_DIR', 'data')) / 'mcp-staging'
    root = root.expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError('mcp_jail_not_directory')
    return resolved


def confined(path: str | Path, *, root: Path | None = None) -> Path:
    if path is None or str(path) == '' or '\x00' in str(path):
        raise ValueError('path_outside_operator_jail')
    base = (root or jail_root()).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    root_s = os.path.normcase(str(base))
    resolved_s = os.path.normcase(str(resolved))
    if resolved_s != root_s and not resolved_s.startswith(root_s + os.sep):
        raise ValueError('path_outside_operator_jail')
    return resolved


def _assert_allowlisted(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in HOSTS
            or parsed.port not in {None, 443} or parsed.username or parsed.password):
        raise ValueError('Download source is not in the reviewed HTTPS allowlist')
    return parsed.hostname


def _looks_zip(value: str, parsed=None) -> bool:
    text = value.lower()
    path = (parsed.path if parsed is not None else text).lower()
    return path.endswith('.zip') or '.zip?' in text or text.endswith('.zip')


def _int(value, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'invalid_{name}')
    return value


def _download(url: str, target: Path, max_bytes: int) -> dict:
    host = _assert_allowlisted(url)
    fetcher = DOWNLOADER
    if fetcher is None:
        from bdt.sync import download_retry
        fetcher = download_retry
    log.info('mcp_staging_fetch tool_host=%s bytes_budget=%s', host, max_bytes)
    return fetcher(url, target, max_bytes)


def _payload(path: Path):
    if path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError('mcp_probe_response_unreadable') from exc


def _probe_page(plan: PagePlan, *, folder: str, root_field: str, allow_empty_pncp: bool = False) -> dict:
    if plan.max_pages != 1:
        raise ValueError('mcp_probe_one_page_only')
    url = page_url(plan, 0)
    host = _assert_allowlisted(url)
    dest = confined(f'{folder}/page-000000.json')
    metadata = _download(url, dest, plan.max_bytes_per_page)
    empty = metadata.get('status_code') == 204 or dest.stat().st_size == 0
    if empty:
        if not allow_empty_pncp or plan.dataset != 'pncp_contracts':
            raise ValueError('unexpected_no_content_response')
        log.info('mcp_tool_ok tool=%s host=%s records=0 terminal=http_204', plan.dataset, host)
        return tool_result(tool=f'{folder}_fetch_page', dataset=plan.dataset, url=url, host=host,
                           path=str(dest), page_index=0, records=0, terminal='http_204_no_content',
                           scope='one_page_probe_not_national_census')
    payload = _payload(dest)
    rows = payload.get(root_field) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError('resource_response_schema_changed')
    log.info('mcp_tool_ok tool=%s host=%s records=%s', plan.dataset, host, len(rows))
    return tool_result(tool=f'{folder}_fetch_page', dataset=plan.dataset, url=url, host=host,
                       path=str(dest), page_index=0, records=len(rows),
                       bytes=metadata.get('bytes'), sha256=metadata.get('sha256'),
                       scope='one_page_probe_not_national_census')


def describe_tools() -> dict:
    return tool_result(
        tool='describe_tools',
        extra='mcp-sources',
        mcp_sdk=mcp_sdk_available(),
        tools=(
            'ibge_download_municipios', 'pncp_fetch_page', 'transferegov_fetch_page',
            'obrasgov_fetch_page', 'cnes_rest_index_0', 'inep_search_dataset',
            'inep_describe_schema', 'inep_download_file',
        ),
        scope='operator_staging_describe_not_certified_catalog',
    )


def ibge_download_municipios(*, target: str = 'ibge/municipios.json') -> dict:
    dest = confined(target)
    if dest.suffix.lower() != '.json':
        raise ValueError('ibge_municipios_require_json_target')
    if not mcp_sdk_available() and DOWNLOADER is None:
        log.info('mcp_tool_ok tool=ibge_download_municipios mode=describe')
        return tool_result(tool='ibge_download_municipios', mode='describe', url=IBGE_URL,
                           target=str(dest), host='servicodados.ibge.gov.br',
                           propose_cli=['bdt', 'download', IBGE_URL, str(dest)],
                           scope='official_municipality_list_file_not_certified_national_catalog')
    metadata = _download(IBGE_URL, dest, 32 * 1024 * 1024)
    log.info('mcp_tool_ok tool=ibge_download_municipios bytes=%s', metadata.get('bytes'))
    return tool_result(tool='ibge_download_municipios', mode='downloaded', url=IBGE_URL,
                       path=str(dest), host='servicodados.ibge.gov.br',
                       bytes=metadata.get('bytes'), sha256=metadata.get('sha256'),
                       imported=False,
                       propose_cli=['bdt', 'import-ibge', str(dest), '--url', IBGE_URL,
                                    '--reference-date', 'DATA_DA_EDICAO'],
                       scope='official_municipality_list_file_not_certified_national_catalog')


def pncp_fetch_page(*, start: str, end: str, page: int = 1, page_size: int = 10) -> dict:
    if _int(page, name='page', minimum=1, maximum=1) != 1:
        raise ValueError('pncp_probe_page_1_only')
    plan = collection_plan('pncp_contracts', start=start, end=end,
                           page_size=_int(page_size, name='page_size', minimum=10, maximum=500),
                           max_pages=1)
    return _probe_page(plan, folder='pncp', root_field='data', allow_empty_pncp=True)


def transferegov_fetch_page(*, year: int | None = None, page: int = 1, page_size: int = 10) -> dict:
    _int(page, name='page', minimum=1, maximum=1)
    if year is not None:
        _int(year, name='year', minimum=2000, maximum=2100)
    plan = collection_plan('transferegov_special_plans', year=year,
                           page_size=_int(page_size, name='page_size', minimum=1, maximum=200),
                           max_pages=1)
    return _probe_page(plan, folder='transferegov', root_field='data')


def obrasgov_fetch_page(*, year: int | None = None, state: str | None = None,
                       page: int = 1, page_size: int = 10) -> dict:
    _int(page, name='page', minimum=1, maximum=1)
    if year is not None:
        _int(year, name='year', minimum=2000, maximum=2100)
    plan = collection_plan('obrasgov_projects', year=year, state=state,
                           page_size=_int(page_size, name='page_size', minimum=1, maximum=200),
                           max_pages=1)
    return _probe_page(plan, folder='obrasgov', root_field='data')


def cnes_rest_index_0(*, limit: int = 20, offset: int = 0) -> dict:
    if type(offset) is not int or offset != 0:
        raise ValueError('cnes_rest_probe_index_0_only')
    plan = PagePlan(
        dataset='cnes-rest-probe', url=CNES_URL, root='estabelecimentos', identity='codigo_cnes',
        page_parameter='offset', size_parameter='limit',
        page_size=_int(limit, name='limit', minimum=1, maximum=50),
        start=0, step=limit, max_pages=1, delay_seconds=0,
    )
    url = page_url(plan, 0)
    if 'offset=0' not in url:
        raise ValueError('cnes_rest_probe_index_0_only')
    host = _assert_allowlisted(url)
    dest = confined('cnes/page-000000.json')
    metadata = _download(url, dest, plan.max_bytes_per_page)
    payload = _payload(dest)
    rows = payload.get('estabelecimentos') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError('resource_response_schema_changed')
    log.info('mcp_tool_ok tool=cnes_rest_index_0 host=%s records=%s', host, len(rows))
    return tool_result(
        tool='cnes_rest_index_0', url=url, host=host, path=str(dest), offset=0, page_index=0,
        records=len(rows), bytes=metadata.get('bytes'), sha256=metadata.get('sha256'),
        scope='first_rest_page_is_not_brazil',
        limit_note='The first CNES REST page is not the national catalog.',
    )


def inep_search_dataset(*, query: str = '') -> dict:
    q = (query or '').casefold()
    hits = [item for item in INEP_CATALOG
            if not q or q in item['id'] or q in item['title'].casefold()]
    local = []
    root = jail_root()
    for index, path in enumerate(root.rglob('*.csv')):
        if index >= LOCAL_CSV_CAP:
            break
        try:
            confined(path, root=root)
        except ValueError:
            continue
        if q and q not in path.name.casefold():
            continue
        local.append({'path': path.relative_to(root).as_posix(), 'kind': 'local_csv'})
    log.info('mcp_tool_ok tool=inep_search_dataset hits=%s local=%s', len(hits), len(local))
    return tool_result(tool='inep_search_dataset', query=query, hits=hits, local_csv=local,
                       transport='local_only',
                       scope='local_dataset_search_not_national_microdata')


def inep_describe_schema(*, path: str) -> dict:
    target = confined(path)
    if target.suffix.lower() == '.zip' or _zip_magic(target):
        raise ValueError('inep_zip_download_refused')
    if not target.is_file() or target.suffix.lower() != '.csv':
        raise ValueError('inep_schema_requires_local_csv')
    raw = target.read_bytes()[:HEADER_BYTES + 1]
    if len(raw) > HEADER_BYTES and b'\n' not in raw[:HEADER_BYTES]:
        raise ValueError('school_header_budget')
    line = raw.split(b'\n', 1)[0].rstrip(b'\r')
    text = None
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            text = line.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError('school_encoding_requires_review')
    columns = tuple(next(csv.reader([text], delimiter=';', strict=True)))
    if not columns or any(not name or name.strip() != name for name in columns):
        raise ValueError('school_duplicate_or_ambiguous_columns')
    log.info('mcp_tool_ok tool=inep_describe_schema columns=%s', len(columns))
    return tool_result(tool='inep_describe_schema', path=str(target), columns=list(columns),
                       required_present=sorted(REQUIRED.intersection(columns)),
                       rows_not_read=True, scope='local_header_only_not_national_import')


def inep_download_file(*, url: str = '', path: str = '') -> dict:
    if url:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.hostname:
            _assert_allowlisted(url)
        if _looks_zip(url, parsed) or parsed.hostname == 'download.inep.gov.br':
            raise ValueError('inep_zip_download_refused')
    if path:
        if Path(path).suffix.lower() == '.zip' or str(path).lower().endswith('.zip'):
            raise ValueError('inep_zip_download_refused')
        target = confined(path)
        if _zip_magic(target):
            raise ValueError('inep_zip_download_refused')
        if target.suffix.lower() == '.csv':
            raise ValueError('inep_use_describe_schema_for_local_csv')
    raise ValueError('inep_zip_download_refused')


def _zip_magic(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return path.read_bytes()[:4] == b'PK\x03\x04'
    except OSError:
        return False

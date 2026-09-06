"""Inspect current official distributions and build an isolated real-data artifact.

No source records are committed to Git. No user/session/document originals are
included in the public catalog artifact. Failure is reported, never substituted
with test data. This operator job is bounded and does not run on web requests.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import httpx
from sqlalchemy import func, select
from bdt.domain import now
from bdt.ingest import IBGE_URL, csv_records, file_source, import_ibge, import_places
from bdt.storage import Database, Place
from bdt.sync import download_retry

ROOT = Path('test-results/official-data')
ROOT.mkdir(parents=True, exist_ok=True)
REPORT = {'started_at': now(), 'national_catalog_certified': False, 'sources': [], 'application_deployed': False}
HEADERS = {'User-Agent': 'BrasilDeTodos/0.2 (+https://github.com/rafaelob/brasildetodos)'}
DOC_HOSTS = {'www.gov.br', 'apidadosabertos.saude.gov.br', 'dadosabertos.saude.gov.br', 'download.inep.gov.br', 'arquivosdadosabertos.saude.gov.br'}


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            value = dict(attrs).get('href')
            if value:
                self.hrefs.append(value)


def text(url):
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in DOC_HOSTS or parsed.username or parsed.password:
            raise ValueError('unreviewed_documentation_host')
        with httpx.Client(timeout=httpx.Timeout(45, connect=15), follow_redirects=False, trust_env=False) as client:
            response = client.get(url, headers=HEADERS)
        if response.is_redirect:
            url = urljoin(url, response.headers['location']); continue
        response.raise_for_status()
        if len(response.content) > 8*1024*1024:
            raise ValueError('documentation_byte_budget')
        return response.text
    raise ValueError('documentation_redirect_budget')


def log(entry):
    REPORT['sources'].append(entry)
    Path(ROOT/'report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def main():
    database = Database('sqlite:///' + str(ROOT/'catalog.db'))
    database.initialize()
    municipalities_ready = False
    try:
        path = ROOT/'municipalities.json'
        meta = download_retry(IBGE_URL, path, 16*1024*1024)
        total = import_ibge(database, path, file_source(path, 'ibge', IBGE_URL, None))
        municipalities_ready = True
        log({'dataset': 'ibge', 'status': 'imported', 'records': total, 'bytes': meta['bytes'], 'sha256': meta['sha256']})
    except Exception as error:
        log({'dataset': 'ibge', 'status': 'failed', 'error': type(error).__name__})
    try:
        url = 'https://apidadosabertos.saude.gov.br/v1/'
        html = text(url)
        # Only inspect schema URLs explicitly referenced by the official Swagger UI.
        matches = re.findall(r'(?:url|configUrl)\s*:\s*[\"\x27]([^\"\x27]+)', html)
        schemas = []
        for relative in matches[:3]:
            schema_url = urljoin(url, relative)
            schema = json.loads(text(schema_url))
            paths = {k:v for k,v in schema.get('paths', {}).items() if 'cnes' in k.lower() and 'estabelecimento' in k.lower()}
            schemas.append({'url': schema_url, 'paths': paths})
        log({'dataset': 'cnes-api-documentation', 'status': 'inspected', 'schemas': schemas,
             'referenced_schema_urls': [urljoin(url,x) for x in matches[:3]]})
    except Exception as error:
        log({'dataset': 'cnes-api-documentation', 'status': 'failed', 'error': type(error).__name__})
    try:
        url = 'https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude'
        html = text(url); parser = Links(); parser.feed(html)
        refs = sorted(set(urljoin(url, h) for h in parser.hrefs if '/resource/' in h or any(s in h.lower() for s in ('.csv','.zip','.json','.xml'))))
        resources = []
        for resource_url in refs[:8]:
            if '/resource/' in resource_url and urlsplit(resource_url).hostname == 'dadosabertos.saude.gov.br':
                page = text(resource_url); links = Links(); links.feed(page)
                resources.extend(urljoin(resource_url,h) for h in links.hrefs if any(s in h.lower() for s in ('.csv','.zip','.json','.xml')))
        log({'dataset': 'cnes-distributions', 'status': 'inspected', 'references': refs, 'download_links': sorted(set(resources))})
    except Exception as error:
        log({'dataset': 'cnes-distributions', 'status': 'failed', 'error': type(error).__name__})
    try:
        url = 'https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar'
        html = text(url); links = Links(); links.feed(html)
        candidates = sorted(set(urljoin(url,h) for h in links.hrefs if '2025' in h and urlsplit(urljoin(url,h)).hostname == 'download.inep.gov.br' and urlsplit(h).path.lower().endswith('.zip')))
        if len(candidates) != 1:
            log({'dataset': 'inep-2025', 'status': 'distribution_review_required', 'candidates': candidates}); return
        distribution = candidates[0]
        archive_path = ROOT/'inep-2025.zip'
        meta = download_retry(distribution, archive_path, 768*1024*1024)
        selected, headers = [], []
        required = {'CO_ENTIDADE','NO_ENTIDADE','CO_MUNICIPIO','TP_DEPENDENCIA','TP_SITUACAO_FUNCIONAMENTO'}
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = info.filename.lower()
                if not name.endswith('.csv') or not any(word in name for word in ('escola','ed_basica')) or any(word in name for word in ('dicionario','auxiliar')):
                    continue
                if info.file_size > 4*1024**3 or info.file_size/max(info.compress_size,1) > 500:
                    raise ValueError('archive_member_budget')
                with archive.open(info) as stream:
                    first = stream.readline(256*1024)
                try:
                    line = first.decode('utf-8-sig'); encoding = 'utf-8-sig'
                except UnicodeDecodeError:
                    line = first.decode('cp1252'); encoding = 'cp1252'
                fields = next(csv.reader([line], delimiter=';'))
                headers.append({'member': info.filename, 'bytes': info.file_size, 'fields': fields, 'encoding': encoding})
                if required.issubset(fields):
                    selected.append((info.filename, encoding))
        log({'dataset': 'inep-2025-schema', 'status': 'inspected', 'url': distribution, 'bytes': meta['bytes'],
             'sha256': meta['sha256'], 'candidate_members': headers})
        if len(selected) != 1 or not municipalities_ready:
            log({'dataset':'inep-2025', 'status':'profile_review_or_municipality_load_required', 'matching_members':len(selected)})
            return
        member, encoding = selected[0]
        source = file_source(archive_path, 'inep-2025', distribution, '2025')
        result = import_places(database, csv_records(archive_path, member, encoding), source, 'inep')
        with database.session() as session:
            partitions = session.execute(select(Place.state, func.count(), func.count(Place.latitude))
                .where(Place.dataset == 'inep-2025', Place.catalogue_eligible.is_(True)).group_by(Place.state)).all()
        log({'dataset': 'inep-2025', 'status': 'imported', 'result': result,
             'partitions': [{'state': state,'records': count,'geocoded':geo} for state,count,geo in partitions],
             'scope': 'selected_official_school_table_public_active_profile', 'national_catalog_certified': False})
    except Exception as error:
        log({'dataset':'inep-2025', 'status':'failed', 'error':type(error).__name__,
             'reason':str(error)[:300] if isinstance(error,ValueError) else 'transport_or_processing_failure'})
    finally:
        with database.engine.connect() as conn:
            conn.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        database.engine.dispose()
        REPORT['finished_at'] = now()
        (ROOT/'report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        # Distribution originals remain in the runner; the artifact only includes
        # the minimal application database and source/coverage report.
        (ROOT/'inep-2025.zip').unlink(missing_ok=True)
    if not any(x.get('dataset') == 'inep-2025' and x.get('status') == 'imported' for x in REPORT['sources']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

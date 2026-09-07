# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inspect the publisher's current CSV index and schemas without collecting people.

Read-only, bounded requests to reviewed official endpoints. Never execute remote
JavaScript, use an inferred data endpoint or disable certificate validation.
"""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit
from bdt.domain import now
from bdt.sync import atomic_json, download_retry

BASE = 'https://api-publica.transferegov.gestao.gov.br'
INDEX = BASE + '/downloads'
SCHEMAS = {'parcerias': BASE + '/parcerias/openapi.json',
           'fundoafundo': BASE + '/fundoafundo/openapi.json'}
MAX_BODY = 8 * 1024 * 1024


class References(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts=[]; self.links=[]; self.inline=[]; self.inside=False
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='script':
            self.inside=True
            if values.get('src'): self.scripts.append(values['src'])
        if tag=='a' and values.get('href'):self.links.append(values['href'])
    def handle_endtag(self,tag):
        if tag=='script':self.inside=False
    def handle_data(self,data):
        if self.inside:self.inline.append(data)


def reviewed_reference(value, base=INDEX):
    if not isinstance(value,str) or len(value)>2048 or any(ord(x)<32 for x in value):
        raise ValueError('invalid_catalog_reference')
    resolved=urljoin(base,value); url=urlsplit(resolved)
    if (url.scheme!='https' or url.hostname!=urlsplit(BASE).hostname or url.port not in (None,443)
            or url.username or url.password or url.fragment or url.query):
        raise ValueError('unreviewed_catalog_reference')
    return resolved


def summarize_script(text):
    # Only static endpoint-like strings and immediate fetch context, not execution.
    strings=re.findall(r'''["']([^"'\n]{1,300})["']''',text)
    candidates=sorted(set(x for x in strings if x.startswith(('/', 'https://'))
                            and any(term in x.lower() for term in ('download','arquivo','csv','siconv','list'))))
    snippets=[]
    for found in re.finditer(r'\b(?:fetch|axios)\s*\(',text):
        snippets.append(text[max(0,found.start()-120):found.start()+280])
    return {'static_reference_candidates':candidates[:50], 'fetch_context':snippets[:8]}


def inspect_index(text):
    parser=References(); parser.feed(text)
    scripts=[]
    for value in parser.scripts:
        try:scripts.append(reviewed_reference(value))
        except ValueError:continue
    links=[]
    for value in parser.links:
        try:link=reviewed_reference(value)
        except ValueError:continue
        if any(x in link.lower() for x in ('csv','zip','download')):links.append(link)
    return {'script_urls':sorted(set(scripts))[:4], 'download_links':sorted(set(links))[:100],
            'inline_summary':summarize_script('\n'.join(parser.inline))}


def inspect_schema(document):
    if not isinstance(document,dict) or not document.get('openapi') or not isinstance(document.get('paths'),dict):
        raise ValueError('official_schema_missing')
    paths={}
    for path, operations in document['paths'].items():
        if not isinstance(operations,dict):raise ValueError('invalid_schema_operation')
        if 'get' in operations:
            get=operations['get']
            paths[path]={k:get[k] for k in ('summary','parameters','responses') if k in get}
    # Definitions describe public fields, not data records; preserve them for review.
    return {'openapi':document['openapi'], 'paths':paths,
            'schemas':document.get('components',{}).get('schemas',{})}


def run(output:Path, *, loader=download_retry):
    output=Path(output)
    if output.exists() or output.is_symlink():raise FileExistsError('probe_output_exists')
    output.mkdir(parents=True)
    report={'schema':'bdt.transferegov-discovery.v1','started_at':now(),'sources':[],
            'records_imported':0,'automatic_endpoint_execution':False,'public_deployment':False}
    with tempfile.TemporaryDirectory(prefix='bdt-official-index-') as folder:
        root=Path(folder)
        try:
            target=root/'index.html'; receipt=loader(INDEX,target,MAX_BODY)
            index=inspect_index(target.read_text(encoding='utf-8-sig'))
            scripts=[]
            for i,url in enumerate(index['script_urls']):
                path=root/f'script-{i}.txt'
                try:
                    meta=loader(url,path,2*1024*1024)
                    scripts.append({'receipt':meta,**summarize_script(path.read_text(encoding='utf-8-sig'))})
                except Exception as error:scripts.append({'url':url,'error_type':type(error).__name__})
            report['sources'].append({'source':'discretionary_csv_index','status':'inspected',
                                       'receipt':receipt,'index':index,'scripts':scripts})
        except Exception as error:
            report['sources'].append({'source':'discretionary_csv_index','status':'failed','error_type':type(error).__name__})
        for key,url in SCHEMAS.items():
            try:
                target=root/(key+'.json');receipt=loader(url,target,MAX_BODY)
                parsed=inspect_schema(json.loads(target.read_text(encoding='utf-8-sig')))
                atomic_json(output/(key+'-schema.json'),parsed)
                report['sources'].append({'source':key,'status':'schema_received','receipt':receipt,'get_paths':len(parsed['paths'])})
            except Exception as error:report['sources'].append({'source':key,'status':'failed','error_type':type(error).__name__})
    report['finished_at']=now()
    atomic_json(output/'report.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('test-results/transferegov-discovery'))
    args=parser.parse_args(argv); result=run(args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if any(x['status']=='failed' for x in result['sources']):raise SystemExit(1)


if __name__=='__main__': main()

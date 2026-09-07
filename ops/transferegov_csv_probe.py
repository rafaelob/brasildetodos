# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the publisher-referenced CSV inventory and inspect selected public fields.

The index URL was found in the official /downloads page by the prior discovery
run. No raw tables, identities of natural persons or bank fields are exported.
"""
from __future__ import annotations
import argparse
import csv
from io import TextIOWrapper
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile
from bdt.domain import now
from bdt.sync import atomic_json, download_retry

BASE='https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/'
INDEX=BASE+'?restype=container&comp=list'
FILES=('siconv_convenio.zip','siconv_termo_aditivo.zip','siconv_desembolso.zip')
SAFE_FIELDS=frozenset(('NR_CONVENIO','ID_PROPOSTA','ID_DESEMBOLSO','ID_TERMO_ADITIVO',
 'DIA_ASSIN_CONV','DIA_PUBL_CONV','DIA_INIC_VIGENC_CONV','DIA_FIM_VIGENC_CONV','SIT_CONVENIO',
 'IND_ASSINADO','INSTRUMENTO_ATIVO','VL_GLOBAL_CONV','VL_REPASSE_CONV','VL_CONTRAPARTIDA_CONV',
 'VL_EMPENHADO_CONV','VL_DESEMBOLSADO_CONV','DATA_DESEMBOLSO','VL_DESEMBOLSADO',
 'DATA_ASSINATURA_TA','VL_GLOBAL_TA','VL_REPASSE_TA','VL_CONTRAPARTIDA_TA','DIAS_PRORROGACAO_TA',
 'NUMERO_TA','TIPO_TA','DATA_FIM_VIGENCIA_TA'))


def parse_index(raw):
    if len(raw)>4*1024*1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('unsafe_or_oversized_csv_index')
    doc=ET.fromstring(raw)
    if doc.tag.split('}')[-1]!='EnumerationResults':raise ValueError('unexpected_csv_index')
    result={}
    for blob in doc.findall('.//{*}Blob'):
        name=blob.findtext('{*}Name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name):continue
        if name in result:raise ValueError('duplicate_csv_index_entry')
        size=blob.findtext('{*}Properties/{*}Content-Length')
        if size is None or not size.isdigit():raise ValueError('invalid_csv_index_size')
        result[name]={'name':name,'bytes':int(size),'last_modified':blob.findtext('{*}Properties/{*}Last-Modified'),
                      'url':BASE+quote(name,safe='')}
    return result, bool(doc.findtext('{*}NextMarker'))


def inspect_zip(path,name):
    expected=name.removesuffix('.zip')
    if not expected.endswith('.csv'): expected += '.csv'
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)!=1 or entries[0].filename!=expected or entries[0].file_size>1024*1024*1024:
            raise ValueError('unexpected_csv_archive_members')
        if entries[0].flag_bits & 1:raise ValueError('encrypted_csv_archive')
        for encoding in ('utf-8-sig','cp1252'):
            try:
                with archive.open(entries[0]) as stream:
                    with TextIOWrapper(stream,encoding=encoding,errors='strict',newline='') as text:
                        reader=csv.DictReader(text,delimiter=';')
                        fields=reader.fieldnames or []
                        if not fields or len(fields)>200 or len(fields)!=len(set(fields)):
                            raise ValueError('invalid_csv_header')
                        sample=[]
                        for _,row in zip(range(3),reader):
                            if None in row:raise ValueError('csv_shape_changed')
                            sample.append({key:value for key,value in row.items() if key in SAFE_FIELDS})
                return {'archive_member':expected,'uncompressed_bytes':entries[0].file_size,
                        'sample_encoding':encoding,'delimiter':';','fields':fields,
                        'selected_public_sample':sample,'sample_is_not_full_validation':True}
            except UnicodeDecodeError:
                if encoding=='cp1252':raise
    raise ValueError('unreadable_csv')


def run(output, *, loader=download_retry):
    output=Path(output)
    if output.exists():raise FileExistsError('csv_probe_output_exists')
    output.mkdir(parents=True)
    report={'schema':'bdt.transferegov-csv-discovery.v1','started_at':now(),'files':[],
            'records_imported':0,'raw_tables_published':False,'public_deployment':False}
    with tempfile.TemporaryDirectory(prefix='bdt-csv-review-') as temp:
        folder=Path(temp)
        target=folder/'index.xml';report['index_receipt']=loader(INDEX,target,4*1024*1024)
        index,more=parse_index(target.read_bytes())
        report['index_has_more_pages']=more
        report['index_names']=sorted(index)
        doc=ET.fromstring(target.read_bytes())
        report['publisher_blob_names']=[b.findtext('{*}Name') for b in doc.findall('.//{*}Blob')][:200]
        report['selected_entries']={key:index[key] for key in FILES if key in index}
        for name in FILES:
            try:
                entry=index.get(name)
                if entry is None:raise ValueError('selected_csv_not_in_publisher_index')
                if not 0<entry['bytes']<=96*1024*1024:raise ValueError('selected_csv_over_budget')
                path=folder/name;receipt=loader(entry['url'],path,96*1024*1024)
                if path.stat().st_size!=entry['bytes']:raise ValueError('csv_index_changed_during_download')
                report['files'].append({'name':name,'status':'inspected','receipt':receipt,**inspect_zip(path,name)})
            except Exception as error:
                report['files'].append({'name':name,'status':'failed','error_type':type(error).__name__,
                                       'reason':str(error) if type(error) is ValueError else 'transport_or_format_failure'})
            atomic_json(output/'report.json',report)
    report['finished_at']=now();atomic_json(output/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=Path('test-results/transferegov-csv-schema'))
    result=run(parser.parse_args().output);print(json.dumps(result,ensure_ascii=False,indent=2))
    if any(row['status']!='inspected' for row in result['files']):raise SystemExit(1)


if __name__=='__main__':main()

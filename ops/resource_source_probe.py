"""Bounded, read-only inspection of official resource schemas (no raw personal data)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from bdt.domain import now
from bdt.sync import atomic_json, download_retry

ROOT = Path('test-results/resource-sources')
SCHEMAS = {
    'pncp': 'https://pncp.gov.br/api/consulta/v3/api-docs',
    'transferegov_especiais': 'https://api-publica.transferegov.gestao.gov.br/especiais/openapi.json',
    'obrasgov': 'https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json',
}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    report = {'started_at': now(), 'sources': [], 'public_deployment': False}
    for name, url in SCHEMAS.items():
        path = ROOT / (name + '-openapi.json')
        try:
            meta = download_retry(url, path, 12 * 1024 * 1024)
            doc = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(doc.get('paths'), dict) or not doc.get('openapi'):
                raise ValueError('not_an_openapi_schema')
            summary = {'source': name, 'status': 'schema_received', 'metadata': meta,
                       'openapi': doc['openapi'], 'paths': {}}
            for route, operations in doc['paths'].items():
                operation = operations.get('get')
                if operation:
                    summary['paths'][route] = {'summary': operation.get('summary'),
                        'parameters': operation.get('parameters', []),
                        'responses': operation.get('responses', {})}
            report['sources'].append(summary)
        except Exception as error:
            path.unlink(missing_ok=True)
            report['sources'].append({'source': name, 'status': 'failed',
                'error_type': type(error).__name__,
                'reason': str(error) if isinstance(error, ValueError) else 'transport_or_schema_failure'})
        atomic_json(ROOT / 'report.json', report)
    # A single documented PNCP page, restricted in time and volume. Store only
    # an allowlisted metadata sample: do not publish raw suppliers/CPF or contacts.
    url = ('https://pncp.gov.br/api/consulta/v1/contratos?dataInicial=20260904'
           '&dataFinal=20260904&pagina=1&tamanhoPagina=10')
    path = ROOT / 'pncp-page-private.json'
    try:
        meta = download_retry(url, path, 8 * 1024 * 1024)
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
        rows = doc.get('data')
        if not isinstance(rows, list):
            raise ValueError('missing_data_array')
        fields = ['numeroControlePNCP', 'numeroControlePNCPCompra', 'numeroContratoEmpenho',
                  'anoContrato', 'sequencialContrato', 'objetoContrato', 'dataAssinatura',
                  'dataVigenciaInicio', 'dataVigenciaFim', 'dataPublicacaoPncp',
                  'dataAtualizacao', 'valorInicial', 'valorGlobal', 'valorAcumulado',
                  'numeroParcelas', 'informacaoComplementar']
        sanitized = []
        for row in rows[:3]:
            item = {key: row[key] for key in fields if key in row and key != 'informacaoComplementar'}
            item['unidadeOrgao'] = {key: row.get('unidadeOrgao', {}).get(key)
                for key in ('codigoUnidade', 'codigoIbge', 'municipioNome', 'ufSigla')}
            item['orgaoEntidade'] = {key: row.get('orgaoEntidade', {}).get(key)
                for key in ('cnpj', 'razaoSocial', 'esferaId', 'poderId')}
            item['source_field_names'] = sorted(row)
            sanitized.append(item)
        report['pncp_sample'] = {'status': 'received_not_imported', 'source': meta,
            'pagination': {k: v for k, v in doc.items() if k != 'data'},
            'rows_returned': len(rows), 'sanitized_examples': sanitized}
    except Exception as error:
        report['pncp_sample'] = {'status': 'failed', 'error_type': type(error).__name__}
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix('.json.manifest.json').unlink(missing_ok=True)
    report['finished_at'] = now()
    atomic_json(ROOT / 'report.json', report)
    print(json.dumps({'schema_status': [(x['source'], x['status']) for x in report['sources']],
                      'sample_status': report['pncp_sample']['status']}, indent=2))
    if not any(s['status'] == 'schema_received' for s in report['sources']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

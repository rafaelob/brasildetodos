"""Bounded official-source probe. Results are evidence, not national-service certification."""
import json
import tempfile
from pathlib import Path
from bdt.domain import now
from bdt.ingest import IBGE_URL, CNES_URL, safe_download, file_source, import_ibge, import_places, json_records
from bdt.storage import Database

report={'started_at':now(),'national_catalog_certified':False,'sources':[]}
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);database=Database(f"sqlite:///{root/'probe.db'}");database.initialize()
    for dataset,url in [('ibge',IBGE_URL),('cnes',CNES_URL)]:
        evidence={'dataset':dataset,'url':url,'scope':'municipality_endpoint' if dataset=='ibge' else 'default_response_sample_only'}
        try:
            path=root/(dataset+'.json');metadata=safe_download(url,path,max_bytes=32*1024*1024)
            source=file_source(path,dataset,url,None)
            if dataset=='ibge':evidence['municipalities']=import_ibge(database,path,source)
            else:evidence['import']=import_places(database,json_records(path,'estabelecimentos'),source,'cnes')
            evidence.update(status='success',bytes=metadata['bytes'],sha256=metadata['sha256'])
        except Exception as error:
            evidence.update(status='failed',error_type=type(error).__name__)
        report['sources'].append(evidence)
    database.engine.dispose()
report['finished_at']=now()
Path('source-probe.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
if any(row['status']!='success' for row in report['sources']):raise SystemExit(1)

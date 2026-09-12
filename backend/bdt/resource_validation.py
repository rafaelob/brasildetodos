"""Complete-query preflight with minimized bounded diagnostics and no DB writes."""
from collections import Counter
from pathlib import Path
from sqlalchemy import select
from .json_codec import decode
from .resource_diagnostics import public_validation
from .resource_sync import _reviewed_plan, verified_resources
from .storage import Municipality


def validate_collection(database, folder: Path, *, max_diagnostics: int = 20):
    if type(max_diagnostics) is not int or not 0 <= max_diagnostics <= 100:
        raise ValueError('invalid_diagnostic_limit')
    report=decode((folder/'collection.json').read_bytes())
    plan=_reviewed_plan(report)
    diagnostics=[];invalid=0;by_rule=Counter()
    with database.session() as session:
        territories={row.id:(row.name,row.state) for row in session.scalars(select(Municipality))}
    def rejected(error,profile,identity,page_hash):
        nonlocal invalid
        invalid+=1
        diagnostic=public_validation(error,profile,identity,page_hash)
        for issue in diagnostic.get('issues',[diagnostic]):
            by_rule[(issue.get('field','unspecified'),issue.get('rule','validation_failure'))]+=1
        if len(diagnostics)<max_diagnostics:diagnostics.append(diagnostic)
    accepted=sum(1 for _ in verified_resources(folder,report,plan,territories,on_invalid=rejected))
    return {'status':'valid' if not invalid else 'rejected','profile':plan.dataset,
        'read':accepted+invalid,'accepted':accepted,'invalid':invalid,'published':0,
        'validation_only':True,'diagnostics':diagnostics,'diagnostics_truncated':invalid>len(diagnostics),
        'issues':[{'field':field,'rule':rule,'count':count} for (field,rule),count in sorted(by_rule.items())]}

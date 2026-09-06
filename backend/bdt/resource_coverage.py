# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimized public status of this installation, not a government uptime probe.

Only import attempts present in the local ledger are covered. A download that
fails before creating an import record is outside this view. No query parameters,
error text, user data, local paths or raw source payload are publicized here.
"""
from datetime import datetime

from sqlalchemy import func, select

from .evidence import Resource
from .resource_profiles import PROFILES
from .storage import Ingestion

COUNTS = ('read', 'created', 'updated', 'unchanged', 'unresolved_municipality', 'published')


def _time(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _attempt(row):
    if row is None:
        return None
    counts = row.counts if isinstance(row.counts, dict) else {}
    return {'status': row.status if row.status in {'running', 'success', 'failed'} else 'unknown',
            'started_at': _time(row.started_at), 'finished_at': _time(row.finished_at),
            'counts': {key: counts[key] for key in COUNTS
                       if type(counts.get(key)) is int and 0 <= counts[key] <= 9_007_199_254_740_991},
            'rolled_back': counts.get('rolled_back') is True}


def resource_coverage(database):
    profiles = []
    with database.session() as session:
        for profile in PROFILES:
            count = session.scalar(select(func.count()).select_from(Resource)
                                   .where(Resource.source['dataset'].as_string() == profile))
            base = select(Ingestion).where(Ingestion.dataset == profile)
            last = session.scalar(base.order_by(Ingestion.started_at.desc(), Ingestion.id.desc()).limit(1))
            successful = session.scalar(base.where(Ingestion.status == 'success')
                                       .order_by(Ingestion.finished_at.desc(), Ingestion.id.desc()).limit(1))
            profiles.append({'profile': profile, 'loaded_records': count,
                             'availability': 'available' if count else 'not_loaded',
                             'last_attempt': _attempt(last),
                             'last_successful_import_at': _time(successful.finished_at) if successful else None})
    return {'scope': 'installation_import_history_not_upstream_service_monitor',
            'national_resources_certified': False, 'profiles': profiles}

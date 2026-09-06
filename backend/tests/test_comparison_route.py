"""The comparison uses the production read route and does not register a test router."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.api import create_app
from bdt.storage import Place, User, Observation, upsert_place


def test_comparison_route_is_unique_readonly_and_preserves_source_periods(database,place):
    with database.session() as s:
        upsert_place(s,place)
        upsert_place(s,place.model_copy(update={'id':'test:health','kind':'health','name':'Synthetic health',
            'source':place.source.model_copy(update={'reference_date':'2024'}),'catalogue_eligible':False}))
    app=create_app(str(database.engine.url),testing=True)
    assert sum(route.path=='/api/saved-places/summary' for route in app.routes if hasattr(route,'path'))==1
    with TestClient(app) as client:
        response=client.post('/api/saved-places/summary',headers={'X-BDT-Client':'web'},json={'place_ids':['test:health','missing:one',place.id],'versions_per_place':1})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        rows=response.json()['items']
        assert [x['id'] for x in rows]==['test:health','missing:one',place.id]
        assert rows[0]['status']=='outside_current_profile' and rows[0]['place']['source']['reference_date']=='2024'
        assert rows[1]['status']=='not_found' and rows[1]['place'] is None
        assert rows[2]['place']['latitude'] is None and rows[2]['place']['source']['reference_date']=='2025'
        assert response.json()['favorites_persisted'] is False
        assert client.post('/api/saved-places/summary',json={'place_ids':[place.id]}).status_code==403
        assert client.get('/api/workbench/documents').status_code==401
    with database.session() as s:
        assert s.scalar(select(func.count()).select_from(Place))==2
        assert s.scalar(select(func.count()).select_from(User))==0
        assert s.scalar(select(func.count()).select_from(Observation))==0

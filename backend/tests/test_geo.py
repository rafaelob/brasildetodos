import pytest
from bdt.geo import parse_bbox, viewport
from bdt.storage import upsert_place


@pytest.mark.parametrize('box', ['bad', '0,0,1', '0,0,1,2,3', 'nan,0,1,2', '0,0,inf,2', '1,0,0,2', '-181,0,1,2', '0,-91,1,2', '0,0,181,2', '0,0,1,91'])
def test_invalid_bounds(box):
    with pytest.raises(ValueError, match='invalid_bbox'):
        parse_bbox(box)


def test_empty_and_unmapped(database, stored):
    result = viewport(database, '-75,-35,-32,6')
    assert result['features'] == []
    assert result['matched_records'] == result['represented_records'] == 0


def seed(database, place, count=80):
    with database.session() as session:
        for index in range(count):
            item = place.model_copy(update={'id': f'test:point{index}', 'name': f'Escola Árvore {index}',
                'latitude': -22 + index * .04, 'longitude': -48 + index * .035, 'geo_source': 'synthetic_test'})
            upsert_place(session, item)
        upsert_place(session, place.model_copy(update={'id': 'test:hidden', 'catalogue_eligible': False,
            'latitude': -22, 'longitude': -48, 'geo_source': 'synthetic_test'}))


def test_raw_includes_more_than_one_list_page(database, place):
    seed(database, place)
    result = viewport(database, '-75,-35,-32,6')
    assert len(result['features']) == 80
    assert result['matched_records'] == result['represented_records'] == 80
    assert result['aggregated'] is False
    assert all(not feature['properties']['cluster'] for feature in result['features'])


@pytest.mark.parametrize('zoom,budget', [(0, 1), (4, 5), (12, 10), (20, 2)])
def test_aggregate_budget_never_silently_discards_points(database, place, zoom, budget):
    seed(database, place)
    result = viewport(database, '-75,-35,-32,6', zoom=zoom, max_features=budget)
    assert 1 <= len(result['features']) <= budget
    assert result['matched_records'] == result['represented_records'] == 80
    for feature in result['features']:
        if feature['properties']['cluster']:
            assert feature['properties']['location_kind'] == 'aggregate_not_facility'
            assert feature['properties']['id'].startswith('grid:')
        else:
            assert feature['properties']['count'] == 1
            assert feature['properties']['id'].startswith('test:point')


@pytest.mark.parametrize('filters,expected', [({'q': 'árvore'}, 80), ({'q': '%'}, 0), ({'kind': 'health'}, 0), ({'kind': 'school'}, 80), ({'state': 'BA'}, 80), ({'state': 'SP'}, 0), ({'municipality_id': '1234567'}, 80), ({'municipality_id': '7654321'}, 0)])
def test_filters_are_identical_for_map_and_list(database, place, filters, expected):
    seed(database, place)
    result = viewport(database, '-75,-35,-32,6', max_features=5, **filters)
    assert result['matched_records'] == result['represented_records'] == expected


@pytest.mark.parametrize('options', [{'zoom': -1}, {'zoom': 21}, {'max_features': 0}, {'max_features': 1001}])
def test_invalid_budget(database, options):
    with pytest.raises(ValueError, match='invalid_map_budget'):
        viewport(database, '-75,-35,-32,6', **options)


def test_single_point_aggregate_preserves_real_identity(database, place):
    seed(database, place, 3)
    result = viewport(database, '-75,-35,-32,6', zoom=20, max_features=2)
    assert result['represented_records'] == 3
    assert parse_bbox('-75,-35,-32,6') == (-75, -35, -32, 6)

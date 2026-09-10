# SPDX-License-Identifier: AGPL-3.0-or-later
"""An empty clone has no municipalities; the dashboard fixture must not stand in."""
from fastapi.testclient import TestClient
from bdt.api import create_app


def test_empty_clone_is_not_national_coverage(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'empty-clone.db'}", testing=True)) as client:
        coverage = client.get('/api/coverage').json()
    assert coverage['national_catalog_certified'] is False
    assert coverage['municipalities'] == 0
    assert coverage['summary']['places'] == 0
    if 'resources' in coverage['summary']:
        assert coverage['summary']['resources'] == 0

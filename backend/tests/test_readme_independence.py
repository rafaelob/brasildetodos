# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ('iajus', 'docia')


def assert_no_unrelated_product_names(path: Path) -> None:
    text = path.read_text(encoding='utf-8').lower()
    for token in TOKENS:
        assert token not in text, token


def test_readme_does_not_name_unrelated_products():
    assert_no_unrelated_product_names(ROOT / 'README.md')


def test_sources_doc_does_not_name_unrelated_products():
    path = ROOT / 'docs/SOURCES.md'
    if not path.is_file():
        pytest.skip('docs/SOURCES.md is not present yet')
    assert_no_unrelated_product_names(path)

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operator MCP staging package. The public API must never import this module."""
from .staging import (
    cnes_rest_index_0,
    describe_tools,
    ibge_download_municipios,
    inep_describe_schema,
    inep_download_file,
    inep_search_dataset,
    obrasgov_fetch_page,
    pncp_fetch_page,
    tool_result,
    transferegov_fetch_page,
)

__all__ = (
    'cnes_rest_index_0',
    'describe_tools',
    'ibge_download_municipios',
    'inep_describe_schema',
    'inep_download_file',
    'inep_search_dataset',
    'obrasgov_fetch_page',
    'pncp_fetch_page',
    'tool_result',
    'transferegov_fetch_page',
)

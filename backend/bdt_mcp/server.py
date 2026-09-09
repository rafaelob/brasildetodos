# SPDX-License-Identifier: AGPL-3.0-or-later
"""STDIO MCP server for operator source probes. Optional extra; never imported by bdt.api."""
from __future__ import annotations

from .staging import (
    OPERATOR_INSTALL,
    cnes_rest_index_0,
    describe_tools,
    ibge_download_municipios,
    inep_describe_schema,
    inep_download_file,
    inep_search_dataset,
    obrasgov_fetch_page,
    pncp_fetch_page,
    transferegov_fetch_page,
)


def _load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(OPERATOR_INSTALL) from exc
    return FastMCP


def build_server():
    fastmcp = _load_fastmcp()
    server = fastmcp('brasildetodos-sources')
    for fn in (
        describe_tools,
        ibge_download_municipios,
        pncp_fetch_page,
        transferegov_fetch_page,
        obrasgov_fetch_page,
        cnes_rest_index_0,
        inep_search_dataset,
        inep_describe_schema,
        inep_download_file,
    ):
        server.add_tool(fn, description=fn.__doc__ or fn.__name__)
    return server


def main():
    build_server().run()

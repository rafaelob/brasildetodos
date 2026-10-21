# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional local PDF page rendering for reviewer-only visual inspection.

Requires Poppler's ``pdftoppm``. It never fetches, OCRs or publishes a page.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


MAX_PAGE_BYTES = 16 * 1024 * 1024
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def render_page(path: Path, page: int, *, dpi: int = 150, timeout: int = 30) -> bytes:
    if type(page) is not int or not 1 <= page <= 1000:
        raise ValueError("page_number_out_of_range")
    if type(dpi) is not int or not 72 <= dpi <= 300:
        raise ValueError("page_dpi_out_of_range")
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError("page_render_timeout_out_of_range")
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("document_original_not_regular")
    binary = shutil.which("pdftoppm")
    if not binary:
        raise ValueError("page_renderer_unavailable")
    with tempfile.TemporaryDirectory(prefix="bdt-page-") as folder:
        prefix = str(Path(folder) / "page")
        try:
            result = subprocess.run(
                [binary, "-f", str(page), "-l", str(page), "-singlefile",
                 "-r", str(dpi), "-png", str(path), prefix],
                capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise ValueError("page_render_timeout") from None
        output = Path(prefix + ".png")
        if result.returncode != 0 or not output.is_file() or output.is_symlink():
            raise ValueError("page_render_failed")
        if output.stat().st_size < len(PNG_HEADER) or output.stat().st_size > MAX_PAGE_BYTES:
            raise ValueError("page_render_size_invalid")
        content = output.read_bytes()
        if not content.startswith(PNG_HEADER):
            raise ValueError("page_render_not_png")
        return content

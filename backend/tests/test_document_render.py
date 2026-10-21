"""Optional local page rendering; no OCR, network or publication."""
import subprocess
from pathlib import Path

import pytest

from bdt import document_render


PNG = b"\x89PNG\r\n\x1a\nsynthetic"


def test_render_page_uses_local_pdftoppm(monkeypatch, tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(document_render.shutil, "which", lambda name: "/usr/bin/pdftoppm")

    def fake_run(args, **kwargs):
        prefix = Path(args[-1])
        prefix.with_suffix(".png").write_bytes(PNG)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(document_render.subprocess, "run", fake_run)
    assert document_render.render_page(source, 1) == PNG


def test_render_page_rejects_missing_renderer_and_bad_arguments(monkeypatch, tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(document_render.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="page_renderer_unavailable"):
        document_render.render_page(source, 1)
    for page in (0, 1001, True):
        with pytest.raises(ValueError, match="page_number_out_of_range"):
            document_render.render_page(source, page)
    with pytest.raises(ValueError, match="page_dpi_out_of_range"):
        document_render.render_page(source, 1, dpi=301)
    with pytest.raises(ValueError, match="page_render_timeout_out_of_range"):
        document_render.render_page(source, 1, timeout=0)


def test_render_page_does_not_accept_failed_or_non_png_output(monkeypatch, tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(document_render.shutil, "which", lambda name: "/usr/bin/pdftoppm")

    monkeypatch.setattr(document_render.subprocess, "run",
                        lambda args, **kwargs: subprocess.CompletedProcess(args, 1))
    with pytest.raises(ValueError, match="page_render_failed"):
        document_render.render_page(source, 1)

    def fake_png(args, **kwargs):
        Path(args[-1] + ".png").write_bytes(b"not png!")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(document_render.subprocess, "run", fake_png)
    with pytest.raises(ValueError, match="page_render_not_png"):
        document_render.render_page(source, 1)

    def fake_timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 1)

    monkeypatch.setattr(document_render.subprocess, "run", fake_timeout)
    with pytest.raises(ValueError, match="page_render_timeout"):
        document_render.render_page(source, 1)

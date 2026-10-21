# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small content-addressed store for operator-private files.

The store never serves bytes by itself and never invents metadata. Callers keep
their own database rows and pass a SHA-256 that was computed from the file.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from .sync import file_hash


def content_path(folder: Path, sha256: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("invalid_content_hash")
    return Path(folder) / "sha256" / sha256[:2] / sha256


def _check_folder(folder: Path) -> Path:
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("private_store_cannot_be_a_symlink")
    hash_root = folder / "sha256"
    if hash_root.is_symlink():
        raise ValueError("private_store_cannot_be_a_symlink")
    return folder


def store_file(source: Path, folder: Path, sha256: str) -> Path:
    """Move one regular file into the store, verifying an existing address."""
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError("private_store_source_not_regular")
    folder = _check_folder(folder)
    target = content_path(folder, sha256)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("private_store_cannot_be_a_symlink")
    if target.exists():
        if target.is_symlink() or not target.is_file() or file_hash(target) != sha256:
            raise ValueError("content_address_collision")
        source.unlink()
        return target
    os.replace(source, target)
    if file_hash(target) != sha256:
        target.unlink(missing_ok=True)
        raise ValueError("private_store_hash_mismatch")
    return target


def store_copy(source: Path, folder: Path, sha256: str) -> Path:
    """Copy one regular file into the store, leaving the source untouched."""
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError("private_store_source_not_regular")
    folder = _check_folder(folder)
    target = content_path(folder, sha256)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("private_store_cannot_be_a_symlink")
    if target.exists():
        if target.is_symlink() or not target.is_file() or file_hash(target) != sha256:
            raise ValueError("content_address_collision")
        return target
    temporary = target.with_name(target.name + ".part-" + str(uuid4()))
    try:
        shutil.copyfile(source, temporary)
        if file_hash(temporary) != sha256:
            raise ValueError("private_store_hash_mismatch")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def verified_path(folder: Path, sha256: str, byte_size: int | None = None) -> Path:
    folder = _check_folder(folder)
    target = content_path(folder, sha256)
    if target.is_symlink() or not target.is_file():
        raise ValueError("private_store_content_missing")
    if byte_size is not None and target.stat().st_size != byte_size:
        raise ValueError("private_store_size_mismatch")
    if file_hash(target) != sha256:
        raise ValueError("private_store_hash_mismatch")
    return target

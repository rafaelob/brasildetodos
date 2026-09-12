# SPDX-License-Identifier: AGPL-3.0-or-later
"""Archive a previously reviewed, synthetic OCR test; never a government corpus.

Input is one explicitly identified GitHub artifact, not arbitrary user uploads.
No network, OCR engine, production database or private document lookup is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

SOURCE = {
    'repository': 'rafaelob/brasildetodos', 'run_id': 34008123457,
    'artifact_id': 9981605829, 'artifact_name': 'portuguese-ocr-synthetic-evidence',
    'revision': 'c6724cf38019a1c1a4d0938a911cb56bea111392',
    'archive_sha256': '3c7bf8d708869e7c620b44cac150930b3be50759b0b814d040535d2d43b96857',
}
EXPECTED = {
    'SYNTHETIC-native.pdf': (1655, '0f7c3d77ffb7ee6d32b323ef141f8d8b9586ea76c9d8eb195d7bc2aa6f385074'),
    'SYNTHETIC-scanned.pdf': (59932, 'feb3c4ca92775e36d04b77204d84af23c5579d3807f63d44e714cde974a22a7a'),
    'SYNTHETIC-page.png': (62544, '52d42ffcab848e242f9dc9ea2bb35e804f939bbd2a79d108b123f1d01cd4700e'),
    'result.json': (915, 'df2a8f0fbb2d343a82ced6e3a96375fb1e783977c430be5e9cd5d94b8952c4fc'),
}
FIELDS = {'agreement_reference': '977950/2025', 'proposal_reference': '036806/2025',
          'estimated_cents': 364261056, 'planned_capacity': 170}
GENERATED = {'manifest.json', 'native-extraction.json', 'recognized-text.txt'}
MAX_FILE_BYTES = 2 * 1024 * 1024


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def read_regular(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError('corpus_symlink_not_allowed')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ValueError('corpus_file_budget_or_type')
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError('corpus_file_budget_or_type')
    return content


def originals(folder: Path, *, archived=False) -> dict[str, bytes]:
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('corpus_folder_invalid')
    names = {p.name for p in folder.iterdir()}
    if names != set(EXPECTED) | (GENERATED if archived else set()):
        raise ValueError('corpus_unreviewed_or_missing_files')
    content = {}
    for name, (size, sha) in EXPECTED.items():
        value = read_regular(folder / name)
        if len(value) != size or hashlib.sha256(value).hexdigest() != sha:
            raise ValueError('corpus_reviewed_bytes_mismatch')
        content[name] = value
    return content


def derive(folder: Path, content: dict[str, bytes]) -> dict[str, bytes]:
    from bdt.documents import candidates, inspect_pdf
    from bdt.json_codec import decode
    evidence = decode(content['result.json'])
    if (evidence.get('fixture') != 'synthetic-scanned-Portuguese' or
            evidence.get('official_corpus_evaluated') is not False or
            evidence.get('revision') != SOURCE['revision'] or
            evidence.get('expected_fields') != FIELDS or
            evidence.get('result', {}).get('original_sha256') != EXPECTED['SYNTHETIC-scanned.pdf'][1] or
            evidence['result'].get('original_preserved') is not True or
            evidence['result'].get('public') is not False):
        raise ValueError('corpus_evidence_mismatch')
    text = evidence.get('recognized_test_text')
    if not isinstance(text, str) or 'DOCUMENTO SINTETICO PARA TESTE' not in text:
        raise ValueError('corpus_test_label_missing')
    # Parse the already verified bytes, not a path another process could replace.
    with tempfile.TemporaryDirectory(prefix='bdt-pinned-pdf-') as tmp:
        checked = Path(tmp)
        for name in ('SYNTHETIC-native.pdf', 'SYNTHETIC-scanned.pdf'):
            (checked / name).write_bytes(content[name])
        native = inspect_pdf(checked / 'SYNTHETIC-native.pdf', max_pages=1)
        scanned = inspect_pdf(checked / 'SYNTHETIC-scanned.pdf', max_pages=1)
    if len(native['pages']) != 1 or native['pages'][0]['route'] != 'native':
        raise ValueError('corpus_native_route_mismatch')
    if len(scanned['pages']) != 1 or scanned['pages'][0]['route'] != 'ocr_candidate':
        raise ValueError('corpus_scanned_route_mismatch')
    for value in (text, native['pages'][0]['text']):
        extracted = candidates(value)
        if {row['field']: row['value'] for row in extracted} != FIELDS:
            raise ValueError('corpus_candidate_regression')
        if any(row['state'] != 'candidate' or row['publication_allowed'] for row in extracted):
            raise ValueError('corpus_candidate_publication_forbidden')
    return {'native-extraction.json': encoded(native), 'recognized-text.txt': text.encode('utf-8')}


def manifest(files: dict[str, bytes]) -> dict:
    return {'schema': 'bdt.reviewed-ocr-corpus.v1', 'classification': 'synthetic-test-only',
        'license': 'CC-BY-4.0', 'source': SOURCE,
        'official_document': False, 'production_import_allowed': False,
        'ocr_reexecuted_by_archive': False, 'original_bytes_preserved': True,
        'privacy_review': 'Synthetic text only; no people, signatures or attachments; visually inspected.',
        'expected_candidate_fields': FIELDS,
        'files': [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'role': 'original-artifact-file' if name in EXPECTED else 'derived-test-evidence'}
                  for name, data in sorted(files.items())]}


def verify(folder: Path) -> dict:
    from bdt.json_codec import decode
    content = originals(folder, archived=True)
    recorded = decode(read_regular(folder / 'manifest.json'))
    derived = {name: read_regular(folder / name) for name in ('native-extraction.json', 'recognized-text.txt')}
    if recorded != manifest(content | derived):
        raise ValueError('corpus_manifest_mismatch')
    current = derive(folder, content)
    if current != derived:
        raise ValueError('corpus_extraction_regression')
    return {'status': 'passed', 'files': len(content) + len(derived), 'originals': len(content),
            'official_corpus': False, 'original_bytes_preserved': True, 'ocr_executed': False}


def archive(source: Path, target: Path) -> dict:
    content = originals(source)
    files = content | derive(source, content)
    expected_manifest = encoded(manifest(files))
    if target.exists() or target.is_symlink():
        result = verify(target)
        if read_regular(target / 'manifest.json') != expected_manifest:
            raise ValueError('corpus_destination_conflict')
        return result | {'already_present': True}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reviewed-ocr-', dir=target.parent) as tmp:
        stage = Path(tmp) / 'corpus'; stage.mkdir()
        for name, data in files.items():
            with (stage / name).open('xb') as stream:
                stream.write(data)
        (stage / 'manifest.json').write_bytes(expected_manifest)
        result = verify(stage)
        if target.exists() or target.is_symlink():
            raise ValueError('corpus_destination_exists')
        stage.rename(target)
    return result | {'already_present': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('archive', 'verify'))
    parser.add_argument('folder', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args(argv)
    if args.operation == 'archive' and args.destination is None:
        parser.error('--destination is required for archive')
    result = archive(args.folder, args.destination) if args.operation == 'archive' else verify(args.folder)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only inventory of project checklists; never certify feature completion.

Only TODO.md, README.md and Markdown files below docs/ are read. Code fences are
excluded. Historical documents remain separate. Identical task text with opposing
checkboxes in active documents is reported for human review, never auto-resolved.
The output contains repository-relative paths and hashes, not local absolute paths.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
TASK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[([ xX])\]\s+(.+?)\s*$")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
IDENTIFIER = re.compile(r"^(?:\*\*)?([A-Z]{1,5}[0-9]{1,4}(?:[.-][0-9]+)*)\b")
HISTORY_COMPONENTS = frozenset({'history', 'archive', 'archives', 'historico'})


def normalized_text(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def parse_tasks(text: str, relative_path: str) -> list[dict]:
    """Extract checkbox occurrences, preserving wording, location and headings."""
    result = []
    headings: dict[int, str] = {}
    fence_character = None
    fence_length = 0
    historical = any(part.casefold() in HISTORY_COMPONENTS
                     for part in Path(relative_path).parts[:-1])
    for line_number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if fence_character is not None:
            if (match and match[1][0] == fence_character
                    and len(match[1]) >= fence_length and not match[2].strip()):
                fence_character = None
            continue
        if match:
            # Backticks in an opening info string make that opening invalid.
            if match[1][0] == '`' and '`' in match[2]:
                continue
            fence_character, fence_length = match[1][0], len(match[1])
            continue
        heading = HEADING.match(line)
        if heading:
            level = len(heading[1])
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = heading[2]
            continue
        task = TASK.match(line)
        if task is None:
            continue
        wording = task[2]
        identifier = IDENTIFIER.match(wording)
        result.append({
            'path': relative_path,
            'line': line_number,
            'checked': task[1].casefold() == 'x',
            'scope': 'historical' if historical else 'active',
            'identifier': identifier[1] if identifier else None,
            'headings': [headings[k] for k in sorted(headings)],
            'text': wording,
        })
    return result


def _documents(root: Path) -> list[Path]:
    selected = [root / name for name in ('README.md', 'TODO.md')
                if (root / name).is_file() or (root / name).is_symlink()]
    docs = root / 'docs'
    if docs.is_symlink():
        raise ValueError('plan_directory_symlink')
    if docs.is_dir():
        for directory, names, files in os.walk(docs, followlinks=False):
            # Never traverse repository links into unrelated files.
            names[:] = sorted(name for name in names
                              if not (Path(directory) / name).is_symlink())
            selected.extend(Path(directory) / name for name in sorted(files)
                            if name.lower().endswith('.md'))
    return sorted(selected, key=lambda path: path.relative_to(root).as_posix())


def _read_document(path: Path, root: Path) -> bytes:
    if path.is_symlink():
        raise ValueError('plan_document_symlink')
    if not path.resolve().is_relative_to(root):
        raise ValueError('plan_document_outside_root')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError('plan_document_not_regular')
        if metadata.st_size > MAX_DOCUMENT_BYTES:
            raise ValueError('plan_document_too_large')
        content = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError('plan_document_too_large')
    return content


def inventory(root: Path) -> dict:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('plan_root_not_directory')
    documents, tasks = [], []
    for path in _documents(root):
        relative = path.relative_to(root).as_posix()
        content = _read_document(path, root)
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('plan_document_invalid_utf8') from exc
        extracted = parse_tasks(text, relative)
        tasks.extend(extracted)
        documents.append({'path': relative, 'bytes': len(content),
                          'sha256': hashlib.sha256(content).hexdigest(),
                          'checkbox_occurrences': len(extracted)})
    groups = defaultdict(list)
    identifiers = defaultdict(list)
    for task in tasks:
        if task['scope'] == 'active':
            groups[normalized_text(task['text'])].append(task)
            if task['identifier']:
                identifiers[task['identifier']].append(task)
    def reference(task):
        return {key: task[key] for key in ('path', 'line', 'checked')}
    conflicts = [
        {'text': occurrences[0]['text'],
         'occurrences': [reference(task) for task in occurrences]}
        for _, occurrences in sorted(groups.items())
        if len({task['checked'] for task in occurrences}) > 1
    ]
    reused = [
        {'identifier': identifier,
         'occurrences': [reference(task) | {'text': task['text']} for task in occurrences]}
        for identifier, occurrences in sorted(identifiers.items())
        if len({normalized_text(task['text']) for task in occurrences}) > 1
    ]
    counts = Counter((task['scope'], task['checked']) for task in tasks)
    return {
        'schema': 'bdt.plan-inventory.v1',
        'scope': 'repository_markdown_only',
        'documents': documents,
        'summary': {
            'documents_scanned': len(documents),
            'checkbox_occurrences': len(tasks),
            'active_checked': counts['active', True],
            'active_unchecked': counts['active', False],
            'historical_checked': counts['historical', True],
            'historical_unchecked': counts['historical', False],
            'opposing_active_checkboxes': len(conflicts),
            'reused_identifiers_with_different_text': len(reused),
        },
        'tasks': tasks,
        'opposing_active_checkboxes': conflicts,
        'reused_identifiers': reused,
        'limitations': [
            'Checkboxes record document assertions, not verified implementation.',
            'Repeated wording or identifiers do not establish identical feature scope.',
            'History classification uses directory names only.',
            'GitHub issues, releases, CI and deployment are not queried by this offline command.',
            'No total-feature count or completion percentage is inferred.',
        ],
        'feature_completion_certified': False,
        'repository_modified': False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path,
                        help='Create a new JSON report; an existing path is never overwritten.')
    args = parser.parse_args(argv)
    try:
        result = inventory(args.root)
        payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output is None:
            print(payload, end='')
        else:
            # Exclusive creation also rejects dangling links and concurrent writers.
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(payload)
    except (OSError, ValueError) as exc:
        # Do not expose local paths or document text in machine-readable errors.
        code = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(json.dumps({'status': 'failed', 'error': code}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

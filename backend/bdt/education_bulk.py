"""Bounded, repeatable INEP school-table ingestion without individual microdata.

Discover archives by their headers, never parse student/teacher tables or infer
new field semantics. Validate the complete input before the transactional import.
Nationwide partition presence is reported separately from population completeness.
"""
from __future__ import annotations

import codecs
import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator
from urllib.parse import urljoin, urlsplit
from html.parser import HTMLParser

from .domain import Source
from .ingest import import_places, inep_record, municipality_lookup
from .sync import file_hash

ANCHOR = 'https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar'
STATES = frozenset('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
REQUIRED = frozenset({'CO_ENTIDADE', 'NO_ENTIDADE', 'CO_MUNICIPIO', 'TP_DEPENDENCIA', 'TP_SITUACAO_FUNCIONAMENTO'})
INDIVIDUAL = re.compile(r'(aluno|matricula|docente|professor|turma)', re.I)


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 1024 ** 3
    member_bytes: int = 4 * 1024 ** 3
    total_school_bytes: int = 8 * 1024 ** 3
    compression_ratio: int = 500
    members: int = 10000
    rows: int = 2_000_000
    header_bytes: int = 256 * 1024


@dataclass(frozen=True)
class SchoolTable:
    member: str
    encoding: str
    columns: tuple[str, ...]
    bytes: int
    sha256: str
    delimiter: str = ';'


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and dict(attrs).get('href'):
            self.links.append(dict(attrs)['href'])


def discover_distribution(html: str, year: int) -> str:
    """Accept one exact-year HTTPS ZIP link from the reviewed official page."""
    if not 2000 <= year <= 2100 or len(html.encode('utf-8')) > 8 * 1024 ** 2:
        raise ValueError('invalid_year_or_anchor_budget')
    parser = _Links()
    parser.feed(html)
    candidates = set()
    for href in parser.links:
        url = urljoin(ANCHOR, href)
        parsed = urlsplit(url)
        if (parsed.scheme == 'https' and parsed.hostname == 'download.inep.gov.br'
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment and parsed.path.lower().endswith('.zip')
                and re.search(rf'(?<![0-9]){year}(?![0-9])', parsed.path)):
            candidates.add(url)
    if len(candidates) != 1:
        raise ValueError(f'official_distribution_requires_review:{len(candidates)}')
    return candidates.pop()


def _validate_member(info: zipfile.ZipInfo, limits: Limits) -> None:
    # Nothing is extracted to filesystem, but ambiguous and unsafe names are rejected.
    name = PurePosixPath(info.filename)
    if name.is_absolute() or '..' in name.parts or '\\' in info.filename or info.flag_bits & 1:
        raise ValueError('unsafe_or_encrypted_archive_member')
    if info.file_size > limits.member_bytes or info.file_size / max(info.compress_size, 1) > limits.compression_ratio:
        raise ValueError('school_archive_member_budget')


def _encoding(archive: zipfile.ZipFile, name: str) -> str:
    """Check ALL bytes; an ASCII header does not establish UTF-8 for the body."""
    for encoding in ('utf-8-sig', 'cp1252'):
        decoder = codecs.getincrementaldecoder(encoding)('strict')
        try:
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    decoder.decode(block)
                decoder.decode(b'', final=True)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError('school_encoding_requires_review')


def inspect_archive(path: Path, *, limits: Limits = Limits()) -> list[SchoolTable]:
    """Return only tables with the reviewed school schema, with member hashes."""
    import hashlib
    if not path.is_file() or path.stat().st_size > limits.archive_bytes:
        raise ValueError('school_archive_missing_or_budget')
    result: list[SchoolTable] = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits.members or len({x.filename for x in infos}) != len(infos):
            raise ValueError('school_archive_entries_invalid')
        total = 0
        for info in infos:
            if info.is_dir() or not info.filename.lower().endswith('.csv'):
                continue
            name = PurePosixPath(info.filename).name.lower()
            if INDIVIDUAL.search(name) or not ('escola' in name or 'ed_basica' in name):
                continue
            _validate_member(info, limits)
            total += info.file_size
            if total > limits.total_school_bytes:
                raise ValueError('school_total_uncompressed_budget')
            encoding = _encoding(archive, info.filename)
            with archive.open(info) as stream:
                header = stream.readline(limits.header_bytes + 1)
            if len(header) > limits.header_bytes:
                raise ValueError('school_header_budget')
            columns = tuple(next(csv.reader([header.decode(encoding).rstrip('\r\n')], delimiter=';', strict=True)))
            if not REQUIRED.issubset(columns):
                continue
            if len(set(columns)) != len(columns) or any(not x or x.strip() != x for x in columns):
                raise ValueError('school_duplicate_or_ambiguous_columns')
            sha = hashlib.sha256()
            with archive.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    sha.update(block)
            result.append(SchoolTable(info.filename, encoding, columns, info.file_size, sha.hexdigest()))
    if not result:
        raise ValueError('reviewed_school_schema_not_found')
    return sorted(result, key=lambda table: table.member)


def school_rows(path: Path, tables: Iterable[SchoolTable]) -> Iterator[dict[str, str]]:
    """Strict width, complete CSV parsing and CRC checks; no replacement characters."""
    with zipfile.ZipFile(path) as archive:
        for table in tables:
            with archive.open(table.member) as raw, io.TextIOWrapper(raw, encoding=table.encoding, newline='') as text:
                reader = csv.reader(text, delimiter=table.delimiter, strict=True)
                if tuple(next(reader)) != table.columns:
                    raise ValueError('school_header_changed')
                for values in reader:
                    if not values:  # Physical blank lines do not represent a school.
                        continue
                    if len(values) != len(table.columns):
                        raise ValueError(f'school_row_width:{reader.line_num}')
                    yield dict(zip(table.columns, values))


def validate_rows(rows: Iterable[dict], source: Source, lookup: dict, *, year: int,
                  required_states: frozenset[str] = STATES, max_rows: int = 2_000_000) -> dict:
    """Fail before publication; missing states never silently become zero coverage."""
    if not required_states or not required_states.issubset(STATES) or max_rows < 1:
        raise ValueError('invalid_school_validation_scope')
    seen: set[str] = set()
    counts: Counter = Counter()
    by_state: dict[str, Counter] = {state: Counter() for state in sorted(STATES)}
    for row_number, row in enumerate(rows, 1):
        if row_number > max_rows:
            raise ValueError('school_row_budget')
        if not REQUIRED.issubset(row) or any(not isinstance(row[k], str) for k in REQUIRED):
            raise ValueError(f'school_required_fields:{row_number}')
        identity, town = row['CO_ENTIDADE'].strip(), row['CO_MUNICIPIO'].strip()
        if not re.fullmatch(r'[0-9]{8}', identity) or identity in seen:
            raise ValueError(f'school_invalid_or_duplicate_identity:{row_number}')
        if not re.fullmatch(r'[0-9]{7}', town) or town not in lookup:
            raise ValueError(f'school_unknown_municipality:{row_number}')
        if row['TP_DEPENDENCIA'] not in {'1', '2', '3', '4'} or row['TP_SITUACAO_FUNCIONAMENTO'] not in {'1', '2', '3', '4'}:
            raise ValueError(f'school_eligibility_code_requires_review:{row_number}')
        if 'NU_ANO_CENSO' in row and row['NU_ANO_CENSO'] != str(year):
            raise ValueError(f'school_reference_year_mismatch:{row_number}')
        if identity != row['CO_ENTIDADE'] or town != row['CO_MUNICIPIO']:
            raise ValueError(f'school_identity_whitespace:{row_number}')
        state = lookup[town][1]
        if state not in STATES or (row.get('SG_UF') and row['SG_UF'] != state):
            raise ValueError(f'school_state_mismatch:{row_number}')
        seen.add(identity)
        counts['read'] += 1
        by_state[state]['read'] += 1
        if 'NU_ANO_CENSO' not in row:
            counts['reference_year_from_distribution_only'] += 1
        place = inep_record(row, source, lookup)
        status = 'excluded' if place is None else 'eligible'
        counts[status] += 1
        by_state[state][status] += 1
        if place:
            quality = 'without_geometry' if place.latitude is None else 'with_geometry'
            counts[quality] += 1
            by_state[state][quality] += 1
    if not counts['read']:
        raise ValueError('empty_school_table')
    missing = sorted(state for state in required_states if not by_state[state]['eligible'])
    report = {'counts': dict(counts), 'partitions': {key: dict(value) for key, value in by_state.items()},
              'required_states': sorted(required_states), 'missing_eligible_states': missing,
              'partition_check_passed': not missing, 'national_catalog_certified': False,
              'scope': 'reviewed_school_tables_public_active_declaration',
              'limit': 'State presence does not prove completeness or current enrolment availability.'}
    return report


def import_school_archive(database, path: Path, source: Source, *, year: int,
                          required_states: frozenset[str] = STATES, limits: Limits = Limits()) -> dict:
    """Two passes, hash checks and one transactional import; existing data preserved on failure."""
    if source.reference_date != str(year) or file_hash(path) != source.snapshot_sha256:
        raise ValueError('school_source_hash_or_year_mismatch')
    tables = inspect_archive(path, limits=limits)
    report = validate_rows(school_rows(path, tables), source, municipality_lookup(database), year=year,
                           required_states=required_states, max_rows=limits.rows)
    report['tables'] = [asdict(table) for table in tables]
    if report['missing_eligible_states']:
        report['status'] = 'partition_review_required'
        return report
    if file_hash(path) != source.snapshot_sha256:
        raise ValueError('school_archive_changed_during_preflight')
    report['import'] = import_places(database, school_rows(path, tables), source, 'inep')
    report['status'] = 'imported'
    return report

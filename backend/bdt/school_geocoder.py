# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geocode school places using official IBGE CNEFE 2022 census GPS coordinates.

Preserves strict data integrity:
- Official survey coordinates (LATITUDE, LONGITUDE) from IBGE Censo 2022.
- Matched strictly within the same official IBGE municipality (COD_MUNICIPIO).
- Records geo_source as 'IBGE-CNEFE-2022' and logs changes into the audit ledger.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .domain import PlaceInput, now
from .storage import Database, Place, upsert_place

logger = logging.getLogger('bdt.school_geocoder')

CNEFE_BASE = 'https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF'
USER_AGENT = 'BrasilDeTodos/0.3 (+https://github.com/rafaelob/brasildetodos)'

STATE_IBGE_CODES: dict[str, str] = {
    'RO': '11', 'AC': '12', 'AM': '13', 'RR': '14', 'PA': '15', 'AP': '16', 'TO': '17',
    'MA': '21', 'PI': '22', 'CE': '23', 'RN': '24', 'PB': '25', 'PE': '26', 'AL': '27', 'SE': '28', 'BA': '29',
    'MG': '31', 'ES': '32', 'RJ': '33', 'SP': '35',
    'PR': '41', 'SC': '42', 'RS': '43',
    'MS': '50', 'MT': '51', 'GO': '52', 'DF': '53'
}

STOP_WORDS = frozenset({
    'ESCOLA', 'ESTADUAL', 'MUNICIPAL', 'COLEGIO', 'CENTRO', 'EDUCACIONAL', 'ENSINO',
    'DE', 'DA', 'DO', 'DOS', 'DAS', 'E', 'EMEF', 'EEFM', 'CMEI', 'CRECHE', 'UNIDADE', 'INTEGRADA'
})


def normalize_school_name(name: str | None) -> str:
    """Clean and normalize school name for accurate lexical matching."""
    if not name:
        return ''
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.upper()
    # Collapse acronym dots: E.M.E.F. -> EMEF
    text = text.replace('.', '')
    text = re.sub(r'[^A-Z0-9\s]', ' ', text)
    words = text.split()
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return ' '.join(filtered)



def download_cnefe_state_zip(state: str, cache_dir: Path | None = None, timeout: int = 60) -> bytes:
    """Download CNEFE state zip archive from IBGE FTP mirror or read from local cache."""
    state_upper = state.upper()
    code = STATE_IBGE_CODES.get(state_upper)
    if not code:
        raise ValueError(f'unknown_state_code_{state_upper}')

    filename = f'{code}_{state_upper}.zip'
    if cache_dir:
        cache_path = cache_dir / filename
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            logger.info(f'Reading {filename} from cache: {cache_path}')
            return cache_path.read_bytes()

    url = f'{CNEFE_BASE}/{filename}'
    logger.info(f'Downloading CNEFE {filename} from {url}...')
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError(f'ibge_download_failed_{resp.status}')
        data = resp.read()

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / filename
        cache_path.write_bytes(data)

    return data


def parse_cnefe_schools(zip_bytes: bytes) -> dict[str, dict[str, tuple[float, float, str]]]:
    """Parse educational establishments (COD_ESPECIE=4) from CNEFE CSV.

    Returns dict mapping: municipality_id -> {normalized_name: (lat, lon, original_establishment_name)}
    Detects and discards ambiguous duplicate names with differing coordinates in the same municipality.
    """
    by_mun: dict[str, dict[str, tuple[float, float, str]]] = {}
    ambiguous: dict[str, set[str]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
        if not csv_names:
            return by_mun
        with zf.open(csv_names[0]) as stream:
            reader = csv.reader(io.TextIOWrapper(stream, encoding='utf-8', errors='replace'), delimiter=';')
            header = next(reader)
            col_map = {name: idx for idx, name in enumerate(header)}
            especie_idx = col_map.get('COD_ESPECIE')
            mun_idx = col_map.get('COD_MUNICIPIO')
            name_idx = col_map.get('DSC_ESTABELECIMENTO')
            lat_idx = col_map.get('LATITUDE')
            lon_idx = col_map.get('LONGITUDE')

            if any(idx is None for idx in (especie_idx, mun_idx, name_idx, lat_idx, lon_idx)):
                raise ValueError('cnefe_header_missing_expected_columns')

            for row in reader:
                if len(row) <= max(especie_idx, mun_idx, name_idx, lat_idx, lon_idx):
                    continue
                if row[especie_idx] == '4':  # Estabelecimento de ensino
                    mun = row[mun_idx].strip()
                    est_name = row[name_idx].strip()
                    lat_str = row[lat_idx].strip()
                    lon_str = row[lon_idx].strip()
                    if mun and est_name and lat_str and lon_str:
                        try:
                            lat = float(lat_str)
                            lon = float(lon_str)
                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                norm_k = normalize_school_name(est_name)
                                if norm_k:
                                    mun_ambig = ambiguous.setdefault(mun, set())
                                    if norm_k in mun_ambig:
                                        continue
                                    mun_dict = by_mun.setdefault(mun, {})
                                    if norm_k in mun_dict:
                                        prev_lat, prev_lon, _ = mun_dict[norm_k]
                                        if abs(prev_lat - lat) > 0.001 or abs(prev_lon - lon) > 0.001:
                                            del mun_dict[norm_k]
                                            mun_ambig.add(norm_k)
                                    else:
                                        mun_dict[norm_k] = (lat, lon, est_name)
                        except (ValueError, TypeError):
                            pass
    return by_mun


def find_cnefe_match(school_name: str, mun_cnefe: dict[str, tuple[float, float, str]]) -> tuple[float, float, str] | None:
    """Match a school against municipality CNEFE entries with high precision."""
    n_key = normalize_school_name(school_name)
    if not n_key:
        return None

    # 1. Exact match
    if n_key in mun_cnefe:
        return mun_cnefe[n_key]

    # 2. Token-based unambiguous match
    n_words = set(n_key.split())
    if len(n_words) >= 2 or (len(n_words) == 1 and len(n_key) >= 8):
        matches = []
        for c_key, val in mun_cnefe.items():
            c_words = set(c_key.split())
            if not c_words:
                continue
            if n_words.issubset(c_words) or c_words.issubset(n_words):
                matches.append(val)
                if len(matches) > 1:
                    break
        if len(matches) == 1:
            return matches[0]

    return None


def geocode_schools_for_state(database: Database, state: str,
                              cnefe_by_mun: dict[str, dict[str, tuple[float, float, str]]],
                              *, batch_size: int = 200) -> dict[str, int]:
    """Geocode all schools in a state using official CNEFE coordinates.

    Saves changes into the audit ledger and places table.
    """
    stats = Counter()

    with database.session() as session:
        query = (
            select(Place)
            .where(Place.kind == 'school', Place.state == state.upper())
        )
        places = session.scalars(query).all()
        stats['total_schools'] = len(places)

        pending_updates = []
        for place in places:
            # Skip if already has coordinates
            if place.latitude is not None and place.longitude is not None:
                stats['already_geocoded'] += 1
                continue

            mun_dict = cnefe_by_mun.get(place.municipality_id)
            if not mun_dict:
                stats['no_mun_cnefe'] = 1
                continue

            match = find_cnefe_match(place.name, mun_dict)
            if match:
                lat, lon, cnefe_name = match
                payload = dict(place.payload)
                payload['latitude'] = lat
                payload['longitude'] = lon
                payload['geo_source'] = 'IBGE-CNEFE-2022'

                try:
                    p_input = PlaceInput.model_validate(payload)
                    pending_updates.append(p_input)
                    stats['matched'] += 1
                except Exception as val_err:
                    stats['validation_error'] += 1
                    logger.debug(f'Validation error for {place.id}: {val_err}')
            else:
                stats['unmatched'] += 1

        # Apply updates in batches
        for i in range(0, len(pending_updates), batch_size):
            batch = pending_updates[i:i + batch_size]
            for p_in in batch:
                outcome = upsert_place(session, p_in)
                stats[f'outcome_{outcome}'] += 1
            session.commit()

    return dict(stats)

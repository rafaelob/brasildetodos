# SPDX-License-Identifier: AGPL-3.0-or-later
"""CNEFE 2022 name matches are unpublished coordinate candidates, not map pins.

Official survey coordinates stay on payload cnefe_candidate after an exact
normalized name match inside the same IBGE municipality. Place.latitude and
Place.longitude stay unset until an official identifier dictionary exists.
Ambiguous duplicate names are dropped at parse time. Downloads are cache-first;
ftp.ibge.gov.br is not in ingest.HOSTS.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from .storage import Database, Place

logger = logging.getLogger('bdt.school_geocoder')

CNEFE_BASE = 'https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF'
USER_AGENT = 'BrasilDeTodos/0.3 (+https://github.com/rafaelob/brasildetodos)'
OPERATOR_DOWNLOAD_ENV = 'BDT_CNEFE_OPERATOR_DOWNLOAD'

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


def _cnefe_cache_path(state: str, cache_dir: Path | None) -> tuple[str, Path | None]:
    state_upper = state.upper()
    code = STATE_IBGE_CODES.get(state_upper)
    if not code:
        raise ValueError(f'unknown_state_code_{state_upper}')
    filename = f'{code}_{state_upper}.zip'
    if cache_dir is None:
        return filename, None
    return filename, cache_dir / filename


def download_cnefe_state_zip(state: str, cache_dir: Path | None = None, timeout: int = 60) -> bytes:
    """Read a CNEFE state zip from local cache.

    ftp.ibge.gov.br is not in ingest.HOSTS. A cache miss raises unless
    BDT_CNEFE_OPERATOR_DOWNLOAD=1, which is an operator exception, not a HOSTS
    expansion to FTP.
    """
    filename, cache_path = _cnefe_cache_path(state, cache_dir)
    if cache_path is not None and cache_path.is_file() and cache_path.stat().st_size > 0:
        logger.info(f'Reading {filename} from cache: {cache_path}')
        return cache_path.read_bytes()

    missing = str(cache_path) if cache_path is not None else filename
    if os.environ.get(OPERATOR_DOWNLOAD_ENV) != '1':
        raise ValueError(
            f'CNEFE cache miss: missing {missing}. '
            'ftp.ibge.gov.br is not in ingest.HOSTS HTTPS allowlist; '
            'refusing silent FTP/HTTP download. Place the zip in the cache directory, '
            f'or set {OPERATOR_DOWNLOAD_ENV}=1 as an operator exception '
            '(not a HOSTS expansion to FTP).'
        )

    url = f'{CNEFE_BASE}/{filename}'
    logger.warning(
        f'CNEFE operator-exception download of {filename} from {url}; '
        f'{OPERATOR_DOWNLOAD_ENV}=1 is not an ingest.HOSTS expansion to FTP'
    )
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError(f'ibge_download_failed_{resp.status}')
        data = resp.read()

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / filename
        dest.write_bytes(data)

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
    """Exact normalized name only. Token-subset matches are not coordinates."""
    n_key = normalize_school_name(school_name)
    if not n_key:
        return None
    return mun_cnefe.get(n_key)


def geocode_schools_for_state(database: Database, state: str,
                              cnefe_by_mun: dict[str, dict[str, tuple[float, float, str]]],
                              *, batch_size: int = 200) -> dict[str, int]:
    """Store unpublished CNEFE name-match candidates for schools in a state.

    Never copies matched coordinates onto Place.latitude / Place.longitude or
    geo_source. A name match is not an official identifier dictionary.
    """
    stats = Counter()

    with database.session() as session:
        query = (
            select(Place)
            .where(Place.kind == 'school', Place.state == state.upper())
        )
        places = session.scalars(query).all()
        stats['total_schools'] = len(places)

        pending = 0
        for place in places:
            if place.latitude is not None and place.longitude is not None:
                stats['already_geocoded'] += 1
                continue

            mun_dict = cnefe_by_mun.get(place.municipality_id)
            if not mun_dict:
                stats['no_mun_cnefe'] += 1
                continue

            match = find_cnefe_match(place.name, mun_dict)
            if match:
                lat, lon, cnefe_name = match
                if not isinstance(place.payload, dict):
                    stats['validation_error'] += 1
                    logger.debug(f'payload is not a dict for {place.id}')
                    continue
                payload = dict(place.payload)
                payload.pop('latitude', None)
                payload.pop('longitude', None)
                if payload.get('geo_source') == 'IBGE-CNEFE-2022':
                    payload.pop('geo_source', None)
                payload['cnefe_candidate'] = {
                    'lat': lat,
                    'lon': lon,
                    'cnefe_name': cnefe_name,
                    'match': 'exact_name',
                }
                place.payload = payload
                stats['matched'] += 1
                pending += 1
                logger.debug(
                    f'cnefe_candidate stored place_id={place.id} '
                    f'municipality_id={place.municipality_id} match=exact_name'
                )
                if pending >= batch_size:
                    session.commit()
                    pending = 0
            else:
                stats['unmatched'] += 1

        if pending:
            session.commit()

    return dict(stats)

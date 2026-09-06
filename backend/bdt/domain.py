"""Deterministic contracts: evidence is required; coordinates and conclusions are not."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal["school", "health", "work"]
Phase = Literal["estimated", "agreed", "committed", "transferred", "contracted", "liquidated", "paid"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cnpj(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("CNPJ must be a string; leading zeros cannot be guessed")
    normalized = re.sub(r"[./\s-]", "", value.upper())
    if not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", normalized):
        raise ValueError("Invalid CNPJ format (check digits and registration are not validated here)")
    return normalized


def brl(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("Brazilian currency must be an explicit string")
    raw = re.sub(r"^R\$\s*", "", value.replace("\u00a0", " ").strip())
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}", raw):
        raise ValueError("Ambiguous Brazilian monetary value")
    return int(Decimal(raw.replace(".", "").replace(",", ".")) * 100)


def decimal_cents(value: str | int | Decimal) -> int:
    if isinstance(value, (float, bool)):
        raise ValueError("Use decimal text, never binary float")
    number = Decimal(value) * 100
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("Non-finite value or fractional cents")
    return int(number)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(StrictModel):
    dataset: str = Field(min_length=2, max_length=100)
    url: str = Field(max_length=2000)
    record_id: str = Field(min_length=1, max_length=180)
    reference_date: str | None = Field(default=None, max_length=80)
    collected_at: str
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("url")
    @classmethod
    def url_http(cls, value: str) -> str:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Public HTTP(S) reference required")
        return value

    @field_validator("collected_at")
    @classmethod
    def aware_date(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Collection timestamp must include timezone")
        return parsed.isoformat()


class PlaceInput(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9_-]+:[A-Za-z0-9._/-]+$", max_length=180)
    kind: Kind
    catalogue_eligible: bool = True
    name: str = Field(min_length=2, max_length=300)
    municipality_id: str = Field(pattern=r"^[0-9]{7}$")
    state: str = Field(pattern=r"^[A-Z]{2}$")
    address: str = Field(default="", max_length=600)
    phone: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    geo_source: str | None = Field(default=None, max_length=100)
    declared_services: list[str] = Field(default_factory=list, max_length=30)
    source: Source

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must be a pair or both null")
        if self.latitude is not None and not self.geo_source:
            raise ValueError("Coordinates require provenance")
        return self


class MoneyEvent(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    source: Source
    municipality_id: str = Field(pattern=r"^[0-9]{7}$")
    instrument_id: str = Field(min_length=1, max_length=180)
    phase: Phase
    cents: Annotated[int, Field(strict=True)]
    currency: Literal["BRL"] = "BRL"
    period: str = Field(pattern=r"^[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?$")
    recipient: str = Field(min_length=1, max_length=200)
    perspective: Literal["federal", "state", "municipal", "executing_unit"]
    nature: Literal["event", "cumulative", "estimate"] = "event"
    facility_id: str | None = Field(default=None, max_length=180)
    relation_state: Literal["territorial", "direct", "reviewed"] = "territorial"
    evidence: str | None = Field(default=None, max_length=2000)

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        date.fromisoformat(value + "-01-01" if len(value) == 4 else value + "-01" if len(value) == 7 else value)
        return value

    @model_validator(mode="after")
    def link_evidence(self):
        if self.facility_id and (self.relation_state == "territorial" or not self.evidence):
            raise ValueError("Facility assignment requires confirmed evidence")
        if self.relation_state != "territorial" and not self.facility_id:
            raise ValueError("Confirmed facility relation requires facility_id")
        return self


def financial_cells(events: list[dict]) -> list[dict]:
    """Never combine stages, recipients, sources, instruments or cumulative snapshots."""
    unique: dict[tuple, dict] = {}
    cells: dict[tuple, dict] = {}
    for raw in events:
        event = MoneyEvent.model_validate(raw).model_dump()
        key = (event["source"]["dataset"], event["id"])
        if key in unique and unique[key] != event:
            raise ValueError("Conflicting versions of the same financial event")
        unique[key] = event
    fields = ("municipality_id", "instrument_id", "phase", "period", "recipient", "perspective", "nature", "currency")
    for event in unique.values():
        key = (event["source"]["dataset"], *(event[k] for k in fields), event["id"] if event["nature"] != "event" else "")
        cell = cells.setdefault(key, {k: event[k] for k in fields} | {"source_dataset": key[0], "cents": 0, "records": 0})
        cell["cents"] += event["cents"]
        cell["records"] += 1
    return list(cells.values())


class ObservationInput(StrictModel):
    place_id: str = Field(max_length=180)
    mode: Literal["field", "document", "street_image"]
    observed_on: date
    body: str = Field(min_length=20, max_length=1200)
    reference_url: str | None = Field(default=None, max_length=2000)
    consent: Literal[True]

    @model_validator(mode="after")
    def valid_observation(self):
        if self.observed_on > datetime.now(timezone.utc).date():
            raise ValueError("Observation cannot be in the future")
        if self.mode != "field" and not self.reference_url:
            raise ValueError("Document/image observations require a reference")
        if self.reference_url:
            Source.url_http(self.reference_url)
        return self

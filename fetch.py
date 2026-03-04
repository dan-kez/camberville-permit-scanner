"""Fetch permits from Socrata APIs and normalize to common schema.

Raw API responses are cached to .cache/ as JSON files. Cached data is used by
default; pass use_cache=False to fetch_all() (or --no-cache on the CLI) to
force a fresh pull from the APIs.
"""

import json
import os
from datetime import datetime

import requests

from config import (
    CAMBRIDGE_ALTERATION,
    CAMBRIDGE_NEW_CONSTRUCTION,
    FETCH_LIMIT,
    LOOKBACK_DATE,
    MIN_COST_THRESHOLD,
    SOMERVILLE_PERMITS,
)

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")

SOURCES = {
    "cambridge_alteration": {
        "url": CAMBRIDGE_ALTERATION,
        "params": {
            "$where": f"applicant_submit_date > '{LOOKBACK_DATE}'",
            "$limit": FETCH_LIMIT,
        },
    },
    "cambridge_new_construction": {
        "url": CAMBRIDGE_NEW_CONSTRUCTION,
        "params": {
            "$where": f"applicant_submit_date > '{LOOKBACK_DATE}'",
            "$limit": FETCH_LIMIT,
        },
    },
    "somerville": {
        "url": SOMERVILLE_PERMITS,
        "params": {
            "$where": f"issue_date > '{LOOKBACK_DATE}'",
            "$limit": FETCH_LIMIT,
        },
    },
}


def _cache_path(source_key):
    return os.path.join(CACHE_DIR, f"{source_key}.json")


def _read_cache(source_key):
    """Read cached raw API payload. Returns (rows, mtime_str) or (None, None)."""
    path = _cache_path(source_key)
    if not os.path.exists(path):
        return None, None
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    with open(path) as f:
        return json.load(f), mtime.strftime("%Y-%m-%d %H:%M")


def _write_cache(source_key, rows):
    """Write raw API payload to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(source_key), "w") as f:
        json.dump(rows, f)


def _fetch_json(url, params):
    """Fetch JSON from Socrata endpoint."""
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_rows(source_key, use_cache=True):
    """Get raw rows for a source, from cache or API."""
    if use_cache:
        rows, mtime = _read_cache(source_key)
        if rows is not None:
            return rows, f"cached {mtime}"
    src = SOURCES[source_key]
    rows = _fetch_json(src["url"], src["params"])
    _write_cache(source_key, rows)
    return rows, "fetched"


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _normalize_cambridge_alteration(rows):
    permits = []
    for r in rows:
        cost = _safe_float(r.get("total_cost"))
        if cost < MIN_COST_THRESHOLD:
            continue
        lat = _safe_float(r.get("latitude"))
        lng = _safe_float(r.get("longitude"))
        if not lat or not lng:
            continue
        permits.append({
            "address": (r.get("full_address") or "").strip(),
            "lat": lat,
            "lng": lng,
            "description": (r.get("detailed_description_of_work") or "").strip(),
            "cost": cost,
            "property_use": (r.get("current_property_use") or "").strip(),
            "dwelling_count": r.get("current_number_of_dwelling", ""),
            "contractor": (r.get("firm_name") or "").strip(),
            "status": (r.get("status") or "").strip(),
            "date": (r.get("applicant_submit_date") or "")[:10],
            "source": "Cambridge Alteration",
        })
    return permits


def _normalize_cambridge_new_construction(rows):
    permits = []
    for r in rows:
        cost = _safe_float(r.get("total_cost_of_construction"))
        lat = _safe_float(r.get("latitude"))
        lng = _safe_float(r.get("longitude"))
        if not lat or not lng:
            continue
        contractor_parts = [
            (r.get("licensed_name") or "").strip(),
            (r.get("architect_firm") or "").strip(),
        ]
        contractor = " / ".join(p for p in contractor_parts if p)
        permits.append({
            "address": (r.get("full_address") or "").strip(),
            "lat": lat,
            "lng": lng,
            "description": (r.get("description_of_work") or "").strip(),
            "cost": cost,
            "property_use": (r.get("proposed_building_use") or "").strip(),
            "dwelling_count": "",
            "contractor": contractor,
            "status": (r.get("status") or "").strip(),
            "date": (r.get("applicant_submit_date") or "")[:10],
            "source": "Cambridge New Construction",
        })
    return permits


def _normalize_somerville(rows):
    permits = []
    for r in rows:
        lat = _safe_float(r.get("application_latitude"))
        lng = _safe_float(r.get("application_longitude"))
        if not lat or not lng:
            continue
        app_type = (r.get("application_type") or "").strip()
        app_subtype = (r.get("application_subtype") or "").strip()
        property_use = f"{app_type} - {app_subtype}" if app_subtype else app_type
        permits.append({
            "address": (r.get("application_address") or "").strip(),
            "lat": lat,
            "lng": lng,
            "description": (r.get("project_description_or_business_name") or "").strip(),
            "cost": _safe_float(r.get("application_amount")),
            "property_use": property_use,
            "dwelling_count": "",
            "contractor": (r.get("applicant_company_name") or "").strip(),
            "status": (r.get("status") or "").strip(),
            "date": (r.get("issue_date") or "")[:10],
            "source": "Somerville",
        })
    return permits


_NORMALIZERS = {
    "cambridge_alteration": ("Cambridge Alteration", _normalize_cambridge_alteration),
    "cambridge_new_construction": ("Cambridge New Construction", _normalize_cambridge_new_construction),
    "somerville": ("Somerville", _normalize_somerville),
}


def fetch_all(use_cache=True):
    """Fetch from all sources and return combined normalized list."""
    all_permits = []
    for key, (display_name, normalize) in _NORMALIZERS.items():
        try:
            rows, status = _get_rows(key, use_cache=use_cache)
            permits = normalize(rows)
            print(f"  {display_name}: {len(permits)} permits ({status})")
            all_permits.extend(permits)
        except Exception as e:
            print(f"  Warning: Failed to fetch {display_name}: {e}")
    return all_permits

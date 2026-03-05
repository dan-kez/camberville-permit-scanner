"""Fetch permits from Socrata and ArcGIS APIs and normalize to common schema.

Raw API responses are cached to .cache/ as JSON files. Cached data is used by
default; pass use_cache=False to fetch_all() (or --no-cache on the CLI) to
force a fresh pull from the APIs.
"""

import json
import os
import re
import time
from datetime import datetime

import requests

from config import (
    CAMBRIDGE_ALTERATION,
    CAMBRIDGE_NEW_CONSTRUCTION,
    CAMBRIDGE_PROPERTY_DB,
    FETCH_LIMIT,
    LOOKBACK_DATE,
    MIN_COST_THRESHOLD,
    SOMERVILLE_PERMITS,
    SOMERVILLE_PROPERTY_DB,
    SOMERVILLE_TOWN_ID,
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
    "cambridge_properties": {
        "url": CAMBRIDGE_PROPERTY_DB,
        "params": {
            "$where": "yearofassessment='2026'",
            "$limit": 50000,
        },
    },
    "somerville_properties": {
        "url": SOMERVILLE_PROPERTY_DB,
        "params": {
            "where": f"TOWN_ID={SOMERVILLE_TOWN_ID}",
            "outFields": "*",
            "f": "json",
            "resultRecordCount": 2000,
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
    # Ensure limit is respected, SODA defaults to 1000
    if "$limit" not in params:
        params["$limit"] = 5000
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _fetch_arcgis_json_paged(url, params):
    """Fetch all records from ArcGIS REST endpoint using paging."""
    all_features = []
    offset = 0
    batch_size = params.get("resultRecordCount", 2000)
    
    while True:
        p = params.copy()
        p["resultOffset"] = offset
        
        resp = requests.get(url, params=p, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        features = data.get("features", [])
        if not features:
            break
            
        all_features.extend([f["attributes"] for f in features])
        
        if not data.get("exceededTransferLimit"):
            break
            
        offset += len(features)
        # Small sleep to be polite
        time.sleep(0.1)
        
    return all_features


def _get_rows(source_key, use_cache=True):
    """Get raw rows for a source, from cache or API."""
    if use_cache:
        rows, mtime = _read_cache(source_key)
        if rows is not None:
            return rows, f"cached {mtime}"
    
    src = SOURCES[source_key]
    if source_key == "somerville_properties":
        rows = _fetch_arcgis_json_paged(src["url"], src["params"])
    else:
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


def normalize_address_key(addr):
    """Normalize address for cache key and lookup."""
    if not addr: return ""
    a = addr.lower().strip()
    
    # Remove unit numbers like ", Unit 13" or " Unit 13"
    a = re.sub(r",?\s+\bunit\b\s+\w+", "", a)
    
    # More robust removal of City, State, Zip
    # First remove anything after a comma if it looks like city/state (e.g. ", Somerville MA")
    a = re.sub(r",\s*(cambridge|somerville|massachusetts|ma).*$", "", a)
    
    # Remove ZIP code
    a = re.sub(r"\b\d{5}(-\d{4})?\b", "", a)
    # Remove common city/state suffixes if not preceded by comma
    a = re.sub(r"\b(cambridge|somerville|ma|massachusetts)\b", "", a)
    
    # Remove punctuation
    a = re.sub(r"[,.#]", " ", a)
    
    # Standardize street types
    a = re.sub(r"\bstreet\b", "st", a)
    a = re.sub(r"\bavenue\b", "ave", a)
    a = re.sub(r"\broad\b", "rd", a)
    a = re.sub(r"\bplace\b", "pl", a)
    a = re.sub(r"\bsquare\b", "sq", a)
    a = re.sub(r"\bparkway\b", "pkwy", a)
    a = re.sub(r"\blane\b", "ln", a)
    a = re.sub(r"\bterrace\b", "ter", a)
    a = re.sub(r"\bhighway\b", "hwy", a)
    a = re.sub(r"\bcourt\b", "ct", a)
    
    # Extra whitespace
    a = re.sub(r"\s+", " ", a).strip()
    return a


def _normalize_cambridge_property(rows):
    """Index properties by normalized address for fast lookup."""
    indexed = {}
    for r in rows:
        # Index by both primary address and owner_address as fallback
        addresses = [r.get("address", ""), r.get("owner_address", "")]
        
        info = {
            "property_class": r.get("propertyclass", "unknown"),
            "year_built": r.get("condition_yearbuilt", "unknown"),
            "bedrooms": r.get("interior_bedrooms", "0"),
            "bathrooms": f"{r.get('interior_fullbaths', '0')}/{r.get('interior_halfbaths', '0')}",
            "total_rooms": r.get("interior_totalrooms", "0"),
            "living_area": r.get("interior_livingarea", "0"),
            "last_sale_date": r.get("saledate", "unknown"),
            "last_sale_price": r.get("saleprice", "0"),
            "assessed_value": r.get("assessedvalue", "0"),
            "lot_size": r.get("landarea", "0"),
        }
        
        for addr in addresses:
            if not addr: continue
            key = normalize_address_key(addr)
            if key:
                # Add city prefix to avoid collisions
                indexed[f"cambridge:{key}"] = info
                
    return indexed


def _normalize_somerville_property(rows):
    """Index Somerville properties (MassGIS ArcGIS schema) by normalized address."""
    indexed = {}
    for r in rows:
        # MassGIS fields: SITE_ADDR, USE_CODE, YEAR_BUILT, NUM_ROOMS, RES_AREA, LS_DATE, LS_PRICE, TOTAL_VAL, LOT_SIZE
        addr = r.get("SITE_ADDR", "")
        if not addr: continue
        
        key = normalize_address_key(addr)
        
        # LS_DATE is YYYYMMDD
        ls_date = r.get("LS_DATE", "unknown")
        if ls_date and ls_date != "unknown" and len(str(ls_date)) == 8:
            s = str(ls_date)
            ls_date = f"{s[:4]}-{s[4:6]}-{s[6:]}"
            
        indexed[f"somerville:{key}"] = {
            "property_class": r.get("USE_CODE", "unknown"),
            "year_built": r.get("YEAR_BUILT", "unknown"),
            "bedrooms": "unknown", 
            "bathrooms": "unknown",
            "total_rooms": r.get("NUM_ROOMS", "0"),
            "living_area": r.get("RES_AREA", "0"),
            "last_sale_date": ls_date,
            "last_sale_price": r.get("LS_PRICE", "0"),
            "assessed_value": r.get("TOTAL_VAL", "0"),
            "lot_size": r.get("LOT_SIZE", "0"),
        }
    return indexed


def fetch_properties(use_cache=True):
    """Fetch property databases for Cambridge and Somerville and index them."""
    all_properties = {}
    
    # Cambridge
    try:
        rows, status = _get_rows("cambridge_properties", use_cache=use_cache)
        if not rows: # Try fallback to 2025
            orig_params = SOURCES["cambridge_properties"]["params"].copy()
            SOURCES["cambridge_properties"]["params"]["$where"] = "yearofassessment='2025'"
            rows, status = _get_rows("cambridge_properties", use_cache=False)
            SOURCES["cambridge_properties"]["params"] = orig_params
            
        cam_props = _normalize_cambridge_property(rows)
        print(f"  Cambridge Properties: {len(cam_props)} indexed ({status})")
        all_properties.update(cam_props)
    except Exception as e:
        print(f"  Warning: Failed to fetch Cambridge properties: {e}")
        
    # Somerville
    try:
        rows, status = _get_rows("somerville_properties", use_cache=use_cache)
        som_props = _normalize_somerville_property(rows)
        print(f"  Somerville Properties: {len(som_props)} indexed ({status})")
        all_properties.update(som_props)
    except Exception as e:
        print(f"  Warning: Failed to fetch Somerville properties: {e}")
        
    return all_properties

"""One-time script to backfill permit IDs and property IDs into existing summary JSONs."""

import json
import os
import sys

# Import normalize_address_key from fetch.py
sys.path.insert(0, os.path.dirname(__file__))
from fetch import normalize_address_key

SUMMARY_DIR = "summaries/llm_assessment_summary"
CACHE_DIR = ".cache"


def build_permit_lookup():
    """Build (source, address_upper, date) -> {permit_id, ...} lookup from cache files."""
    lookup = {}

    # Cambridge Alteration
    path = os.path.join(CACHE_DIR, "cambridge_alteration.json")
    if os.path.exists(path):
        records = json.loads(open(path).read())
        for r in records:
            addr = r.get("full_address", "")
            date = (r.get("applicant_submit_date") or "")[:10]
            if addr and date:
                key = ("Cambridge Alteration", addr.upper(), date)
                lookup[key] = {"permit_id": r.get("id")}
        print(f"  Loaded {len(records)} Cambridge Alteration records")
    else:
        print(f"  WARN: {path} not found")

    # Cambridge New Construction
    path = os.path.join(CACHE_DIR, "cambridge_new_construction.json")
    if os.path.exists(path):
        records = json.loads(open(path).read())
        for r in records:
            addr = r.get("full_address", "")
            date = (r.get("applicant_submit_date") or "")[:10]
            if addr and date:
                key = ("Cambridge New Construction", addr.upper(), date)
                lookup[key] = {"permit_id": r.get("id")}
        print(f"  Loaded {len(records)} Cambridge New Construction records")
    else:
        print(f"  WARN: {path} not found")

    # Somerville
    path = os.path.join(CACHE_DIR, "somerville.json")
    if os.path.exists(path):
        records = json.loads(open(path).read())
        for r in records:
            addr = r.get("application_address", "")
            date = (r.get("issue_date") or "")[:10]
            if addr and date:
                key = ("Somerville", addr.upper(), date)
                lookup[key] = {
                    "permit_id": r.get("application_id"),
                    "permit_number": r.get("application_number"),
                }
        print(f"  Loaded {len(records)} Somerville records")
    else:
        print(f"  WARN: {path} not found")

    print(f"  Built permit lookup with {len(lookup)} entries")
    return lookup


def build_property_lookup():
    """Build city:norm_addr -> {property_pid, property_parcel} lookup from property cache files."""
    lookup = {}

    # Cambridge properties
    path = os.path.join(CACHE_DIR, "cambridge_properties.json")
    if os.path.exists(path):
        records = json.loads(open(path).read())
        for r in records:
            addr = r.get("address", "")
            if not addr:
                continue
            norm = normalize_address_key(addr)
            if norm:
                lookup[f"cambridge:{norm}"] = {
                    "property_pid": r.get("pid"),
                    "property_parcel": r.get("map_lot"),
                }
        print(f"  Loaded {len(records)} Cambridge property records")
    else:
        print(f"  WARN: {path} not found")

    # Somerville properties
    path = os.path.join(CACHE_DIR, "somerville_properties.json")
    if os.path.exists(path):
        records = json.loads(open(path).read())
        for r in records:
            addr = r.get("SITE_ADDR", "")
            if not addr:
                continue
            norm = normalize_address_key(addr)
            if norm:
                lookup[f"somerville:{norm}"] = {
                    "property_parcel": r.get("PROP_ID"),
                }
        print(f"  Loaded {len(records)} Somerville property records")
    else:
        print(f"  WARN: {path} not found")

    print(f"  Built property lookup with {len(lookup)} entries")
    return lookup


def backfill_permits(permit_lookup):
    """Patch permit_id/permit_number into each permit entry in summary JSONs."""
    files = sorted(f for f in os.listdir(SUMMARY_DIR) if f.endswith(".json"))
    hits = misses = skipped = 0

    for fname in files:
        path = os.path.join(SUMMARY_DIR, fname)
        data = json.loads(open(path).read())
        changed = False
        top_addr = data.get("address", "").upper()

        for permit in data.get("permits", []):
            if "permit_id" in permit:
                skipped += 1
                continue
            key = (permit.get("source", ""), top_addr, permit.get("date", ""))
            match = permit_lookup.get(key)
            if match:
                permit.update(match)
                changed = True
                hits += 1
            else:
                misses += 1

        if changed:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    print(f"  Permit IDs: {hits} patched, {skipped} already present, {misses} not found")
    return hits


def backfill_properties(prop_lookup):
    """Patch property_pid/property_parcel into property_info in summary JSONs."""
    files = sorted(f for f in os.listdir(SUMMARY_DIR) if f.endswith(".json"))
    hits = misses = 0

    for fname in files:
        path = os.path.join(SUMMARY_DIR, fname)
        data = json.loads(open(path).read())
        changed = False

        addr = data.get("address", "")
        city = "cambridge" if "CAMBRIDGE" in addr.upper() else "somerville"
        norm = normalize_address_key(addr)
        key = f"{city}:{norm}"

        match = prop_lookup.get(key)
        if match:
            pi = data.setdefault("property_info", {})
            for k, v in match.items():
                if v and k not in pi:
                    pi[k] = v
                    changed = True
            if changed:
                hits += 1
        else:
            misses += 1

        if changed:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    print(f"  Property IDs: {hits} patched, {misses} not found")
    return hits


if __name__ == "__main__":
    if not os.path.isdir(SUMMARY_DIR):
        print(f"ERROR: {SUMMARY_DIR} not found")
        sys.exit(1)

    print("Building permit lookup from cache...")
    permit_lookup = build_permit_lookup()

    print("\nBuilding property lookup from cache...")
    prop_lookup = build_property_lookup()

    print(f"\nBackfilling {SUMMARY_DIR}/...")
    permit_hits = backfill_permits(permit_lookup)
    prop_hits = backfill_properties(prop_lookup)

    print(f"\nDone: {permit_hits} permit IDs patched, {prop_hits} property ID sets patched")

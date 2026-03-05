"""One-time script to backfill lat/lng from cache files into llm_assessment_summary JSONs."""

import json
import os
import re


def slugify(addr):
    """Convert address to filename-safe slug (same logic as analyze.py sanitize_filename)."""
    name = addr.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name[:80]


def load_coords():
    """Build slug -> (lat, lng) lookup from all cache files."""
    coords = {}

    sources = [
        (".cache/cambridge_alteration.json", "full_address", "latitude", "longitude"),
        (".cache/cambridge_new_construction.json", "full_address", "latitude", "longitude"),
        (".cache/somerville.json", "application_address", "application_latitude", "application_longitude"),
    ]

    for path, addr_field, lat_field, lng_field in sources:
        if not os.path.exists(path):
            print(f"  WARN: {path} not found, skipping")
            continue
        with open(path) as f:
            records = json.load(f)
        for r in records:
            addr = r.get(addr_field, "")
            lat = r.get(lat_field)
            lng = r.get(lng_field)
            if addr and lat is not None and lng is not None:
                slug = slugify(addr)
                coords[slug] = (float(lat), float(lng))
        print(f"  Loaded {len(records)} records from {path}")

    print(f"  Built coord lookup with {len(coords)} unique slugs")
    return coords


def backfill(summary_dir="summaries/llm_assessment_summary"):
    coords = load_coords()

    files = sorted(f for f in os.listdir(summary_dir) if f.endswith(".json"))
    ok = skip = miss = 0

    for fname in files:
        slug = fname[:-5]  # strip .json
        path = os.path.join(summary_dir, fname)

        with open(path) as f:
            record = json.load(f)

        if "lat" in record and "lng" in record:
            skip += 1
            print(f"  SKIP {fname}")
            continue

        if slug in coords:
            lat, lng = coords[slug]
            record["lat"] = lat
            record["lng"] = lng
            with open(path, "w") as f:
                json.dump(record, f, indent=2)
            ok += 1
            print(f"  OK   {fname}  ({lat}, {lng})")
        else:
            miss += 1
            print(f"  MISS {fname}")

    print(f"\nDone: {ok} OK, {skip} skipped (already had coords), {miss} missing")


if __name__ == "__main__":
    backfill()

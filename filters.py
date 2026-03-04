"""Filtering pipeline: proximity, residential, significance scoring."""

import math

from config import COMPLETED_STATUSES, MINOR_KEYWORDS, SIGNIFICANT_KEYWORDS, SQUARES
from fetch import normalize_address_key


def haversine_mi(lat1, lng1, lat2, lng2):
    """Haversine distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def nearest_square(lat, lng):
    """Return (name, distance_mi) for the nearest target square."""
    best_name = None
    best_dist = float("inf")
    for name, (slat, slng) in SQUARES.items():
        d = haversine_mi(lat, lng, slat, slng)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name, best_dist


def filter_proximity(permits, radius_mi):
    """Keep permits within radius of any target square. Adds nearest_square and distance."""
    result = []
    for p in permits:
        name, dist = nearest_square(p["lat"], p["lng"])
        if dist <= radius_mi:
            p["nearest_square"] = name
            p["distance_mi"] = round(dist, 2)
            result.append(p)
    return result


def is_residential_single_family(permit, properties=None):
    """Check if a permit is for a detached single-family home.
    
    Prioritizes information from the property database if available.
    """
    address = permit.get("address", "")
    norm_addr = normalize_address_key(address)
    source = permit.get("source", "")
    
    # 1. Use property database if available
    if properties and norm_addr in properties:
        p_info = properties[norm_addr]
        p_class = p_info.get("property_class", "").upper()
        
        # Cambridge single-family classes
        if "Cambridge" in source:
            sngl_fam_classes = ["SNGL-FAM-RES", "SINGLE FAM W/AUXILIARY APT", "MXD SNGL-FAM-RES"]
            if p_class in sngl_fam_classes:
                return True
            return False
            
        # Somerville
        if "Somerville" in source:
            # MassGIS USE_CODE 1010 is single-family
            if p_class == "1010":
                return True
            # Special case: allow 2-family (1040) if permit description suggests conversion
            if p_class == "1040":
                desc = permit.get("description", "").lower()
                if any(kw in desc for kw in ["to single family", "to 1 family", "to one family"]):
                    return True
            return False

    # 2. Fallback to permit data (if property info missing or source is Somerville)
    prop_use = permit.get("property_use", "").lower()
    desc = permit.get("description", "").lower()
    dwelling = str(permit.get("dwelling_count", "")).strip()

    # Keywords that indicate multi-family or non-detached (exclude)
    exclude_kws = [
        "multi", "2 family", "3 family", "two-family", "three-family", "two family", "three family",
        "apartment", "condo", "townhouse", "attached", "mixed use", "commercial",
        "2-family", "3-family",
    ]

    if any(kw in prop_use for kw in exclude_kws):
        return False

    if "Somerville" in source:
        # Somerville: check application_type/subtype
        if "residential" in prop_use:
            # Must explicitly be single or 1-family
            if any(kw in prop_use for kw in ["single", "1 family", "one family"]):
                return True
            # "Residential" without qualifier — check description for strict single-family indicators
            if any(kw in desc for kw in ["single family", "single-family", "1 family", "sfr"]):
                if not any(kw in desc for kw in exclude_kws):
                    return True
        return False

    # Cambridge permit fallback
    if "single family" in prop_use or "single-family" in prop_use:
        return True
    if dwelling == "1":
        # Double check prop_use for exclusions even if dwelling is 1 (e.g. 1 unit in a condo)
        if any(kw in prop_use for kw in exclude_kws):
            return False
        return True

    # Check description for residential indicators
    if any(kw in desc for kw in ["single family", "single-family", "1 family", "sfr"]):
        if not any(kw in desc for kw in exclude_kws):
            return True

    return False


def filter_residential(permits, properties=None):
    """Keep only single-family residential permits."""
    return [p for p in permits if is_residential_single_family(p, properties)]


def score_significance(permit):
    """Score a permit's significance. Returns (score, reasons)."""
    score = 0
    reasons = []
    desc = permit.get("description", "").lower()
    cost = permit.get("cost", 0)
    source = permit.get("source", "")
    status = permit.get("status", "")

    # Cost scoring — Cambridge only (Somerville amount is permit fee)
    if "Cambridge" in source:
        if cost >= 200000:
            score += 3
            reasons.append(f"high cost (${cost:,.0f})")
        elif cost >= 25000:
            score += 1
            reasons.append(f"moderate cost (${cost:,.0f})")

    # Significant work keywords
    for kw in SIGNIFICANT_KEYWORDS:
        if kw in desc:
            score += 2
            reasons.append(f"keyword: {kw}")
            break  # Only count once

    # Minor work keywords
    for kw in MINOR_KEYWORDS:
        if kw in desc:
            score -= 3
            reasons.append(f"minor: {kw}")
            break

    # New construction bonus
    if "New Construction" in source:
        score += 3
        reasons.append("new construction")

    # Completion status bonus
    if status in COMPLETED_STATUSES:
        score += 2
        reasons.append("permit completed")

    permit["score"] = score
    permit["score_reasons"] = "; ".join(reasons) if reasons else "no signals"
    return permit


def score_address_completion(permits):
    """Group permits by address and add bonus if all or most are completed."""
    if not permits:
        return permits

    # Grouping by normalized address
    groups = {}
    for p in permits:
        addr = p.get("address", "").strip().upper()
        addr = " ".join(addr.split())  # simple normalization
        groups.setdefault(addr, []).append(p)

    for addr, group in groups.items():
        total = len(group)
        completed = sum(1 for p in group if p.get("status") in COMPLETED_STATUSES)

        if completed == 0:
            continue

        ratio_str = f"{completed}/{total} complete"

        bonus = 0
        reason = ""
        if completed == total:
            bonus = 3
            reason = "all permits completed"
        elif completed > total / 2:
            bonus = 1
            reason = "most permits completed"

        for p in group:
            p["completed_permits"] = completed
            p["completion_ratio"] = ratio_str
            if bonus > 0:
                p["score"] += bonus
                reasons = p.get("score_reasons", "no signals").split("; ")
                if reasons == ["no signals"]:
                    reasons = []
                reasons.append(reason)
                p["score_reasons"] = "; ".join(reasons)

    return permits


def apply_filters(permits, properties, radius_mi, min_score, skip_residential=False, skip_significance=False, only_completing=False):
    """Run the full filter pipeline."""
    permits = filter_proximity(permits, radius_mi)
    print(f"  After proximity filter ({radius_mi} mi): {len(permits)} permits")

    if not skip_residential:
        permits = filter_residential(permits, properties)
        print(f"  After residential filter: {len(permits)} permits")

    permits = [score_significance(p) for p in permits]

    if not skip_significance:
        permits = score_address_completion(permits)
        permits = [p for p in permits if p["score"] >= min_score]
        print(f"  After significance filter (≥{min_score}): {len(permits)} permits")

    if only_completing:
        def normalize(a):
            return " ".join(a.strip().upper().split())
        completed_addresses = {
            normalize(p.get("address", ""))
            for p in permits
            if p.get("status") in COMPLETED_STATUSES
        }
        permits = [p for p in permits if normalize(p.get("address", "")) in completed_addresses]
        print(f"  After completing-only filter: {len(permits)} permits")

    permits.sort(key=lambda p: p.get("score", 0), reverse=True)
    return permits

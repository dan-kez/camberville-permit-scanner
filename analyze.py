"""Group permits by address and generate per-address summaries for LLM analysis."""

import json
import os
import re
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from fetch import normalize_address_key


def normalize_address(addr):
    """Normalize address for grouping."""
    return re.sub(r"\s+", " ", addr.strip().upper())


def sanitize_filename(addr):
    """Convert address to a safe filename."""
    name = addr.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name[:80]


def group_by_address(permits):
    """Group permits by normalized address."""
    groups = {}
    for p in permits:
        key = normalize_address(p.get("address", ""))
        if not key:
            continue
        groups.setdefault(key, []).append(p)
    return groups


def _build_summary_record(address, permits, properties):
    """Build a structured JSON record for one address."""
    p0 = permits[0]
    total_cost = sum(p.get("cost", 0) for p in permits)
    
    # Create Search URLs
    encoded_addr = urllib.parse.quote_plus(address)
    # Zillow often prefers hyphens or %20 over + in the path-based URL
    encoded_addr_path = urllib.parse.quote(address)
    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_addr}"
    zillow_url = f"https://www.zillow.com/homes/{encoded_addr_path}_rb/"
    # Google search fallback
    google_search_url = f"https://www.google.com/search?q={encoded_addr}+zillow+redfin"
    
    # Lookup property info from pre-fetched properties
    norm_addr = normalize_address_key(address)
    city = "cambridge" if "Cambridge" in p0.get("source", "") else "somerville"
    property_info = properties.get(f"{city}:{norm_addr}")
    
    return {
        "address": address,
        "lat": p0.get("lat"),
        "lng": p0.get("lng"),
        "google_maps_url": google_maps_url,
        "zillow_url": zillow_url,
        "google_search_url": google_search_url,
        "property_info": property_info,
        "property_use": p0.get("property_use", ""),
        "nearest_square": p0.get("nearest_square", ""),
        "distance_mi": p0.get("distance_mi", 0),
        "max_score": max((p.get("score", 0) for p in permits), default=0),
        "total_cost": total_cost,
        "permit_count": len(permits),
        "completed_permits": p0.get("completed_permits", 0),
        "completion_ratio": p0.get("completion_ratio", f"0/{len(permits)}"),
        "permits": [
            {
                "date": p.get("date", ""),
                "source": p.get("source", ""),
                "status": p.get("status", ""),
                "description": p.get("description", ""),
                "cost": p.get("cost", 0),
                "property_use": p.get("property_use", ""),
                "contractor": p.get("contractor", ""),
                "owner_occupied": p.get("owner_occupied", True),
                "score": p.get("score", 0),
                "score_reasons": p.get("score_reasons", ""),
                **({} if not p.get("permit_id") else {"permit_id": p["permit_id"]}),
                **({} if not p.get("permit_number") else {"permit_number": p["permit_number"]}),
            }
            for p in permits
        ],
    }


def max_score_for_address(permits):
    """Return the highest significance score among a group of permits."""
    return max((p.get("score", 0) for p in permits), default=0)


def write_summaries(permits, properties, output_dir="summaries", min_score=None):
    """Group permits by address and write JSON summary files.

    If min_score is set, only write summaries for addresses where at least one
    permit meets that score threshold.
    """
    os.makedirs(output_dir, exist_ok=True)
    groups = group_by_address(permits)

    files_written = []
    skipped = 0
    for address, addr_permits in sorted(groups.items()):
        if min_score is not None and max_score_for_address(addr_permits) < min_score:
            skipped += 1
            continue
        record = _build_summary_record(address, addr_permits, properties)
        filename = sanitize_filename(address) + ".json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(record, f, indent=2)
        files_written.append((address, filepath))

    print(f"\nWrote {len(files_written)} summary files to {output_dir}/")
    if skipped:
        print(f"  Skipped {skipped} addresses below score threshold")
    return files_written


LLM_PROMPT = (
    "Assess the likelihood that this property is being prepared for sale based on building permits and assessment data.\n\n"
    "CRITICAL INDICATORS FOR HIGH LIKELIHOOD:\n"
    "1. High-end 'prep-for-sale' renovations: Simultaneous full-scale updates to Kitchen AND multiple Bathrooms.\n"
    "2. Non-owner occupied: If the permit lists owner_occupied as False, it is much more likely to be a project/flip.\n"
    "3. Significant 'Gut' or 'Whole House' work even with long-term ownership (8+ years).\n\n"
    "CRITICAL INDICATORS FOR LOW LIKELIHOOD:\n"
    "1. Maintenance work: Roof, windows (unless part of a larger project), siding, or HVAC only.\n"
    "2. Minor updates: A single bathroom or small kitchen refresh by a long-term owner-occupant.\n\n"
    "Respond with ONLY valid JSON in this exact format:\n"
    '{"likelihood": "low|medium|high", "reasoning": "one sentence explanation"}'
)


def _parse_llm_response(raw):
    """Parse LLM JSON response, returning a dict with likelihood and reasoning.
    
    Robustly handles thinking or conversational filler by searching for the 
    first '{' and last '}' if the initial parse fails.
    """
    text = raw.strip()
    
    # Strip <thought> tags if present
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    
    # Strip "Thinking... done thinking" style blocks
    if "done thinking" in text.lower():
        parts = re.split(r"done thinking", text, flags=re.IGNORECASE)
        if len(parts) > 1:
            text = parts[-1].strip()
    
    # Strip "Thinking..." at the start
    if text.lower().startswith("thinking"):
        start_json = text.find("{")
        if start_json != -1:
            if "```" in text:
                pass 
            else:
                text = text[start_json:].strip()

    # Strip markdown code fences
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()

    # Try direct parse
    try:
        parsed = json.loads(text)
        return {
            "likelihood": str(parsed.get("likelihood", "unknown")).lower(),
            "reasoning": str(parsed.get("reasoning", "")),
        }
    except (json.JSONDecodeError, TypeError):
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                inner_text = text[start : end + 1]
                parsed = json.loads(inner_text)
                return {
                    "likelihood": str(parsed.get("likelihood", "unknown")).lower(),
                    "reasoning": str(parsed.get("reasoning", "")),
                }
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback for failed parse
    likelihood = "unknown"
    lower_text = text.lower()
    if '"likelihood": "high"' in lower_text or '"likelihood":"high"' in lower_text: likelihood = "high"
    elif '"likelihood": "medium"' in lower_text or '"likelihood":"medium"' in lower_text: likelihood = "medium"
    elif '"likelihood": "low"' in lower_text or '"likelihood":"low"' in lower_text: likelihood = "low"
    elif "high" in lower_text: likelihood = "high"
    elif "medium" in lower_text: likelihood = "medium"
    elif "low" in lower_text: likelihood = "low"
    
    reason_match = re.search(r'"reasoning":\s*"(.*?)"', text, re.DOTALL | re.IGNORECASE)
    if reason_match:
        reasoning = reason_match.group(1)
    else:
        reasoning = text
        
    if len(reasoning) > 200:
        reasoning = reasoning[:197] + "..."
        
    return {"likelihood": likelihood, "reasoning": reasoning}


def _run_local_ollama(prompt, model="glm-4.7-flash:latest"):
    """Run prompt via claude CLI pointed at local ollama server."""
    env = os.environ.copy()
    env["ANTHROPIC_AUTH_TOKEN"] = "ollama"
    env["ANTHROPIC_BASE_URL"] = "http://localhost:11434"
    return subprocess.run(
        ["claude", "--model", model, "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


# Keys to strip from summary JSON before sending to LLM (save tokens, not needed for assessment)
_LLM_EXCLUDED_KEYS = {
    "google_maps_url",
    "zillow_url",
    "google_search_url",
    "lat",
    "lng",
    "completion_ratio",
    "completed_permits",
}


def _analyze_one(address, filepath, llm_type="ollama"):
    """Run LLM on a single summary file. Returns (address, parsed_assessment)."""
    try:
        with open(filepath) as f:
            data = json.load(f)
        data = {k: v for k, v in data.items() if k not in _LLM_EXCLUDED_KEYS}
        content = json.dumps(data, separators=(',', ':'))

        prompt = f"{LLM_PROMPT}\n\nDATA:\n{content}"

        primary_error = None
        result = None
        try:
            if llm_type == "sonnet":
                result = subprocess.run(
                    ["claude", "-p", prompt],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            elif llm_type == "gemini":
                result = subprocess.run(
                    ["gemini", "-m", "flash", "-p", prompt],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            elif llm_type == "ollama-qwen-35":
                result = _run_local_ollama(prompt, model="qwen3.5:9b")
            else:
                result = _run_local_ollama(prompt)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            primary_error = str(e)

        if result is not None and result.returncode == 0:
            return address, _parse_llm_response(result.stdout.strip())

        # Primary failed — fall back to local ollama (skip if already using it)
        if llm_type not in ("ollama", "ollama-qwen-35"):
            error_detail = primary_error or (result.stderr.strip() if result else "unknown error")
            print(f"    ⚠ {llm_type} failed ({error_detail[:80]}), falling back to local ollama...")
            try:
                fallback = _run_local_ollama(prompt)
                if fallback.returncode == 0:
                    return address, _parse_llm_response(fallback.stdout.strip())
                return address, {"likelihood": "error", "reasoning": fallback.stderr.strip()}
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                return address, {"likelihood": "error", "reasoning": f"ollama fallback failed: {e}"}

        error_msg = primary_error or (result.stderr.strip() if result else "unknown error")
        return address, {"likelihood": "error", "reasoning": error_msg}
    except Exception as e:
        return address, {"likelihood": "error", "reasoning": str(e)}


def _write_assessment(summary_path, assessment, output_dir):
    """Read a summary JSON, add llm_assessment, write to output dir."""
    os.makedirs(output_dir, exist_ok=True)
    with open(summary_path) as f:
        record = json.load(f)
    record["llm_assessment"] = assessment
    out_path = os.path.join(output_dir, os.path.basename(summary_path))
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)
    return out_path


def run_llm_analysis(summary_files, permits, llm_type="ollama", max_workers=10, output_dir="summaries/llm_assessment_summary"):
    """Run LLM analysis on each summary file with parallel execution."""
    results = []
    total = len(summary_files)
    print(f"  Running LLM ({llm_type}) analysis on {total} addresses ({max_workers} parallel)...")
    print(f"  Writing assessments to {output_dir}/")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_one, addr, path, llm_type=llm_type): (addr, path)
            for addr, path in summary_files
        }
        for i, future in enumerate(as_completed(futures), 1):
            address, assessment = future.result()
            _, summary_path = futures[future]
            _write_assessment(summary_path, assessment, output_dir)
            results.append((address, assessment))
            print(f"  [{i}/{total}] {address}")
            print(f"    → {assessment['likelihood']}: {assessment['reasoning'][:100]}")

    addr_order = {addr: idx for idx, (addr, _) in enumerate(summary_files)}
    results.sort(key=lambda r: addr_order.get(r[0], 0))
    return results


def print_llm_report(results):
    """Print a consolidated LLM analysis report grouped by likelihood."""
    if not results:
        return

    by_likelihood = {}
    for address, assessment in results:
        level = assessment.get("likelihood", "unknown")
        by_likelihood.setdefault(level, []).append((address, assessment))

    print("\n" + "=" * 70)
    print("LLM LIKELIHOOD ASSESSMENT")
    print("=" * 70)
    for level in ["high", "medium", "low", "unknown", "error"]:
        entries = by_likelihood.get(level, [])
        if not entries:
            continue
        print(f"\n  [{level.upper()}] ({len(entries)})")
        for address, assessment in entries:
            print(f"    {address}")
            print(f"      {assessment.get('reasoning', '')}")
    print()

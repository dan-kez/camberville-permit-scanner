"""Group permits by address and generate per-address summaries for LLM analysis."""

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


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


def _build_summary_record(address, permits):
    """Build a structured JSON record for one address."""
    p0 = permits[0]
    total_cost = sum(p.get("cost", 0) for p in permits)
    return {
        "address": address,
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
                "score": p.get("score", 0),
                "score_reasons": p.get("score_reasons", ""),
            }
            for p in permits
        ],
    }


def max_score_for_address(permits):
    """Return the highest significance score among a group of permits."""
    return max((p.get("score", 0) for p in permits), default=0)


def write_summaries(permits, output_dir="summaries", min_score=None):
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
        record = _build_summary_record(address, addr_permits)
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
    "Given these building permits for a single-family home, assess the likelihood "
    "that this property is being renovated for sale. Consider: scope of work, "
    "cost, number of permits, whether work suggests cosmetic flip vs owner renovation.\n\n"
    "Respond with ONLY valid JSON in this exact format, no other text:\n"
    '{"likelihood": "low|medium|high", "reasoning": "one sentence explanation"}'
)


def _parse_llm_response(raw):
    """Parse LLM JSON response, returning a dict with likelihood and reasoning."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        return {
            "likelihood": parsed.get("likelihood", "unknown"),
            "reasoning": parsed.get("reasoning", ""),
        }
    except (json.JSONDecodeError, TypeError):
        return {"likelihood": "unknown", "reasoning": raw}


def _analyze_one(address, filepath):
    """Run claude -p on a single summary file. Returns (address, parsed_assessment)."""
    try:
        with open(filepath) as f:
            result = subprocess.run(
                ["claude", "-p", "--model", "claude-sonnet-4-6", "--output-format", "text", LLM_PROMPT],
                stdin=f,
                capture_output=True,
                text=True,
                timeout=120,
            )
        if result.returncode == 0:
            return address, _parse_llm_response(result.stdout.strip())
        return address, {"likelihood": "error", "reasoning": result.stderr.strip()}
    except FileNotFoundError:
        return address, {"likelihood": "error", "reasoning": "claude CLI not found"}
    except subprocess.TimeoutExpired:
        return address, {"likelihood": "error", "reasoning": "timed out"}


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


def run_llm_analysis(summary_files, permits, max_workers=4, output_dir="summaries/llm_assessment_summary"):
    """Run claude -p on each summary file with parallel execution.

    Results are written to output_dir as copies of the summary JSON with an
    added llm_assessment field. Original summary files are not modified.
    """
    results = []
    total = len(summary_files)
    print(f"  Running LLM analysis on {total} addresses ({max_workers} parallel)...")
    print(f"  Writing assessments to {output_dir}/")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_one, addr, path): (addr, path)
            for addr, path in summary_files
        }
        for i, future in enumerate(as_completed(futures), 1):
            address, assessment = future.result()
            _, summary_path = futures[future]
            _write_assessment(summary_path, assessment, output_dir)
            results.append((address, assessment))
            print(f"  [{i}/{total}] {address}")
            print(f"    → {assessment['likelihood']}: {assessment['reasoning'][:100]}")

    # Sort results to match input order
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

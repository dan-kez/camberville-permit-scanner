#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""Permit Scanner CLI: find upcoming home listings from building permit data."""

import argparse

from analyze import print_llm_report, run_llm_analysis, write_summaries
from config import DEFAULT_MIN_SCORE, DEFAULT_RADIUS_MI
from fetch import fetch_all
from filters import apply_filters
from report import export_csv, print_table


def build_parser():
    parser = argparse.ArgumentParser(
        description="Scan building permits near target squares to find homes likely coming to market."
    )
    parser.add_argument(
        "--radius", type=float, default=DEFAULT_RADIUS_MI,
        help=f"Search radius in miles (default: {DEFAULT_RADIUS_MI})",
    )
    parser.add_argument(
        "--min-score", type=int, default=DEFAULT_MIN_SCORE,
        help=f"Minimum significance score (default: {DEFAULT_MIN_SCORE})",
    )
    parser.add_argument(
        "--csv", metavar="FILE",
        help="Export results to CSV file",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Show all nearby permits (skip residential and significance filters)",
    )
    parser.add_argument(
        "--completing", action="store_true",
        help="Only show addresses where at least one permit is Complete/Closed",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Bypass cache and fetch fresh data from APIs",
    )
    parser.add_argument(
        "--analyze", action="store_true",
        help="Write per-address summary files to summaries/ directory",
    )
    parser.add_argument(
        "--analyze-llm", nargs="?", type=int, const=0, default=None, metavar="MIN_SCORE",
        help="Run claude -p on each summary for likelihood assessment (optionally only for addresses with score ≥ MIN_SCORE)",
    )
    return parser


def main():
    parser = build_parser()

    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()

    use_cache = not args.no_cache
    print("Fetching permits..." if not use_cache else "Loading permits (use --no-cache to refresh)...")
    permits = fetch_all(use_cache=use_cache)
    print(f"Total: {len(permits)}\n")

    print("Filtering...")
    permits = apply_filters(
        permits,
        radius_mi=args.radius,
        min_score=args.min_score,
        skip_residential=args.all,
        skip_significance=args.all,
        only_completing=args.completing,
    )

    print_table(permits)

    if args.csv:
        export_csv(permits, args.csv)

    if args.analyze or args.analyze_llm is not None:
        llm_min_score = args.analyze_llm if args.analyze_llm is not None else None
        summary_files = write_summaries(permits, min_score=llm_min_score)
        if args.analyze_llm is not None and summary_files:
            results = run_llm_analysis(summary_files, permits)
            print_llm_report(results)


if __name__ == "__main__":
    main()

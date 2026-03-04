"""Output: terminal table and CSV export."""

import csv

from tabulate import tabulate


def truncate(text, maxlen=60):
    if len(text) <= maxlen:
        return text
    return text[:maxlen - 3] + "..."


def format_cost(cost):
    if cost <= 0:
        return "—"
    return f"${cost:,.0f}"


def print_table(permits):
    """Print a formatted table to the terminal."""
    if not permits:
        print("\nNo permits matched your filters.")
        return

    headers = ["Address", "Square", "Dist", "Description", "Cost", "Contractor", "Date", "Status", "Score"]
    rows = []
    for p in permits:
        rows.append([
            p.get("address", ""),
            p.get("nearest_square", ""),
            f"{p.get('distance_mi', 0):.2f} mi",
            truncate(p.get("description", ""), 35),
            format_cost(p.get("cost", 0)),
            truncate(p.get("contractor", ""), 25),
            p.get("date", ""),
            p.get("status", ""),
            p.get("score", 0),
        ])

    print(f"\n{len(permits)} permits found:\n")
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print()


def export_csv(permits, filename):
    """Export permits to CSV with full details."""
    if not permits:
        print(f"No permits to export.")
        return

    fieldnames = [
        "address", "nearest_square", "distance_mi", "description", "cost",
        "property_use", "dwelling_count", "contractor", "status", "date",
        "source", "score", "score_reasons",
    ]
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(permits)

    print(f"Exported {len(permits)} permits to {filename}")

# Permit Scanner

Find single-family homes likely coming to market by scanning public building permit data from Cambridge and Somerville, MA. Significant renovations (gut rehabs, additions, new construction) often signal a home will be listed for sale — this tool helps you spot them early and reach out to the contractor.

## How it works

1. Pulls permit data from city open data portals (Socrata API)
2. Filters by proximity to Davis, Porter, Central, Inman, and Union squares
3. Keeps only single-family residential permits
4. Scores each permit by significance (cost, keywords, permit type)
5. Outputs an actionable report with contractor info

## Setup

```bash
uv sync
```

### Tab completion (optional)

```bash
uv add argcomplete
# For bash
eval "$(register-python-argcomplete uv run scanner.py)"

# For zsh — add to ~/.zshrc
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete uv run scanner.py)"
```

## Usage

```bash
# Default: significant single-family permits within 0.75 mi of target squares
uv run scanner.py

# Wider search radius
uv run scanner.py --radius 1.0

# Lower significance threshold
uv run scanner.py --min-score 0

# Skip all filters, show everything nearby
uv run scanner.py --all

# Export to CSV
uv run scanner.py --csv results.csv

# Force fresh API fetch (default uses cached data)
uv run scanner.py --no-cache

# Write per-address summaries for LLM analysis
uv run scanner.py --analyze

# Auto-run claude -p on each summary (4 parallel, uses Sonnet)
uv run scanner.py --analyze-llm

# Only analyze addresses with score ≥ 3
uv run scanner.py --analyze-llm 3
```

## Caching

API responses are cached in `.cache/` as raw JSON. Subsequent runs use cached data by default so you don't hammer the city APIs. Use `--no-cache` to pull fresh data.

## Data sources

| Source | City | What it covers |
|--------|------|----------------|
| [Cambridge Alteration Permits](https://data.cambridgema.gov/resource/qu2z-8suj.json) | Cambridge | Renovations, additions, alterations to existing buildings |
| [Cambridge New Construction](https://data.cambridgema.gov/resource/9qm7-wbdc.json) | Cambridge | New building construction |
| [Somerville Permits](https://data.somervillema.gov/resource/nneb-s3f7.json) | Somerville | All building permits |

## Significance scoring

Permits are scored to surface the most interesting results:

| Signal | Score | Notes |
|--------|-------|-------|
| Cost ≥ $200K | +3 | Cambridge only (Somerville amount is the permit fee) |
| Cost ≥ $25K | +1 | Cambridge only |
| Significant keyword (gut, renovation, addition, etc.) | +2 | |
| Minor work keyword (smoke detector, furnace, etc.) | -3 | |
| New construction permit | +3 | |

Default display threshold is score ≥ 1.

## LLM analysis

The `--analyze` flag writes one summary file per address to `summaries/`. Each file is designed to be piped to an LLM:

```bash
claude -p "Given these building permits for a single-family home, assess the
likelihood (low/medium/high) that this property is being renovated for sale.
Consider: scope of work, cost, number of permits, whether work suggests
cosmetic flip vs owner renovation. Be concise." < summaries/123-main-st.txt
```

Or use `--analyze-llm` to do this automatically for all addresses (runs 4 in parallel using Sonnet). Pass a score threshold to limit which addresses get analyzed:

```bash
uv run scanner.py --analyze-llm       # all addresses
uv run scanner.py --analyze-llm 3     # only addresses with score ≥ 3
```

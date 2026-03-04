# Permit Scanner

Scan building permits near target squares to find homes likely coming to market.

## Usage

```bash
# Basic scan (Porter square, 0.75 mi radius)
uv run scanner.py

# Customize search
uv run scanner.py --radius 1.0 --min-score 3

# Export to CSV
uv run scanner.py --csv results.csv

# Run LLM analysis on summaries
# Default: uses opencode (ollama) locally
uv run scanner.py --analyze-llm

# Use Claude (Sonnet 3.5) for analysis
uv run scanner.py --analyze-llm --llm sonnet

# Filter LLM analysis by score
uv run scanner.py --analyze-llm 5
```

## Features

- **Proximity Search**: Finds permits near Davis, Porter, and Central squares.
- **Significance Scoring**: Filters permits based on cost and keywords (e.g., "addition", "renovation").
- **LLM Assessment**: Evaluates the likelihood of a property being flipped vs. owner-occupied.
- **Property Enrichment**: Fetches property details (bedrooms, baths, sale history) from city assessment databases to inform the LLM.
- **Google Maps Integration**: Generates direct links for quick property lookup.

## Configuration

- `config.py`: Target squares, scoring keywords, and API endpoints.
- `.cache/`: Raw API responses are cached locally. Use `--no-cache` to refresh.
- `summaries/`: JSON summary files for each significant address.
- `summaries/llm_assessment_summary/`: Enriched JSON files with LLM assessments.

## LLM Backends

1.  **opencode** (Default): Uses `ollama` with `glm-4.7-flash:latest` model locally. Requires `ollama` to be installed and running.
2.  **sonnet**: Uses `claude -p .` CLI to run analysis via Anthropic's Claude 3.5 Sonnet. Requires `claude` CLI and active session.

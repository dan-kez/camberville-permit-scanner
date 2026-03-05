#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="summaries/llm_assessment_summary"
OUTPUT="docs/data.json"

mkdir -p docs

jq -s '.' "$INPUT_DIR"/*.json > "$OUTPUT"

count=$(jq 'length' "$OUTPUT")
echo "Wrote $count records to $OUTPUT"

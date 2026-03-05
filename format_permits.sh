#!/bin/bash

# Script to format and sort permit data by chance and score

find summaries/llm_assessment_summary -name "*.json" -exec sh -c 'fp=$(realpath "$1"); jq -c "{address: .address, url:.google_search_url, fp: \"$fp\", score:(.permits | map(.score) | add), chance:.llm_assessment.likelihood, reason:.llm_assessment.reasoning}" "$1"' _ {} \; > /tmp/entries.json

python3 << 'EOF'
import json

with open('/tmp/entries.json', 'r') as f:
    entries = [json.loads(line) for line in f]

def sort_key(entry):
    chance_score = {"high": 3, "medium": 2, "low": 1}.get(entry["chance"], 1)
    return (-chance_score, -entry["score"])

entries.sort(key=sort_key)

for entry in entries:
    print(f"Address: {entry['address']}")
    print(f"Chance: {entry['chance']} | Score: {entry['score']} | {entry['url']}")
    print(f"file://{entry['fp']}")
    print(entry['reason'])
    print("---")
    print()
EOF
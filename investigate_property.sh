#!/bin/bash

# Check if file path is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <relative_file_path>"
    exit 1
fi

FILE_PATH=$1

# Check if file exists
if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File '$FILE_PATH' not found."
    exit 1
fi

# Prepare the prompt
PROMPT_HEADER="Instruction: Act as a real estate research specialist. I will provide the content of a permit assessment JSON. Your goal is to identify the decision-maker for this property and determine the best strategy to find out if it is hitting the market soon.

Task Workflow:
1. Analyze Permits: Read the JSON and summarize the 'narrative' of the work (e.g., is it a high-end gut renovation, a 2-to-1 conversion, or just maintenance?).
2. Identify the Project Lead: Extract the primary Building/General Contractor and check their online portfolio/social media (Instagram/Facebook) for recent project updates or 'sneak peeks' of this specific address.
3. Identify the Owner: Search the Somerville Assessor's database and Secretary of State records for the current owner. If it is an LLC, find the Manager or Registered Agent's name.
4. Check Market Status: Verify if the property has a 'Coming Soon' status on Zillow/Redfin or if it was recently transferred for a nominal amount (e.g., \$1, \$10, \$100), which indicates a developer-led project.
5. Strategy Recommendation: Based on the renovation timeline and the type of owner, suggest the best contact method (e.g., direct mail to the manager, a call to the contractor, or reaching out to a specific local realtor)."

FILE_CONTENT=$(cat "$FILE_PATH")

# Combine everything into one string
FULL_PROMPT="$PROMPT_HEADER

Permit Assessment JSON:
$FILE_CONTENT"

# Call gemini directly with YOLO mode to allow searches and commands
gemini --approval-mode=yolo "$FULL_PROMPT"

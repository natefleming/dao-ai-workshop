#!/usr/bin/env bash
#
# Create (or find) an MLflow experiment for the dao-ai workshop.
#
# Idempotent: running twice returns the same experiment_id.
#
# Usage:
#   bash setup/create_experiment.sh
#
# Requires:
#   - databricks CLI installed and authenticated
#   - $DATABRICKS_CONFIG_PROFILE set (defaults to "DEFAULT")

set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"

echo "Using Databricks profile: $PROFILE"

USER_NAME="$(databricks current-user me --profile "$PROFILE" --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)["userName"])')"
if [ -z "$USER_NAME" ]; then
  echo "ERROR: could not resolve current user from profile $PROFILE" >&2
  exit 1
fi

EXPERIMENT_PATH="/Users/${USER_NAME}/dao-ai-workshop"
echo "Experiment path: $EXPERIMENT_PATH"

# Check if it already exists.
EXISTING_ID="$(
  databricks experiments get-by-name "$EXPERIMENT_PATH" --profile "$PROFILE" --output json 2>/dev/null \
    | python3 -c 'import json,sys
try:
  d = json.load(sys.stdin)
  exp = d.get("experiment") or {}
  print(exp.get("experiment_id",""))
except Exception:
  print("")'
)"

if [ -n "$EXISTING_ID" ]; then
  echo "Experiment already exists: $EXISTING_ID"
  EXP_ID="$EXISTING_ID"
else
  echo "Creating new experiment..."
  EXP_ID="$(
    databricks experiments create-experiment "$EXPERIMENT_PATH" --profile "$PROFILE" --output json \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["experiment_id"])'
  )"
  echo "Created: $EXP_ID"
fi

echo ""
echo "Done. Next step:"
echo "  Add the following to your .env:"
echo ""
echo "    MLFLOW_EXPERIMENT_ID=$EXP_ID"
echo ""
echo "(Most chapters auto-create their own sub-experiment under"
echo " $EXPERIMENT_PATH/<chapter>, so the root one above is optional"
echo " unless a chapter README tells you to set it explicitly.)"

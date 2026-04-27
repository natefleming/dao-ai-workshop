#!/usr/bin/env bash
#
# Create a service principal + OAuth client secret for the dao-ai
# workshop. Only needed for chapters that deploy agents as a service
# principal (rather than running as the notebook user). Safe to skip
# for the core teaching flow.
#
# Idempotent: if an SP with the same display name already exists, we
# reuse it. Secrets are always rotated on each run (Databricks doesn't
# expose existing secret values).
#
# Usage:
#   bash setup/create_service_principal.sh
#
# Requires:
#   - databricks CLI installed and authenticated
#   - $DATABRICKS_CONFIG_PROFILE set (defaults to "DEFAULT")
#   - You have permission to create service principals in the workspace

set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
SP_NAME="${DAO_AI_WORKSHOP_SP_NAME:-dao-ai-workshop-sp}"

echo "Using Databricks profile: $PROFILE"
echo "Service principal name:   $SP_NAME"

# Look for an existing SP by display name.
SP_JSON="$(
  databricks service-principals list --profile "$PROFILE" --output json \
    | python3 -c 'import json,sys,os
name = os.environ["SP_NAME"]
d = json.load(sys.stdin)
for sp in d if isinstance(d,list) else d.get("service_principals",[]):
  if sp.get("display_name") == name:
    print(json.dumps(sp)); break' SP_NAME="$SP_NAME"
)"

if [ -n "$SP_JSON" ]; then
  SP_APP_ID="$(echo "$SP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["application_id"])')"
  SP_ID="$(echo "$SP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  echo "Service principal already exists: application_id=$SP_APP_ID"
else
  echo "Creating service principal..."
  SP_RESP="$(databricks service-principals create --display-name "$SP_NAME" --profile "$PROFILE" --output json)"
  SP_APP_ID="$(echo "$SP_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["application_id"])')"
  SP_ID="$(echo "$SP_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  echo "Created: application_id=$SP_APP_ID"
fi

echo ""
echo "Creating a fresh OAuth client secret..."
SECRET_RESP="$(
  databricks service-principal-secrets-proxy create-service-principal-secret "$SP_ID" \
    --profile "$PROFILE" --output json 2>/dev/null || echo ""
)"

if [ -z "$SECRET_RESP" ]; then
  echo "WARNING: could not auto-generate a client secret via CLI."
  echo "  Generate one manually in the UI:"
  echo "    Settings -> Identity and access -> Service principals ->"
  echo "    $SP_NAME -> OAuth secrets -> Generate"
  echo "  Client ID: $SP_APP_ID"
  exit 0
fi

CLIENT_SECRET="$(echo "$SECRET_RESP" | python3 -c 'import json,sys
d = json.load(sys.stdin)
print(d.get("secret") or d.get("client_secret",""))')"

echo ""
echo "Done. Next step:"
echo "  Add the following to your .env (never commit):"
echo ""
echo "    DAO_AI_WORKSHOP_CLIENT_ID=$SP_APP_ID"
echo "    DAO_AI_WORKSHOP_CLIENT_SECRET=$CLIENT_SECRET"
echo ""
echo "Grant the SP the permissions each chapter needs:"
echo "  - Chapter 04 (MCP):  EXECUTE on your workshop catalog's functions"
echo "  - Chapter 07 (Mem):  USE CATALOG + SELECT on the Lakebase schema"

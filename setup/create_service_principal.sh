#!/usr/bin/env bash
#
# End-to-end setup for the dao-ai-workshop service principal:
#
#   1. Creates a service principal (idempotent: reuses if name matches).
#   2. Generates a fresh OAuth client secret on the SP.
#   3. Creates a Databricks secret scope (idempotent).
#   4. Stores the client_id and client_secret in the scope.
#   5. Grants the calling user MANAGE on the scope so notebook runs can
#      read the secrets via dbutils.secrets.
#
# After this runs, Lab 7's `support_assistant.yaml` (which references
# `${var.sp_secret_scope}` + `${var.sp_client_id_secret}` /
# `${var.sp_client_secret_secret}`) resolves automatically -- no .env
# values needed.
#
# Usage:
#   bash setup/create_service_principal.sh
#
# Configurable via env:
#   DATABRICKS_CONFIG_PROFILE  Profile name (default: DEFAULT)
#   DAO_AI_WORKSHOP_SP_NAME    SP display name (default: dao-ai-workshop-sp)
#   DAO_AI_WORKSHOP_SCOPE      Secret scope name (default: dao_ai_workshop)
#   DAO_AI_WORKSHOP_CID_KEY    Secret key for client_id   (default: DAO_AI_SP_CLIENT_ID)
#   DAO_AI_WORKSHOP_CSECRET_KEY  Secret key for client_secret (default: DAO_AI_SP_CLIENT_SECRET)
#
# Requires:
#   - databricks CLI installed and authenticated
#   - permission to create service principals + secret scopes in the workspace

set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
SP_NAME="${DAO_AI_WORKSHOP_SP_NAME:-dao-ai-workshop-sp}"
SCOPE_NAME="${DAO_AI_WORKSHOP_SCOPE:-dao_ai_workshop}"
CID_KEY="${DAO_AI_WORKSHOP_CID_KEY:-DAO_AI_SP_CLIENT_ID}"
CSECRET_KEY="${DAO_AI_WORKSHOP_CSECRET_KEY:-DAO_AI_SP_CLIENT_SECRET}"

echo "Profile:      $PROFILE"
echo "SP name:      $SP_NAME"
echo "Secret scope: $SCOPE_NAME"
echo "  -> $CID_KEY,  $CSECRET_KEY"
echo

run() { databricks --profile "$PROFILE" "$@"; }

# --- 1. Look up or create the SP --------------------------------------------
# Workspace-wide SCIM list can time out on large workspaces, so try create
# first and parse the existing-record id from the conflict response.

SP_CREATE_OUT="$(mktemp)"
trap 'rm -f "$SP_CREATE_OUT" "$SP_SECRET_OUT"' EXIT

if run service-principals create --display-name "$SP_NAME" --output json \
        > "$SP_CREATE_OUT" 2>&1; then
  SP_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' < "$SP_CREATE_OUT")"
  SP_APP_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["applicationId"])' < "$SP_CREATE_OUT")"
  echo "Created SP: id=$SP_ID  application_id=$SP_APP_ID"
else
  if grep -qiE 'conflict|already exists|duplicate' "$SP_CREATE_OUT"; then
    echo "SP already exists; looking it up..."
    SP_LIST_OUT="$(mktemp)"
    SP_NAME="$SP_NAME" run service-principals list --output json \
      > "$SP_LIST_OUT" 2>&1 || true
    SP_ID="$(python3 -c '
import json, os, sys
name = os.environ["SP_NAME"]
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
sps = d if isinstance(d, list) else d.get("Resources") or d.get("service_principals", [])
for sp in sps:
    if (sp.get("displayName") or sp.get("display_name")) == name:
        print(sp.get("id", ""))
        break
' "$SP_LIST_OUT")"
    SP_APP_ID="$(python3 -c '
import json, os, sys
name = os.environ["SP_NAME"]
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
sps = d if isinstance(d, list) else d.get("Resources") or d.get("service_principals", [])
for sp in sps:
    if (sp.get("displayName") or sp.get("display_name")) == name:
        print(sp.get("applicationId") or sp.get("application_id") or "")
        break
' "$SP_LIST_OUT")"
    rm -f "$SP_LIST_OUT"
    if [ -z "${SP_ID:-}" ]; then
      echo "ERROR: SP exists but couldn't locate its id (workspace listing may have timed out)."
      echo "       Look up the SP id manually in Settings -> Identity and access -> Service principals,"
      echo "       then re-run with DAO_AI_WORKSHOP_SP_ID=<id> to skip the lookup step."
      exit 1
    fi
    echo "Found existing SP: id=$SP_ID  application_id=$SP_APP_ID"
  else
    cat "$SP_CREATE_OUT"
    exit 1
  fi
fi

# --- 2. Generate a fresh OAuth client secret --------------------------------

SP_SECRET_OUT="$(mktemp)"
echo
echo "Generating fresh OAuth client secret on SP $SP_ID..."
run service-principal-secrets-proxy create "$SP_ID" --output json \
  > "$SP_SECRET_OUT"

CLIENT_SECRET="$(python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("secret") or d.get("client_secret", ""))
' < "$SP_SECRET_OUT")"

if [ -z "$CLIENT_SECRET" ]; then
  echo "ERROR: SP secret response did not include a secret value."
  cat "$SP_SECRET_OUT"
  exit 1
fi

# --- 3. Create the secret scope (idempotent) --------------------------------

echo
echo "Ensuring secret scope '$SCOPE_NAME' exists..."
SCOPE_CREATE_OUT="$(mktemp)"
if run secrets create-scope "$SCOPE_NAME" > "$SCOPE_CREATE_OUT" 2>&1; then
  echo "  Created scope $SCOPE_NAME"
else
  if grep -qiE 'already exists|RESOURCE_ALREADY_EXISTS' "$SCOPE_CREATE_OUT"; then
    echo "  Scope $SCOPE_NAME already exists; reusing."
  else
    cat "$SCOPE_CREATE_OUT"
    rm -f "$SCOPE_CREATE_OUT"
    exit 1
  fi
fi
rm -f "$SCOPE_CREATE_OUT"

# --- 4. Store the credentials -----------------------------------------------

echo
echo "Storing $CID_KEY (application_id)..."
run secrets put-secret "$SCOPE_NAME" "$CID_KEY" --string-value "$SP_APP_ID" >/dev/null
echo "Storing $CSECRET_KEY (rotated this run)..."
run secrets put-secret "$SCOPE_NAME" "$CSECRET_KEY" --string-value "$CLIENT_SECRET" >/dev/null

# --- 5. Grant the calling user MANAGE on the scope --------------------------

USER_NAME="$(run current-user me --output json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("userName") or d.get("user_name") or "")')"
if [ -n "$USER_NAME" ]; then
  echo
  echo "Granting MANAGE on scope $SCOPE_NAME to $USER_NAME..."
  run secrets put-acl "$SCOPE_NAME" "$USER_NAME" MANAGE >/dev/null || true
fi

# --- Summary ----------------------------------------------------------------

echo
echo "============================================================"
echo "Setup complete."
echo "  SP id:           $SP_ID"
echo "  application_id:  $SP_APP_ID  (-> ${SCOPE_NAME}/${CID_KEY})"
echo "  client_secret:   stored in ${SCOPE_NAME}/${CSECRET_KEY}"
echo
echo "Next: grant the SP whatever each lab needs, e.g."
echo "  Lab 4 (MCP):  EXECUTE on your workshop catalog's functions"
echo "  Lab 7 (Mem):  databricks_superuser membership on the Lakebase"
echo "                project (run database.create() in the notebook,"
echo "                or grant via Settings -> Lakebase project -> roles)."
echo "============================================================"

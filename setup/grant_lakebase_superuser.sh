#!/usr/bin/env bash
#
# Grant the workshop service principal DATABRICKS_SUPERUSER on a Lakebase
# Autoscaling project. Without this grant, the deployed app's SP can
# CONNECT to the Lakebase project (via the postgres app-resource binding)
# but lacks schema-level CREATE on `public` -- so langgraph's checkpoint
# migrations fail with `permission denied for schema public`.
#
# The script creates a postgres role under the project's default branch
# (or the branch you specify), bound to the SP's client_id, with
# DATABRICKS_SUPERUSER membership. This is the same operation that
# `dao-ai`'s `DatabaseModel.create()` performs in Lab 7, but exposed
# as a standalone setup step so multiple labs can share one Lakebase
# project without each notebook doing the grant.
#
# Idempotent: if the role already exists, it leaves it alone.
#
# Usage:
#   bash setup/grant_lakebase_superuser.sh [project] [branch] [client_id]
#
# All three args are optional:
#   project    -- Lakebase autoscaling project name
#                 (default: $DAO_AI_WORKSHOP_LAKEBASE_PROJECT, then
#                 retail-consumer-goods)
#   branch     -- branch ID under the project (default: auto-resolved
#                 to the project's default branch)
#   client_id  -- application_id of the SP to grant on
#                 (default: read from the dao_ai_workshop secret scope
#                 key DAO_AI_SP_CLIENT_ID, populated by
#                 create_service_principal.sh)
#
# Configurable via env:
#   DATABRICKS_CONFIG_PROFILE              CLI profile (default: DEFAULT)
#   DAO_AI_WORKSHOP_LAKEBASE_PROJECT       Lakebase project name
#   DAO_AI_WORKSHOP_SCOPE                  Secret scope holding the SP
#                                          creds (default: dao_ai_workshop)
#   DAO_AI_WORKSHOP_CID_KEY                Key for client_id in the scope
#                                          (default: DAO_AI_SP_CLIENT_ID)

set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
PROJECT="${1:-${DAO_AI_WORKSHOP_LAKEBASE_PROJECT:-retail-consumer-goods}}"
BRANCH_ARG="${2:-}"
CLIENT_ID_ARG="${3:-}"
SCOPE_NAME="${DAO_AI_WORKSHOP_SCOPE:-dao_ai_workshop}"
CID_KEY="${DAO_AI_WORKSHOP_CID_KEY:-DAO_AI_SP_CLIENT_ID}"

echo "Profile:           $PROFILE"
echo "Lakebase project:  $PROJECT"
echo "Branch:            ${BRANCH_ARG:-(auto-resolve default)}"
echo "Client ID source:  ${CLIENT_ID_ARG:+'<arg>'}${CLIENT_ID_ARG:-${SCOPE_NAME}/${CID_KEY}}"
echo

# --- Resolve the SP's client_id (an application_id) -------------------------

if [ -n "$CLIENT_ID_ARG" ]; then
  CLIENT_ID="$CLIENT_ID_ARG"
else
  CLIENT_ID="$(databricks --profile "$PROFILE" secrets get-secret \
                "$SCOPE_NAME" "$CID_KEY" --output json 2>/dev/null \
              | python3 -c '
import base64, json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
v = d.get("value", "")
# Databricks returns secrets base64-encoded
try:
    print(base64.b64decode(v).decode("utf-8").strip())
except Exception:
    print(v.strip())
' || true)"
fi

if [ -z "${CLIENT_ID:-}" ]; then
  echo "ERROR: client_id not provided and scope ${SCOPE_NAME}/${CID_KEY} could"
  echo "       not be read. Run setup/create_service_principal.sh first or"
  echo "       pass the SP application_id as the third argument."
  exit 1
fi

echo "Resolved client_id: $CLIENT_ID"
echo

# --- Run the grant via dao-ai's role provisioner ----------------------------
# We invoke the same code path Lab 7 uses (`DatabaseModel.create()`), so the
# setup matches what the notebook would do. This also keeps idempotency,
# error handling, and naming consistent with the framework.

PROFILE="$PROFILE" PROJECT="$PROJECT" BRANCH_ARG="$BRANCH_ARG" \
CLIENT_ID="$CLIENT_ID" \
uv run --quiet --with databricks-sdk python <<'PYTHON'
import os, re, sys
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceAlreadyExists
from databricks.sdk.service.postgres import (
    Role,
    RoleIdentityType,
    RoleMembershipRole,
    RoleRoleSpec,
)

profile = os.environ["PROFILE"]
project = os.environ["PROJECT"]
branch = os.environ.get("BRANCH_ARG") or None
client_id = os.environ["CLIENT_ID"]

w = WorkspaceClient(profile=profile)

# 1. Resolve the branch (default-flagged branch under the project) if the
#    user didn't pin one explicitly.
project_path = f"projects/{project}"
if branch:
    branch_path = f"{project_path}/branches/{branch}"
else:
    branches = list(w.postgres.list_branches(project_path))
    if not branches:
        print(f"ERROR: No branches found under {project_path}.")
        sys.exit(2)
    default = next((b for b in branches if b.status and b.status.default), branches[0])
    branch_path = default.name
    branch = branch_path.rsplit("/", 1)[-1]
print(f"Branch:            {branch}  ({branch_path})")

# 2. Sanitize the SP client_id into a valid postgres role_id.
#    role_id must match ^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$ — start with a
#    lowercase letter, lowercase/digit/hyphen body. dao-ai prefixes "sp-"
#    so we use the same convention for parity with framework runs.
sanitized = re.sub(r"[^a-z0-9-]", "-", client_id.lower()).strip("-")
role_id = f"sp-{sanitized}"[:63]
role_resource_name = f"{branch_path}/roles/{role_id}"
print(f"Role:              {role_id}")
print()

# 3. Idempotent create: skip if the role already exists.
try:
    w.postgres.get_role(name=role_resource_name)
    print(f"Role already exists at {role_resource_name}; nothing to do.")
    sys.exit(0)
except NotFound:
    pass
except Exception as e:
    print(f"WARNING: probe for existing role failed: {e}; proceeding to create.")

print(f"Creating role with DATABRICKS_SUPERUSER membership for SP {client_id}...")
try:
    w.postgres.create_role(
        parent=branch_path,
        role=Role(spec=RoleRoleSpec(
            postgres_role=client_id,
            identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
            membership_roles=[RoleMembershipRole.DATABRICKS_SUPERUSER],
        )),
        role_id=role_id,
    )
    print("Done.")
except ResourceAlreadyExists:
    print("Role was created concurrently; nothing to do.")
except Exception as e:
    msg = str(e).lower()
    if "already exists" in msg:
        print("Role already exists; nothing to do.")
    else:
        raise
PYTHON

echo
echo "============================================================"
echo "The SP can now CREATE schemas/tables/etc on Lakebase project"
echo "  $PROJECT"
echo "via the postgres app-resource binding. Lab 7 will start cleanly"
echo "without manually running database.create() in the notebook."
echo "============================================================"

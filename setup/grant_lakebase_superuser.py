# Databricks notebook source
# MAGIC %md
# MAGIC # Workshop setup -- grant the SP postgres `DATABRICKS_SUPERUSER` on a Lakebase project
# MAGIC
# MAGIC Run this **once per Lakebase project** before Lab 7 (memory) or
# MAGIC Lab 15 (long-running). Without this grant, the deployed app's SP
# MAGIC can connect to the project (via the `postgres` app-resource binding
# MAGIC dao-ai emits) but lacks schema-level CREATE on `public` -- so
# MAGIC langgraph's checkpoint migrations fail with
# MAGIC `permission denied for schema public`.
# MAGIC
# MAGIC ## What this notebook does (idempotent end-to-end)
# MAGIC
# MAGIC 1. Resolve the SP's `client_id` (from a widget or, if blank, from the
# MAGIC    secret scope populated by `create_service_principal.py`).
# MAGIC 2. Resolve the Lakebase project's default branch (or use the branch
# MAGIC    you pin in the widget).
# MAGIC 3. Sanitize the `client_id` into a valid postgres role_id
# MAGIC    (`sp-<lowercased-uuid>`).
# MAGIC 4. Probe for the role; create it with `DATABRICKS_SUPERUSER`
# MAGIC    membership only if missing.
# MAGIC
# MAGIC The role this notebook creates is the same one dao-ai's
# MAGIC `DatabaseModel.create()` would create from a lab notebook -- so if a
# MAGIC student already ran Lab 7's `database.create()` cell, this notebook
# MAGIC sees the role and exits clean.
# MAGIC
# MAGIC ## Sharing across students
# MAGIC
# MAGIC The role binds to the SP's `client_id`. Every student that uses
# MAGIC the same SP (the default scenario) shares the role. Run this
# MAGIC notebook once per Lakebase project; subsequent runs are no-ops.
# MAGIC
# MAGIC ## Required permissions for whoever runs this
# MAGIC
# MAGIC - Permission to create postgres roles on the Lakebase project's
# MAGIC   branch (typically Lakebase project owner or workspace admin).
# MAGIC - `READ` on the secret scope holding the SP credentials (default:
# MAGIC   `dao_ai_workshop`).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Configure widgets

# COMMAND ----------

dbutils.widgets.text("lakebase_project", "retail-consumer-goods", "1. Lakebase project name")
dbutils.widgets.text("branch", "", "2. Branch (blank = auto-resolve default)")
dbutils.widgets.text("client_id", "", "3. SP application_id (blank = read from secret scope)")
dbutils.widgets.text("scope_name", "dao_ai_workshop", "4. Secret scope (used when client_id is blank)")
dbutils.widgets.text("client_id_key", "DAO_AI_SP_CLIENT_ID", "5. Scope key for client_id")

lakebase_project: str = dbutils.widgets.get("lakebase_project").strip()
branch_arg: str = dbutils.widgets.get("branch").strip()
client_id_arg: str = dbutils.widgets.get("client_id").strip()
scope_name: str = dbutils.widgets.get("scope_name").strip()
client_id_key: str = dbutils.widgets.get("client_id_key").strip()

print(f"Lakebase project: {lakebase_project}")
print(f"Branch:           {branch_arg or '(auto-resolve default)'}")
print(f"Client ID source: {'<arg>' if client_id_arg else f'{scope_name}/{client_id_key}'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Resolve the SP's `client_id`

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()

if client_id_arg:
    client_id: str = client_id_arg
    print(f"Using provided client_id: {client_id}")
else:
    secret = w.secrets.get_secret(scope=scope_name, key=client_id_key)
    # The SDK returns the value base64-encoded.
    import base64
    client_id = base64.b64decode(secret.value).decode("utf-8").strip()
    print(f"Resolved client_id from {scope_name}/{client_id_key}: {client_id}")

if not client_id:
    raise ValueError(
        f"client_id is empty. Provide it via the `client_id` widget, or run "
        f"setup/create_service_principal.py first to populate {scope_name}/{client_id_key}."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Resolve the Lakebase branch

# COMMAND ----------

project_path: str = f"projects/{lakebase_project}"
if branch_arg:
    branch_path: str = f"{project_path}/branches/{branch_arg}"
    branch_id: str = branch_arg
    print(f"Branch (pinned): {branch_id}  ({branch_path})")
else:
    branches = list(w.postgres.list_branches(project_path))
    if not branches:
        raise ValueError(
            f"No branches found under {project_path}. Verify the project "
            "exists and you have access. Use `w.postgres.list_projects()` "
            "to enumerate visible projects."
        )
    default = next((b for b in branches if b.status and b.status.default), branches[0])
    branch_path = default.name
    branch_id = branch_path.rsplit("/", 1)[-1]
    print(f"Branch (resolved default): {branch_id}  ({branch_path})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Sanitize the client_id into a valid postgres role_id
# MAGIC
# MAGIC Lakebase's role_id constraint is `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`.
# MAGIC We prefix with `sp-` (matching dao-ai's `create_lakebase_autoscaling_role`
# MAGIC convention) so this notebook and the framework produce the same
# MAGIC role name from the same SP.

# COMMAND ----------

import re

sanitized: str = re.sub(r"[^a-z0-9-]", "-", client_id.lower()).strip("-")
role_id: str = f"sp-{sanitized}"[:63]
role_resource_name: str = f"{branch_path}/roles/{role_id}"
print(f"Role:       {role_id}")
print(f"Full path:  {role_resource_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Idempotent create
# MAGIC
# MAGIC Probe for the role first; only call `create_role` if the role is
# MAGIC genuinely missing. A second student running this notebook on a
# MAGIC project that already has the role exits cleanly with no changes.

# COMMAND ----------

from databricks.sdk.errors import NotFound, ResourceAlreadyExists
from databricks.sdk.service.postgres import (
    Role,
    RoleIdentityType,
    RoleMembershipRole,
    RoleRoleSpec,
)

try:
    existing_role = w.postgres.get_role(name=role_resource_name)
    print(f"Role already exists: {existing_role.name}")
    print("Nothing to do.")
except NotFound:
    print(f"Role missing; creating with DATABRICKS_SUPERUSER membership for SP {client_id}...")
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
        print("Role created.")
    except ResourceAlreadyExists:
        print("Role created concurrently by another caller; nothing to do.")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg:
            print("Role already exists; nothing to do.")
        else:
            raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Summary

# COMMAND ----------

print("=" * 60)
print("Lakebase superuser grant complete.")
print(f"  Project:     {lakebase_project}")
print(f"  Branch:      {branch_id}")
print(f"  Role:        {role_id}")
print(f"  Bound SP:    {client_id}")
print(f"  Membership:  DATABRICKS_SUPERUSER")
print()
print("The deployed app's SP now has CREATE on `public` via this role,")
print("so langgraph's checkpoint migrations and the long-running")
print("response-tracking tables (Lab 15) will succeed on first request.")
print("=" * 60)

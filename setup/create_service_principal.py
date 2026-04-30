# Databricks notebook source
# MAGIC %md
# MAGIC # Workshop setup -- service principal + secret scope
# MAGIC
# MAGIC End-to-end provisioning for the workshop's Lakebase service-principal
# MAGIC credentials. Run this **once per workspace** before the labs that need
# MAGIC SP-based Lakebase auth (Lab 7 memory, Lab 15 long-running).
# MAGIC
# MAGIC ## What this notebook does (idempotent end-to-end)
# MAGIC
# MAGIC 1. Look up a Databricks service principal by display name. Reuse if it
# MAGIC    already exists; create otherwise.
# MAGIC 2. Generate a fresh OAuth client secret on the SP (default) -- or skip
# MAGIC    secret rotation if a previous run already populated the scope.
# MAGIC 3. Create the Databricks secret scope (idempotent).
# MAGIC 4. Store the SP's `application_id` and the OAuth client secret as
# MAGIC    secrets in the scope.
# MAGIC 5. Grant the calling user `MANAGE` on the scope so their notebook
# MAGIC    runs can read the secrets.
# MAGIC
# MAGIC ## Sharing across students
# MAGIC
# MAGIC Keep the **default widget values** to share one SP + one scope across
# MAGIC every student in the workspace. The first student to run the
# MAGIC notebook creates the SP and populates the scope; subsequent students
# MAGIC reuse the same SP and scope but each needs the `MANAGE` ACL on the
# MAGIC scope (granted automatically on every run for the calling user).
# MAGIC
# MAGIC If you want a per-student SP, override `sp_name` and `scope_name`
# MAGIC with student-prefixed values (e.g. `dao-ai-workshop-sp-jane-doe`).
# MAGIC
# MAGIC ## Required permissions for whoever runs this
# MAGIC
# MAGIC - Workspace admin OR `Account Admin` (to create service principals).
# MAGIC - `MANAGE` on the secret scope (or admin -- needed to put secrets +
# MAGIC   set ACLs).
# MAGIC - Permission to mint OAuth secrets on the SP (workspace admin or
# MAGIC   the SP owner).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Configure widgets

# COMMAND ----------

# Widgets are the "args" -- override per-student or per-environment.
dbutils.widgets.text("sp_name", "dao-ai-workshop-sp", "1. SP display name")
dbutils.widgets.text("scope_name", "dao_ai_workshop", "2. Secret scope name")
dbutils.widgets.text("client_id_key", "DAO_AI_SP_CLIENT_ID", "3. Scope key for client_id")
dbutils.widgets.text("client_secret_key", "DAO_AI_SP_CLIENT_SECRET", "4. Scope key for client_secret")
dbutils.widgets.dropdown(
    "rotate_secret",
    "auto",
    ["auto", "always", "never"],
    "5. When to mint a fresh client_secret",
)
# auto    -- mint a new secret only if the scope doesn't already hold one
#            (first-student wins; subsequent students reuse).
# always  -- always mint a fresh secret and overwrite the scope (use after
#            an SP credential leak).
# never   -- never mint; fail loudly if the scope is missing the secret.

sp_name: str = dbutils.widgets.get("sp_name").strip()
scope_name: str = dbutils.widgets.get("scope_name").strip()
client_id_key: str = dbutils.widgets.get("client_id_key").strip()
client_secret_key: str = dbutils.widgets.get("client_secret_key").strip()
rotate_secret: str = dbutils.widgets.get("rotate_secret")

print(f"SP display name:   {sp_name}")
print(f"Secret scope:      {scope_name}")
print(f"  client_id key:   {client_id_key}")
print(f"  client_secret:   {client_secret_key}")
print(f"Rotation policy:   {rotate_secret}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Look up or create the service principal

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import ResourceAlreadyExists

w: WorkspaceClient = WorkspaceClient()

# Look up by display_name. SCIM list can be slow on large workspaces;
# the SDK's filter param keeps it focused.
existing = list(w.service_principals.list(filter=f'displayName eq "{sp_name}"'))
if existing:
    sp = existing[0]
    print(f"Reusing existing SP: id={sp.id} application_id={sp.application_id}")
else:
    try:
        sp = w.service_principals.create(display_name=sp_name)
        print(f"Created SP: id={sp.id} application_id={sp.application_id}")
    except ResourceAlreadyExists:
        # Race: another student created the SP between our list and create.
        existing = list(w.service_principals.list(filter=f'displayName eq "{sp_name}"'))
        sp = existing[0]
        print(f"SP created concurrently; reusing: id={sp.id} application_id={sp.application_id}")

sp_id: str = sp.id
sp_app_id: str = sp.application_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Decide whether to mint a fresh OAuth client secret
# MAGIC
# MAGIC Only the value matters at runtime: dao-ai reads the secret from the
# MAGIC scope. If `rotate_secret == "auto"` and the scope already holds the
# MAGIC client_secret, we skip minting (the existing SP credential keeps
# MAGIC working for every student that already has it cached).

# COMMAND ----------

def _scope_has_key(scope: str, key: str) -> bool:
    """Return True if the scope exists and contains the named key."""
    try:
        keys = {s.key for s in w.secrets.list_secrets(scope=scope)}
    except Exception:
        return False  # scope doesn't exist yet
    return key in keys


secret_present: bool = _scope_has_key(scope_name, client_secret_key)

if rotate_secret == "always" or (rotate_secret == "auto" and not secret_present):
    print(f"Minting a fresh OAuth client_secret on SP {sp_app_id}...")
    # SDK: w.service_principal_secrets_proxy.create() returns a
    # CreateServicePrincipalSecretResponse with the cleartext .secret
    # (only available at create time -- store it now or rotate later).
    secret_resp = w.service_principal_secrets_proxy.create(service_principal_id=sp_id)
    client_secret_value: str | None = secret_resp.secret
    if not client_secret_value:
        raise RuntimeError(
            "OAuth secret response did not include a value -- workspace may "
            "require the secret be created via the UI for this SP. See "
            "Settings -> Identity and access -> Service principals -> "
            f"{sp_name} -> OAuth secrets."
        )
    print("  fresh secret minted (will be written to the scope below)")
elif rotate_secret == "never":
    if not secret_present:
        raise RuntimeError(
            f"rotate_secret='never' but {scope_name}/{client_secret_key} is "
            "missing. Re-run with rotate_secret='auto' or 'always'."
        )
    client_secret_value = None
    print("  rotate_secret='never' and secret already present -- not minting")
else:
    # auto + already present
    client_secret_value = None
    print("  rotate_secret='auto' and secret already present -- not minting")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Create the secret scope (idempotent)

# COMMAND ----------

try:
    w.secrets.create_scope(scope=scope_name)
    print(f"Created scope: {scope_name}")
except ResourceAlreadyExists:
    print(f"Scope {scope_name} already exists; reusing")
except Exception as e:
    msg = str(e).lower()
    if "already exists" in msg or "resource_already_exists" in msg:
        print(f"Scope {scope_name} already exists; reusing")
    else:
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Store SP credentials in the scope
# MAGIC
# MAGIC The `application_id` is always (re)written -- it's safe to overwrite
# MAGIC because it never changes. The `client_secret` is only written when
# MAGIC we actually minted a new value above.

# COMMAND ----------

# Always (re)write the application_id; idempotent and harmless.
w.secrets.put_secret(scope=scope_name, key=client_id_key, string_value=sp_app_id)
print(f"Wrote {scope_name}/{client_id_key} = {sp_app_id}")

if client_secret_value is not None:
    w.secrets.put_secret(scope=scope_name, key=client_secret_key, string_value=client_secret_value)
    print(f"Wrote {scope_name}/{client_secret_key} (value not echoed)")
else:
    print(f"Skipped {scope_name}/{client_secret_key} (no rotation this run)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Grant the calling user MANAGE on the scope
# MAGIC
# MAGIC Each student that runs this notebook needs to be able to read the
# MAGIC secrets from their notebook compute. `MANAGE` on the scope covers
# MAGIC reading + listing + (re)writing if they ever rerun.

# COMMAND ----------

from databricks.sdk.service.workspace import AclPermission

current_user: str = w.current_user.me().user_name
try:
    w.secrets.put_acl(
        scope=scope_name,
        principal=current_user,
        permission=AclPermission.MANAGE,
    )
    print(f"Granted MANAGE on {scope_name} to {current_user}")
except Exception as e:
    print(f"Could not set ACL (may already be present): {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Summary
# MAGIC
# MAGIC The SP is reachable as:
# MAGIC
# MAGIC | what                                  | where                                              |
# MAGIC |---|---|
# MAGIC | OAuth `client_id` (= `application_id`) | `secrets/<scope_name>/<client_id_key>`             |
# MAGIC | OAuth `client_secret`                   | `secrets/<scope_name>/<client_secret_key>`         |
# MAGIC
# MAGIC Lab YAMLs reference these via the dao-ai composite-variable pattern:
# MAGIC
# MAGIC ```yaml
# MAGIC variables:
# MAGIC   client_id: &client_id
# MAGIC     options:
# MAGIC       - scope: dao_ai_workshop
# MAGIC         secret: DAO_AI_SP_CLIENT_ID
# MAGIC       - env: DAO_AI_SP_CLIENT_ID
# MAGIC ```
# MAGIC
# MAGIC ## Next
# MAGIC
# MAGIC If you'll run Lab 7 (memory) or Lab 15 (long-running), also run
# MAGIC `setup/grant_lakebase_superuser.py` to grant the SP a postgres role
# MAGIC with `DATABRICKS_SUPERUSER` membership on the Lakebase project.

# COMMAND ----------

print("=" * 60)
print("Setup complete.")
print(f"  SP id:           {sp_id}")
print(f"  application_id:  {sp_app_id}  -> {scope_name}/{client_id_key}")
if client_secret_value is not None:
    print(f"  client_secret:   stored in {scope_name}/{client_secret_key}")
else:
    print(f"  client_secret:   already in {scope_name}/{client_secret_key} (not rotated)")
print("=" * 60)

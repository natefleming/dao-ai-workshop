# `setup/` -- workshop one-time provisioning

Two **Databricks notebooks** that provision the SP + Lakebase role the
later labs depend on. Both are idempotent and widget-driven; defaults
let multiple students share a single SP / scope / role for the
workspace.

| Notebook | Run when | What it does |
|---|---|---|
| [`create_service_principal.py`](create_service_principal.py) | Once per workspace, before Lab 7 / Lab 15. | Creates (or reuses) the `dao-ai-workshop-sp` service principal, mints an OAuth client_secret, creates the `dao_ai_workshop` secret scope, stores `application_id` + `client_secret` in the scope, grants the calling user `MANAGE` on the scope. |
| [`grant_lakebase_superuser.py`](grant_lakebase_superuser.py) | Once per Lakebase project, before Lab 7 / Lab 15. | Resolves the SP's `client_id` from the secret scope, resolves the project's default branch, creates a postgres role bound to the SP with `DATABRICKS_SUPERUSER` membership (idempotent). |

## Sharing across students

Both notebooks default to **one shared SP and one shared scope per
workspace**. The first student that runs them creates the SP and
populates the scope; subsequent students see the existing resources
and exit cleanly (each student still picks up the `MANAGE` ACL on
the scope so their notebook can read the secrets).

If you'd rather give each student a private SP, override the
`sp_name` and `scope_name` widgets with student-prefixed values
(e.g. `dao-ai-workshop-sp-jane-doe` / `dao_ai_workshop_jane_doe`).

## Required permissions

- **`create_service_principal.py`**:
  - Workspace admin OR account admin (to create service principals).
  - Permission to mint OAuth secrets on the SP.
  - `MANAGE` on the secret scope (or admin -- needed to put secrets +
    set ACLs).
- **`grant_lakebase_superuser.py`**:
  - Permission to create postgres roles on the Lakebase project's
    branch (typically Lakebase project owner or workspace admin).
  - `READ` on the secret scope (default `dao_ai_workshop`).

## Run order (clean workspace)

```text
1.  setup/create_service_principal.py        # widget defaults are fine
2.  setup/grant_lakebase_superuser.py        # widget defaults are fine
3.  any lab notebook
```

## Other files

- `create_experiment.sh` -- legacy helper that creates a per-user
  MLflow experiment. Optional; the labs auto-create their own
  experiments on first deploy. Will be retired in a future cleanup
  pass.

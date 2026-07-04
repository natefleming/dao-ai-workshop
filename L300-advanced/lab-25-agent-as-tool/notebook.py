# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 25 -- Agent-as-Tool: `type: app` + `type: serving_endpoint`
# MAGIC
# MAGIC **Level:** L300 (advanced)
# MAGIC
# MAGIC ## Goals
# MAGIC
# MAGIC - Deploy two dao-ai apps (Translator, Greeter) on Databricks Apps.
# MAGIC - The Greeter has two tools that demonstrate the new first-class
# MAGIC   tool kinds in dao-ai 0.1.98:
# MAGIC   * `translate` uses `type: app` and delegates to the deployed
# MAGIC     `translator-<username>` app.
# MAGIC   * `fancy_rewrite` uses `type: serving_endpoint` and calls the
# MAGIC     Sonnet FMAPI endpoint directly.
# MAGIC - Send three inferences and watch the Greeter pick the right tool
# MAGIC   for each. Pull the resulting MLflow trace and confirm both tool
# MAGIC   spans appear.
# MAGIC
# MAGIC ## Deliverable
# MAGIC
# MAGIC Two deployed apps (`translator-<you>` and `greeter-<you>`),
# MAGIC three live inferences against the Greeter, three traces, and a
# MAGIC clean app-log scan.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **DAO-AI concept:** the `type: app` and `type: serving_endpoint`
# MAGIC first-class tool kinds replace three legacy `type: factory`
# MAGIC patterns. Both kinds discover the target's wire shape (Responses
# MAGIC vs Chat Completions) on the FIRST invocation, then cache the
# MAGIC result -- offline-safe at config-load time.
# MAGIC
# MAGIC ## Pre-reqs
# MAGIC
# MAGIC `databricks-claude-sonnet-4-5` enabled, and a workspace identity
# MAGIC that can deploy Databricks Apps. No catalog / Genie / Lakebase
# MAGIC required.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 -- Install dependencies

# COMMAND ----------

# MAGIC %pip install "dao-ai>=0.1.100" "openai>=1.40"
# MAGIC %restart_python

# COMMAND ----------

from importlib.metadata import version

print(f"dao-ai = {version('dao-ai')}")
print(f"openai = {version('openai')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 -- Configure parameters

# COMMAND ----------

import re
import time
from typing import Any

from databricks.sdk import WorkspaceClient

w: WorkspaceClient = WorkspaceClient()
short_name: str = w.current_user.me().user_name.split("@")[0].lower()
username: str = re.sub(r"[^a-z0-9]+", "-", short_name).strip("-")[:13]
print(f"Derived username: {username}")

dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "LLM endpoint")
dbutils.widgets.text("fancy_endpoint", "databricks-claude-sonnet-4-5", "fancy_rewrite endpoint")

params: dict[str, str] = {
    "username": username,
    "llm_endpoint": dbutils.widgets.get("llm_endpoint").strip(),
    "fancy_endpoint": dbutils.widgets.get("fancy_endpoint").strip(),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 -- Deploy the Translator
# MAGIC
# MAGIC The Translator is the leaf agent. The Greeter's `type: app` tool
# MAGIC references it by name (`translator-<username>`), so it must be
# MAGIC deployed and running before we invoke the Greeter.
# MAGIC
# MAGIC dao-ai's `type: app` is offline-safe -- the Greeter's config will
# MAGIC validate even when the Translator doesn't exist. The failure
# MAGIC mode is at first invocation (`/agent/info` probe returns 404 or
# MAGIC the URL doesn't resolve), not at deploy time.

# COMMAND ----------

from dao_ai.config import AppConfig, DeploymentTarget

translator_config: AppConfig = AppConfig.from_file("translator.yaml", params=params)
print(f"Translator app name: {translator_config.app.name}")

translator_config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed: {translator_config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 3a -- Wait for the Translator to be RUNNING

# COMMAND ----------

def wait_for_app(app_name: str, timeout_attempts: int = 40, sleep_seconds: int = 15) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for i in range(timeout_attempts):  # default cap ~10 min
        info = w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
        cs = (info.get("compute_status") or {}).get("state")
        aps = (info.get("app_status") or {}).get("state")
        print(f"  [{app_name}] attempt {i+1:>2d}  compute={cs}  app={aps}")
        if cs == "ACTIVE" and aps == "RUNNING":
            return info
        time.sleep(sleep_seconds)
    raise TimeoutError(f"{app_name} never reached ACTIVE/RUNNING; last status: {info}")


translator_info = wait_for_app(translator_config.app.name)
translator_app = w.apps.get(translator_config.app.name)
print(f"\nTranslator URL: {translator_app.url}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 -- Deploy the Greeter
# MAGIC
# MAGIC The Greeter references the Translator by app name in its
# MAGIC `resources.apps.translator_app` block. Same `${var.username}` in
# MAGIC both YAMLs ensures the names line up.

# COMMAND ----------

greeter_config: AppConfig = AppConfig.from_file("greeter.yaml", params=params)
print(f"Greeter app name: {greeter_config.app.name}")
print(f"Greeter tools   : {list(greeter_config.tools.keys())}")

greeter_config.deploy_agent(target=DeploymentTarget.APPS)
print(f"Deployed: {greeter_config.app.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 4a -- Wait for the Greeter to be RUNNING

# COMMAND ----------

greeter_info = wait_for_app(greeter_config.app.name)
greeter_app = w.apps.get(greeter_config.app.name)
print(f"\nGreeter URL:                  {greeter_app.url}")
print(f"Greeter oauth2_app_client_id: {greeter_app.oauth2_app_client_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 -- Mint an app-scoped bearer and call `/invocations`
# MAGIC
# MAGIC Two notes on the inference path:
# MAGIC
# MAGIC 1. dao-ai apps mount the strict `/v1/responses*` FastAPI routes
# MAGIC    ONLY when `app.background:` is configured (Lab 15 demonstrates
# MAGIC    that). The Greeter doesn't need background, so we hit the
# MAGIC    canonical MLflow Agent Server route: `POST <app.url>/invocations`
# MAGIC    with a `ResponsesAgentRequest` body.
# MAGIC 2. `databricks_openai.DatabricksOpenAI` would route through the
# MAGIC    workspace proxy with `model="apps/<name>"`, BUT it requires
# MAGIC    `WorkspaceClient.config.oauth_token()` which isn't available in
# MAGIC    the jobs runtime auth context. The token-exchange path here
# MAGIC    matches Labs 15, 19, 20.

# COMMAND ----------

import requests

subject_pat: str = w.config.authenticate()["Authorization"].removeprefix("Bearer ")

exchange = requests.post(
    f"{w.config.host}/oidc/v1/token",
    data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": subject_pat,
        "subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "all-apis",
        "audience": greeter_app.oauth2_app_client_id,
    },
    timeout=30,
)
exchange.raise_for_status()
app_token: str = exchange.json()["access_token"]
print(f"Minted app-scoped bearer (len={len(app_token)})")

# COMMAND ----------

invocations_url: str = f"{greeter_app.url.rstrip('/')}/invocations"


def ask_greeter(prompt: str, *, thread_id: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "input": [{"role": "user", "content": prompt}],
        "custom_inputs": {"configurable": {"thread_id": thread_id}},
    }
    r = requests.post(
        invocations_url,
        headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def ask_with_retry(prompt: str, *, thread_id: str, attempts: int = 8) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            return ask_greeter(prompt, thread_id=thread_id)
        except requests.HTTPError as e:
            last_err = e
            if e.response is not None and e.response.status_code in (502, 503, 504):
                print(f"  [cold start, attempt {attempt+1}] {e.response.status_code} retry in 15s")
                time.sleep(15)
                continue
            raise
    raise RuntimeError(f"never succeeded after {attempts} attempts: {last_err}")


def extract_text(envelope: dict[str, Any]) -> str:
    """Pull the assistant's reply text from a ResponsesAgentResponse envelope."""
    for item in envelope.get("output") or []:
        for block in item.get("content") or []:
            text = block.get("text")
            if text:
                return text
    return ""

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 -- Send three inferences via the Greeter

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 6a -- Direct LLM reply (no tool call)
# MAGIC
# MAGIC Simplest case: a plain "Hi" should be answered by the Greeter's
# MAGIC LLM with no tool invocation. The trace should contain zero
# MAGIC `translate` or `fancy_rewrite` spans.

# COMMAND ----------

resp_direct = ask_with_retry("Hi", thread_id=f"lab25-{username}-direct")
direct_trace_id: str = (resp_direct.get("custom_outputs") or {}).get("trace_id", "")
direct_text: str = extract_text(resp_direct)
print(f"trace_id : {direct_trace_id}")
print(f"reply    : {direct_text!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 6b -- Delegate to the Translator via `type: app`
# MAGIC
# MAGIC `"Greet me in Spanish"` should trigger one call to `translate`.
# MAGIC The first call also fires the lazy `/agent/info` probe against
# MAGIC the Translator's URL; subsequent calls reuse the cached wire
# MAGIC shape (Responses) and skip the probe.

# COMMAND ----------

resp_app = ask_with_retry("Please greet me in Spanish.", thread_id=f"lab25-{username}-app")
app_trace_id: str = (resp_app.get("custom_outputs") or {}).get("trace_id", "")
app_text: str = extract_text(resp_app)
print(f"trace_id : {app_trace_id}")
print(f"reply    : {app_text!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 6c -- Delegate to Sonnet via `type: serving_endpoint`
# MAGIC
# MAGIC `"Give me a fancy welcome"` should trigger one call to
# MAGIC `fancy_rewrite`. The first call probes the endpoint's `.task`;
# MAGIC databricks-claude-sonnet-4-5 is `llm/v1/chat`, so the dispatcher
# MAGIC selects the Chat Completions wire shape.

# COMMAND ----------

resp_endpoint = ask_with_retry("Give me a fancy welcome.", thread_id=f"lab25-{username}-endpoint")
endpoint_trace_id: str = (resp_endpoint.get("custom_outputs") or {}).get("trace_id", "")
endpoint_text: str = extract_text(resp_endpoint)
print(f"trace_id : {endpoint_trace_id}")
print(f"reply    : {endpoint_text!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 -- Inspect the traces (best-effort)
# MAGIC
# MAGIC For each of the three calls, pull the trace and list its spans.
# MAGIC The expected pattern is:
# MAGIC
# MAGIC | Call | Expected tool spans |
# MAGIC |---|---|
# MAGIC | 6a "Hi"                       | none |
# MAGIC | 6b "Greet me in Spanish"      | `translate` |
# MAGIC | 6c "Give me a fancy welcome"  | `fancy_rewrite` |
# MAGIC
# MAGIC Note: by default dao-ai apps export traces to a Databricks control-
# MAGIC plane storage host that Apps containers cannot reach. Without an
# MAGIC `app.trace_location` block (see Lab 24), `mlflow.get_trace` will
# MAGIC return None for traces produced inside the deployed app. That's a
# MAGIC trace-persistence concern, not an OBO/tool-dispatch concern, so we
# MAGIC make the assertions in Step 7a best-effort.

# COMMAND ----------

import mlflow

from dao_ai.evaluation import _wait_for_trace

mlflow.set_tracking_uri("databricks")

def dump_trace(label: str, trace_id: str) -> list[str]:
    _wait_for_trace(trace_id, timeout_seconds=30.0)
    trace = mlflow.get_trace(trace_id)
    if trace is None or trace.data is None:
        print(f"\n--- {label}  trace_id={trace_id}  (UNRETRIEVABLE — Apps trace-export host unreachable)")
        return []
    spans = list(trace.data.spans)
    span_names: list[str] = [s.name for s in spans]
    print(f"\n--- {label}  trace_id={trace_id} ---")
    for s in spans:
        print(f"  {s.name:<48s}  span_type={s.span_type}  status={s.status}")
    return span_names


direct_spans = dump_trace("6a direct", direct_trace_id)
app_spans = dump_trace("6b type:app", app_trace_id)
endpoint_spans = dump_trace("6c type:serving_endpoint", endpoint_trace_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Step 7a -- Assertions (skipped when traces are unretrievable)
# MAGIC
# MAGIC When all three trace fetches returned empty span lists, we skip
# MAGIC the span-based assertions and rely on Step 6's inference results
# MAGIC alone. To make these assertions reliable, set `app.trace_location`
# MAGIC in the greeter config (Lab 24 walks through the pattern).

# COMMAND ----------

if not direct_spans and not app_spans and not endpoint_spans:
    print("⚠️  Traces unretrievable from Apps — skipping span assertions.")
    print("    The three inferences in Step 6 succeeded, which is the")
    print("    primary signal that the `type: app` + OBO path works.")
else:
    # 6a -- direct reply, expect zero tool spans
    assert not any("translate" in n for n in direct_spans), \
        f"direct reply should NOT call translate; spans: {direct_spans}"
    assert not any("fancy_rewrite" in n for n in direct_spans), \
        f"direct reply should NOT call fancy_rewrite; spans: {direct_spans}"

    # 6b -- type: app tool, expect one translate span
    assert any("translate" in n for n in app_spans), \
        f"'Greet me in Spanish' should have called translate; spans: {app_spans}"

    # 6c -- type: serving_endpoint tool, expect one fancy_rewrite span
    assert any("fancy_rewrite" in n for n in endpoint_spans), \
        f"'Give me a fancy welcome' should have called fancy_rewrite; spans: {endpoint_spans}"

    print("\nAll three trace assertions passed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 -- Scan the Greeter's app logs for ERROR entries
# MAGIC
# MAGIC Final sanity check: no application-level errors during the run.

# COMMAND ----------

import subprocess

log_proc = subprocess.run(
    ["databricks", "apps", "logs", greeter_config.app.name, "--num-lines", "200"],
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)
print(f"databricks apps logs exit: {log_proc.returncode}")

error_lines: list[str] = [
    line for line in log_proc.stdout.splitlines()
    if "ERROR" in line and "INFO" not in line[:20]
]
if error_lines:
    print(f"\n{len(error_lines)} ERROR line(s) found:")
    for line in error_lines[:20]:
        print(f"  {line}")
else:
    print("No ERROR lines in last 200 log entries.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC Both apps are left running so you can poke at the traces and
# MAGIC the live `/agent/info` discovery endpoints. Delete with:
# MAGIC
# MAGIC ```
# MAGIC databricks apps delete --profile fevm translator-<username>
# MAGIC databricks apps delete --profile fevm greeter-<username>
# MAGIC ```
# MAGIC
# MAGIC See the workshop root README for next-steps and references.

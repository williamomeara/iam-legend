---
name: kitchen-sink
description: "The everything test for iam-legend: lint, type-check, catalog cross-validation, pytest unit/parser/integration suites, Docker build, CLI smoke, MCP server smoke (stdio + live Cloud Run), end-to-end PR-review flow on a throwaway git repo, optional Vertex Gemini live call. Self-improving — learns from each run via patterns.md."
user-invocable: true
argument-hint: "[--full | --quick | --quality | --deployed | --review-flow | lint+unit+e2e]"
allowed-tools: Read, Bash, Glob, Grep, Agent, Skill
---

# kitchen-sink — iam-legend

The "everything" test. Runs against `/Users/williamomeara/Dev/google-cloud-for-startups/iam-legend`.

## Step 0: Read Patterns & Parse Arguments

**MANDATORY:** Read `.claude/skills/kitchen-sink/patterns.md` BEFORE running anything. It encodes known flaky tests, environment quirks, false positives, and previous failure modes. Carry that context forward — skip checks that patterns.md flags as broken-and-tracked.

Parse args:
- `--full` (or no args) → all layers
- `--quick` → lint + unit only (~5s)
- `--quality` → lint + type-check + unit + parser + integration + catalog cross-validation
- `--deployed` → smoke-test the live Cloud Run endpoint (https://iam-legend-372139006998.us-central1.run.app)
- `--review-flow` → end-to-end PR-review flow on a throwaway git repo (see Layer 11)
- `+`-combos: `lint+unit+catalog`, `unit+e2e`, etc.

## Step 1: Readiness Check

```bash
cd /Users/williamomeara/Dev/google-cloud-for-startups/iam-legend
test -d .venv || { echo "venv missing — run: uv venv && uv pip install -e '.[dev]'"; exit 1; }
source .venv/bin/activate
which pytest ruff iam-legend iam-legend-mcp 2>&1
gcloud auth print-access-token >/dev/null 2>&1 && echo "ADC: present" || echo "ADC: missing (some layers will SKIP)"
```

## Step 2: Execute Layers

Run each selected layer. Capture pass/fail/skip per layer. Continue on failure — collect all results, report at the end.

### Layer 1 — Lint (ruff)
```bash
ruff check src/ tests/ catalog_build/ 2>&1
ruff format --check src/ tests/ catalog_build/ 2>&1
```
Exit 0 → PASS. Any output with `error:` or unformatted files → FAIL.

### Layer 2 — Type check (pyright) — OPTIONAL
```bash
which pyright >/dev/null && pyright src/iam_legend 2>&1 || echo "pyright not installed — SKIP"
```
Treat type errors as advisory (not blocking) until patterns.md says otherwise.

### Layer 3 — Catalog cross-validation
The catalog's correctness is the #1 risk. Every perm in `resources.yaml` must exist in `api_methods.json`; every role used in tests must exist in `roles.json`.
```bash
pytest tests/unit/test_catalog_loader.py tests/unit/test_catalog_validity.py -v 2>&1
```
Also assert dataset sizes haven't regressed:
```bash
python -c "
from iam_legend.catalog.loader import load_catalog
c = load_catalog()
assert len(c.roles) >= 2000, f'roles regression: {len(c.roles)} < 2000'
assert len(c.api_methods) >= 10000, f'api_methods regression: {len(c.api_methods)} < 10000'
assert len(c.resources) >= 90, f'resources regression: {len(c.resources)} < 90'
print(f'OK: {len(c.roles)} roles, {len(c.api_methods)} perms, {len(c.resources)} curated entries')
"
```

### Layer 4 — Unit tests
```bash
pytest tests/unit -v --tb=short 2>&1
```
Expected: ~20 tests pass. Failure here is blocking.

### Layer 5 — Parser tests
```bash
pytest tests/parsers -v --tb=short 2>&1
```
Expected: ~14 tests pass across terraform_plan, terraform_hcl + line_recovery, adk_python, gcloud_sh, base.

### Layer 6 — Integration tests
```bash
pytest tests/integration -v --tb=short 2>&1
```
Expected: ~7 tests pass (analyze orchestrator, CLI subcommands, MCP server tool gating).

### Layer 7 — Full suite with coverage
```bash
which coverage >/dev/null || uv pip install coverage
coverage run -m pytest -q
coverage report --skip-covered --fail-under=70 2>&1 || echo "coverage below 70% — investigate"
```
Coverage report is informational; first run sets a baseline in patterns.md.

### Layer 8 — Docker build smoke
```bash
# Only if docker daemon is up — many devs run without it.
docker info >/dev/null 2>&1 && {
  docker build --platform=linux/amd64 -t iam-legend:kitchen-sink-smoke . 2>&1 | tail -10
  docker run --rm iam-legend:kitchen-sink-smoke iam-legend --help 2>&1 | head -5
  docker run --rm -e IAM_LEGEND_MODE=mcp -e IAM_LEGEND_TRANSPORT=stdio iam-legend:kitchen-sink-smoke iam-legend-mcp --help 2>&1 | head -3 || true
} || echo "docker daemon not running — SKIP"
```

### Layer 9 — CLI smoke
Run the actual CLI against real fixtures:
```bash
iam-legend --version
iam-legend lookup google_storage_bucket
iam-legend lookup roles/storage.admin | head -5
iam-legend lookup storage.buckets.create
iam-legend review --plan tests/fixtures/plan_json/simple.json --format json 2>&1 | head -20
iam-legend review --repo tests/fixtures/terraform --format pretty 2>&1 | head -30
```
Look for stack traces or non-zero exits.

### Layer 10 — MCP server smoke (stdio, local)
Spawn `iam-legend-mcp` in stdio mode, send `initialize`, verify response on stdout. Kill after.
```bash
python - <<'PY'
import json, subprocess, time
proc = subprocess.Popen(
    ["iam-legend-mcp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={"IAM_LEGEND_TRANSPORT": "stdio", "PATH": __import__("os").environ["PATH"]},
)
req = {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"ks","version":"0.1"}}}
proc.stdin.write((json.dumps(req)+"\n").encode()); proc.stdin.flush()
time.sleep(2)
proc.terminate()
out, err = proc.communicate(timeout=5)
print("STDOUT:", out.decode()[:400])
assert "iam-legend" in out.decode(), f"no server identification in response: {out.decode()[:200]}"
print("OK stdio MCP")
PY
```

### Layer 11 — Live Cloud Run smoke (--deployed mode)
Test the deployed read-only HTTP MCP at `https://iam-legend-372139006998.us-central1.run.app`. Requires ADC on `tendermatch-prod` (or wherever the live service runs — read URL from patterns.md if it changes).
```bash
URL="https://iam-legend-372139006998.us-central1.run.app/mcp"
TOKEN=$(gcloud auth print-identity-token 2>/dev/null) || { echo "no identity token — SKIP"; exit 0; }

# Initialize
curl -sS -L -X POST "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"kitchen-sink","version":"0.1"}}}' \
  -D /tmp/ks_h.txt -o /tmp/ks_init.txt

SESSION=$(grep -i '^mcp-session-id' /tmp/ks_h.txt | awk '{print $2}' | tr -d '\r\n')
test -n "$SESSION" || { echo "no session id returned — FAIL"; exit 1; }
curl -sS -X POST "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Mcp-Session-Id: $SESSION" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' -o /dev/null

# tools/list — confirm privileged tools are absent on HTTP transport
curl -sS -X POST "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' 2>&1 | sed -n 's/^data: //p' | python -c "
import json,sys
r = json.loads(sys.stdin.read())
names = {t['name'] for t in r['result']['tools']}
assert 'analyze' in names and 'recommend_roles' in names, f'missing core tools: {names}'
assert 'test_permissions' not in names and 'get_iam_policy' not in names, f'PRIVILEGED LEAK: {names}'
print('OK: tools/list returns', sorted(names))
"

# lookup_permissions_for
curl -sS -X POST "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lookup_permissions_for","arguments":{"target":"google_storage_bucket"}}}' 2>&1 | sed -n 's/^data: //p' | python -c "
import json,sys
r = json.loads(sys.stdin.read())
content = r['result']['content'][0]['text']
assert 'storage.buckets.create' in content, content
print('OK: live lookup works')
"
```

### Layer 12 — End-to-end PR-review flow (--review-flow mode)
The hackathon hero demo, executed locally without a real GitHub PR. Creates a throwaway directory, runs Terraform plan, runs `iam-legend review`, prints the review payload that *would* be posted. Cleans up.

```bash
TMP=$(mktemp -d)
echo "throwaway repo: $TMP"
trap "rm -rf $TMP" EXIT

# Seed the throwaway repo with realistic content from the examples/demo-repo
cp -r examples/demo-repo/. "$TMP/"
cd "$TMP"

# Hand-craft a plan.json equivalent to what `terraform show -json` would produce.
# We can't run real `terraform plan` here because it requires GCP credentials and
# the user's `var.project_id`. Instead, fabricate a plan that matches what the
# demo-repo would produce.
cat > plan.json <<'JSON'
{
  "format_version": "1.2",
  "terraform_version": "1.9.0",
  "resource_changes": [
    {"address":"google_storage_bucket.data","type":"google_storage_bucket","name":"data","change":{"actions":["create"]}},
    {"address":"google_pubsub_topic.events","type":"google_pubsub_topic","name":"events","change":{"actions":["create"]}},
    {"address":"google_vertex_ai_endpoint.agent","type":"google_vertex_ai_endpoint","name":"agent","change":{"actions":["create"]}}
  ]
}
JSON

# Run review in JSON mode against a real project (uses ADC if available; falls
# back to no-live-diff otherwise).
PROJECT="${KITCHEN_SINK_PROJECT:-tendermatch-prod}"
iam-legend review --plan plan.json --project "$PROJECT" --format json > review.json 2>&1 || {
  echo "review CLI failed"; cat review.json; exit 1;
}

# Validate the review shape
python - <<PY
import json
r = json.load(open("review.json"))
assert isinstance(r.get("resources"), list) and len(r["resources"]) == 3, r["resources"]
kinds = {x["kind"] for x in r["resources"]}
assert kinds == {"google_storage_bucket","google_pubsub_topic","google_vertex_ai_endpoint"}, kinds
assert "storage.buckets.create" in r["required_permissions"]
assert "aiplatform.googleapis.com" in r["required_apis"]
assert r["recommendation"]["roles"], r["recommendation"]
assert r["grant_commands"], r["grant_commands"]
print("OK: review JSON is well-formed")
print(" roles:", r["recommendation"]["roles"])
print(" grants:", len(r["grant_commands"]), "commands")
print(" warnings:", len(r["warnings"]))
PY

# Now render the PR-review markdown that would be posted (using the templated
# fallback so this test doesn't require Vertex Gemini access).
python - <<PY
import json
from iam_legend.types import (
  FullReport, DetectedGCPResource, LiveState, RoleRecommendation,
  AccessRequestDraft,
)
from iam_legend.reviewer.format import format_review
from unittest.mock import patch

raw = json.load(open("review.json"))
# Rehydrate to a FullReport (rough — only fields we render need to be right)
resources = [DetectedGCPResource(**r) for r in raw["resources"]]
live = LiveState(**raw["live_state"]) if raw.get("live_state") else None
report = FullReport(
  resources=resources,
  required_permissions=raw["required_permissions"],
  required_apis=raw["required_apis"],
  by_file=raw["by_file"],
  live_state=live,
  recommendation=RoleRecommendation(**raw["recommendation"]),
  grant_commands=raw["grant_commands"],
  access_request=AccessRequestDraft(**raw["access_request"]),
  warnings=raw["warnings"],
)
with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("forced fallback for kitchen-sink determinism")):
  pl = format_review(report, deployer="kitchen-sink-tester@example.com")
print("=" * 60)
print("PR REVIEW that would be posted (event =", pl.event, "):")
print("=" * 60)
print(pl.body)
print()
print(f"Inline comments: {len(pl.comments)}")
for c in pl.comments[:3]:
  print(f"  {c.file}:{c.line} → {c.body[:80]}")
PY
```

If the review markdown looks broken (missing sections, broken markdown, "<PROJECT_ID>" leaking through when a project was provided), flag it.

## Step 3: Learn from Results

For each layer that FAILED or showed surprising behaviour, add an entry to `.claude/skills/kitchen-sink/patterns.md` under the appropriate section. Examples of things worth recording:

- "Layer 11 fails with 'no identity token' when ADC has expired (run `gcloud auth login`)"
- "Layer 8 docker build flakey on M1 macs when buildkit cache is cold; second run usually clean"
- "Layer 12 review markdown shows `<PROJECT_ID>` placeholder when --project flag is omitted"
- "roles count dropped from 2324 to 2310 — investigate; possibly a GCP role-stage migration"

Run-history entry format:
```markdown
### YYYY-MM-DD HH:MM (mode)
- Layers passed: 1,3,4,5,6,7,9,10,11,12
- Layers SKIPPED: 2 (pyright not installed), 8 (docker not running)
- Layers FAILED: none
- Tests: 54 passed in 2.6s. Coverage: 78% (baseline).
- Notes: ...
```

## Step 4: Summary Report

Print a table:
```
┌─────────────────────────────────────────────────────┬────────┐
│ Layer                                               │ Result │
├─────────────────────────────────────────────────────┼────────┤
│  1 Lint (ruff)                                      │ PASS   │
│  2 Type check (pyright)                             │ SKIP   │
│  3 Catalog cross-validation                         │ PASS   │
│  4 Unit tests                                       │ PASS   │
│  5 Parser tests                                     │ PASS   │
│  6 Integration tests                                │ PASS   │
│  7 Full suite + coverage                            │ PASS   │
│  8 Docker build smoke                               │ SKIP   │
│  9 CLI smoke                                        │ PASS   │
│ 10 MCP stdio smoke                                  │ PASS   │
│ 11 Live Cloud Run smoke (--deployed)                │ PASS   │
│ 12 E2E PR-review flow (--review-flow)               │ PASS   │
└─────────────────────────────────────────────────────┴────────┘
```

## Step 5: Exit Assessment

One line. Choose one:
- `✅ All layers green — ship it.`
- `⚠️  N/12 layers passed, M skipped, K known-failure (see patterns.md).`
- `🚫 N/12 failed — block ship until fixed: [layers].`

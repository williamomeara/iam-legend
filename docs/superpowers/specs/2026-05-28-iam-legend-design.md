# iam-legend — Design Spec

**Date:** 2026-05-28
**Author:** William O'Meara
**Status:** Draft — pending user approval before planning
**Hackathon:** Google for Startups AI Agents Challenge, Track 1 (Build — Net-New Agents). Submission deadline: 2026-06-05.

---

## 1. Problem

When you deploy GCP infrastructure or agents — Terraform, ADK Python, gcloud scripts — you cannot know in advance which IAM permissions the deploying principal needs. Current best practice, documented by Google, is to run `terraform apply`, watch it fail with a 403, grant the missing permission, retry. The principal that actually fails is rarely the developer; it's the pipeline's service account, which the developer often cannot inspect.

This creates three concrete pains:

1. **Broken pipelines.** CI runs `terraform apply`, fails halfway, leaves infrastructure half-applied. Cleanup eats hours.
2. **No upstream signal.** The developer's local `terraform plan` succeeds even when the pipeline SA lacks perms.
3. **No usable map.** The map from "Terraform `google_*` resource" to "required GCP permissions" exists implicitly in the provider source code, the gcloud command behaviour, and the IAM permissions reference page. Nothing joins them into a queryable form for agents or humans.

The space is partially covered by existing tools — most relevantly [Pike](https://github.com/JamesWoolfenden/pike), which scans Terraform statically and emits an IAM policy. Pike's catalog lags on the newest GCP surfaces (Vertex Agent Engine, Gemini Enterprise, Discovery Engine), reads only Terraform, and ships as a CLI rather than as a CI-native review bot or as an MCP-callable service for AI agents.

## 2. Solution

**iam-legend** is two products sharing one analysis core:

1. **An MCP server** — the polished primary product — that exposes GCP IAM domain knowledge as MCP tools so any AI agent (Gemini CLI, Claude Code, Cursor, Gemini Enterprise) can reason about GCP IAM without forking a custom client. Deployed on Cloud Run as streamable HTTP, also runnable locally as stdio.
2. **A GitHub Action** — the killer demo of what the core enables — that runs after `terraform plan` on every PR push, checks the pipeline's service account against the resources the PR will touch, and posts an AI code review (top-level + inline comments) blocking the deploy when permissions are missing.

Both products share `core/`, a pure Python library. A thin CLI (`iam-legend review`) falls out of the same package and is used for ad-hoc local invocations and for the Action's container entrypoint; it is not a third user-facing product. The Action does **not** route through the MCP at runtime — it imports the core directly. This is deliberate: a deterministic CI pipeline with two narrow Gemini calls at the edges is faster, cheaper, more reliable, and easier to test than an LLM agent loop. The MCP is the right architecture for interactive use where an LLM composes tools dynamically; the Action is the right architecture for automated review.

### Submission framing

The submission lead is the MCP server (Track 1 explicitly asks for MCP usage). The Action is the impact demo and the business case. The two-product framing puts MCP at the centre of the architecture diagram without compromising the engineering integrity of the Action.

## 3. Scope and non-goals

**In scope (MVP).**

- MCP server with 8 tools (see §6).
- Shared core library: parsers, catalog, GCP clients, recommender, reviewer.
- GitHub Action that posts PR reviews via REST.
- CLI binary (`iam-legend review`) — falls out of the Python package.
- Catalog covering top 50 Terraform `google_*` resources, top 25 ADK / Vertex / Discovery Engine SDK calls, top 30 `gcloud` verbs.
- Live IAM diff via Application Default Credentials.
- Gemini-backed role recommendation justification and PR review prose, both gated by deterministic fallbacks.

**Stretch (if time permits).**

- Cloud Build YAML and GitHub Actions YAML parsers.
- Registry-module walking via `.terraform/modules/` after `terraform init`.
- `explain_403` tool (paste a Terraform error → bot identifies the failing perm).
- Policy Simulator integration for cases where the action runs as a different SA than the deployer.

**Explicit non-goals.**

- Auto-granting permissions (security boundary; we draft the request, humans approve).
- Cross-cloud (AWS, Azure) coverage.
- Generating custom IAM roles (we recommend predefined roles only; custom-role creation is org-policy-dependent).
- Real-time long-lived monitoring (we're a per-event reviewer, not an agent that watches a project).

## 4. Architecture

```
google-cloud-for-startups/
└── iam-legend/
    ├── core/                  ← shared analysis library (no MCP, no agent loop)
    │   ├── parsers/           ← terraform plan json, hcl, adk python, gcloud sh, ci yaml
    │   ├── catalog/           ← baked roles + resource→perm map + api method map
    │   ├── gcp/               ← IAM Admin + testIamPermissions clients (ADC)
    │   ├── recommender/       ← set-cover solver + Gemini explanation
    │   ├── reviewer/          ← turns analysis report into PR review body + inline comments
    │   └── types.py           ← DetectedGCPResource, AnalysisReport, FullReport
    ├── mcp/                   ← MCP server wrapping core (Cloud Run + stdio)
    ├── cli/                   ← thin CLI wrapping core
    ├── action/                ← GitHub Action wrapping core (Docker-based)
    ├── catalog-build/         ← weekly refresh script for roles/api_methods
    ├── examples/
    │   └── demo-repo/         ← public demo repo with .github/workflows/deploy.yml
    ├── tests/
    │   ├── fixtures/
    │   └── e2e/
    ├── Dockerfile             ← multi-stage, used by both MCP server and Action
    └── README.md
```

Two products, one shared core. The core knows nothing about MCP or GitHub.

### Data flow — bot path

```
GitHub PR push
  → workflow runs `google-github-actions/auth` (sets ADC to deployer SA)
  → workflow runs `terraform plan -out=plan.tfplan && terraform show -json > plan.json`
  → iam-legend action runs in Docker container:
       core.parsers.analyze(plan_json + repo files)
       → list[DetectedGCPResource]
       core.catalog.resolve(resources)
       → required permissions, required APIs, warnings
       core.gcp.testIamPermissions(project, perms)
       → granted, missing
       core.recommender(missing) [Gemini call inside]
       → roles, reasoning, alternatives
       core.reviewer(report) [Gemini call inside]
       → review body + inline comments
       GitHub REST: POST /repos/.../pulls/{n}/reviews (event=REQUEST_CHANGES or APPROVE)
  → action exits 0 (review IS the signal; branch protection enforces blocking)
```

### Data flow — MCP path (interactive)

```
User in Gemini CLI: "what IAM do I need to deploy this repo?"
  → Gemini chooses to call MCP tool `analyze(kind="repo", path=".", project="my-proj")`
  → MCP server forwards the user's bearer token to GCP clients
  → core.analyze() runs the same code path as the bot
  → returns FullReport JSON
  → Gemini synthesises a natural-language answer for the user
```

## 5. Parser layer

Four parsers, one shared interface, one shared resolver behind them. Adding a fifth parser is purely additive.

### 5.1 Shared interface

```python
class Parser(Protocol):
    name: str                                    # "terraform_plan", "terraform_hcl", "adk_python", ...
    def matches(self, path: str) -> bool: ...    # quick extension/heuristic gate
    def parse(self, path_or_content: str) -> list[DetectedGCPResource]: ...
```

### 5.2 Terraform (two modes)

**Plan JSON mode (preferred, used by CI gate).** Parses `terraform show -json plan.tfplan` output. `resource_changes[].type` and `resource_changes[].change.actions` give the exact resource kind and operation (`create` / `update` / `delete`). Module nesting and registry sources are already fully resolved by Terraform — the depth-1 limitation that affects static HCL parsing does **not** apply here. This is the authoritative path for the bot.

**HCL static mode (used when no plan JSON available).** Uses [`python-hcl2`](https://pypi.org/project/python-hcl2/). Walks all `resource "google_*" "name" { ... }` blocks. Assumes `create` operation (worst-case for perms). Recurses into local modules to arbitrary depth (cheap). Registry modules surface a warning unless `terraform init` has populated `.terraform/modules/` (stretch).

**Line-number recovery (for inline PR comments).** `python-hcl2` does not preserve source positions in its parse output. We need line numbers for inline review comments. After the HCL parse identifies `(resource_type, resource_name)` pairs, a secondary text-scan pass over the original file uses an anchored regex (`^resource\s+"<type>"\s+"<name>"`) to recover the line. Same recovery pass applies to plan-JSON detections that need to map back to source files. Resources we can't locate get attached to a generic "file-level" comment rather than line-anchored. This is an honest engineering cost of using python-hcl2 instead of a position-preserving parser; alternative parsers (e.g. `hcl2-parser` if positions are exposed) are a v2 swap.

**Auto-plan fallback in `analyze(kind="repo")`.** When `terraform` is on PATH and the user opts in via `auto_plan=true`, the local stdio MCP or CLI runs `terraform plan -out=/tmp/iam-legend-<hash>.tfplan && terraform show -json` in a temp dir and uses plan JSON. No state pollution. **Auto-plan is never enabled in the hosted Cloud Run MCP** — running `terraform` against arbitrary user-submitted code on a shared server is arbitrary-code-execution surface (provider init-time side effects, remote state reads, etc.). Hosted instances require precomputed plan JSON as input.

### 5.3 ADK Python (the wedge against Pike)

AST-based — not regex. Walks `ast.parse(file)` looking for calls in a curated signature map `adk_call_signatures.yaml`.

**Import-alias resolution (critical).** Real code rarely calls fully-qualified names. `from vertexai import agent_engines; agent_engines.create(...)` shows up in the AST as `agent_engines.create`, not `vertexai.agent_engines.create`. So before matching call sites against the signature map, a first pass walks `ast.Import` and `ast.ImportFrom` nodes and builds a per-file alias table: `{local_name → fully_qualified_path}`. The call-site matcher then resolves each `ast.Call`'s callable chain through the alias table before lookup. This handles `import x as y`, `from x.y import z`, and `from x.y import z as w`. ~30 lines, no extra dependency (we deliberately avoid `astroid` / `libcst` — overkill for our narrow surface). Calls whose chain can't be fully resolved (e.g. dynamic attribute access) fall through with a warning.

Signature map (`adk_call_signatures.yaml`):

```yaml
vertexai.agent_engines.create:
  kind: vertex.agent_engine_create
  operation: create

vertexai.agent_engines.AgentEngine.deploy:
  kind: vertex.agent_engine_deploy
  operation: create

vertexai.init:
  side_effect: records project + location context for subsequent calls

google.cloud.aiplatform.Endpoint.create:
  kind: aiplatform.endpoint_create
  operation: create

google.cloud.storage.Client.create_bucket:
  kind: storage.bucket_create_imperative
  operation: create

google.cloud.discoveryengine_v1.DataStoreServiceClient.create_data_store:
  kind: discoveryengine.datastore_create
  operation: create
```

Hand-curated for the highest-value ~25 calls. Unrecognised calls fall through with a warning. This is the surface Pike does not cover.

### 5.4 gcloud CLI scripts

Regex-based with a curated `gcloud_command_map.yaml`:

```yaml
"gcloud storage buckets create":      [storage.buckets.create]
"gcloud iam service-accounts create": [iam.serviceAccounts.create]
"gcloud run deploy":                  [run.services.create, run.services.update, iam.serviceAccounts.actAs]
"gcloud ai agents deploy":            [aiplatform.reasoningEngines.create, ...]
"gcloud services enable":             [serviceusage.services.enable]
```

Map targets the ~30 most common `gcloud` verbs. Scans `*.sh`, `Makefile`, and fenced `bash`/`sh`/`shell` blocks in `README*`. Unrecognised verbs surface a warning.

### 5.5 CI/CD YAML (stretch)

**Cloud Build.** For each step, look at `name` (image) and `args`. If `gcr.io/cloud-builders/gcloud`, dispatch args to §5.4's command map. If `hashicorp/terraform`, scan for `plan`/`apply` and emit a synthetic resource indicating the whole plan needs to apply.

**GitHub Actions.** Recognise `google-github-actions/*` actions by `uses:` line and map each to a known permission signature. `run:` steps containing gcloud lines dispatch to §5.4.

### 5.6 Shared resolver

After parsing, every parser hands `DetectedGCPResource`s to one resolver:

```python
def resolve(resources: list[DetectedGCPResource]) -> ResolvedRequirements:
    perms = set()
    apis = set()
    by_file = defaultdict(list)
    warnings = []
    for r in resources:
        entry = catalog.get(r.kind, r.operation)
        if entry is None:
            warnings.append(f"unknown resource kind: {r.kind} at {r.file}:{r.line}")
            continue
        perms.update(entry.permissions)
        apis.update(entry.apis)
        by_file[r.file].extend(entry.permissions)
    return ResolvedRequirements(perms, apis, by_file, warnings)
```

The resolver does not care which parser produced the resource. All parsers contribute to one unified permission set per `analyze()` call.

### 5.7 MVP scope tiering

**Tier 1 (must work for the demo).** Terraform plan JSON, Terraform HCL with full local-module recursion, auto-plan fallback when `terraform` is on PATH, ADK Python core signatures (~25), gcloud verbs (~30).

**Tier 2 (try).** Cloud Build YAML. GitHub Actions `google-github-actions/*`.

**Tier 3 (cut if time tight).** Makefile parsing. README code-block extraction. Registry-module walking via `.terraform/modules/`.

Tier 2 and 3 missing will not break the demo. Tier 1 missing will.

## 6. MCP tool surface

Eight tools. `analyze` is the workhorse for ~90% of calls; the rest are escape hatches. Implementation uses **FastMCP** (`mcp.server.fastmcp.FastMCP` in the official `mcp` Python package), the idiomatic high-level API: decorator-based tool registration, automatic JSON-schema generation from Python type hints, and built-in stdio + streamable-HTTP transports. No low-level MCP protocol plumbing.

**Tool availability differs by transport.** Tools that touch user credentials are stdio-only (see §8.2 for the security rationale):

| Tool | Stdio (local) | Hosted HTTP |
|---|---|---|
| `analyze` (with `kind="plan_json"` or `kind="snippet"`) | ✅ | ✅ |
| `analyze` (with `kind="repo"` or `auto_plan=true`) | ✅ | ❌ |
| `lookup_permissions_for`, `find_roles_with` | ✅ | ✅ |
| `recommend_roles`, `generate_grant_commands`, `explain_403` | ✅ | ✅ |
| `test_permissions`, `get_iam_policy` | ✅ | ❌ |

### Workhorse

```
analyze(
  input:    str | dict,                          # repo path, plan JSON, file, or snippet
  kind:     "auto"|"repo"|"dir"|"plan_json"|"file"|"snippet" = "auto",
  project:  str | None = None,                   # if set + ADC available → live diff
  principal: str = "self",
) -> FullReport
```

### Lookups (deterministic, no network)

```
lookup_permissions_for(target: str)              # resource kind | role | permission — auto-detects
find_roles_with(permission: str)
```

### Live primitives (require ADC)

```
test_permissions(project: str, permissions: list[str], principal: str = "self")
get_iam_policy(project: str, resource: str | None = None)
```

### Recommender + helpers

```
recommend_roles(
  permissions: list[str],
  avoid: list[str] = ["roles/owner", "roles/editor"],
  prefer_per_service: bool = True,
) -> { roles: [...], reasoning: str, alternatives: [...] }

generate_grant_commands(roles: list[str], project: str, principal: str) -> list[str]

explain_403(error_text: str, repo_context: str | None = None) -> { permission: str, resource_hint: str, fix: str }
```

### Response shapes

```python
DetectedGCPResource = {
    "kind":      str,          # "google_storage_bucket" | "vertex.agent_engine_create" | ...
    "name":      str,
    "operation": "create" | "update" | "delete",
    "file":      str,
    "line":      int,
    "source":    "terraform_plan" | "terraform_hcl" | "adk_python" | "gcloud_sh" | "cloudbuild" | "github_actions",
}

FullReport = {
    "resources":            [DetectedGCPResource, ...],
    "required_permissions": [str, ...],          # union across all resources
    "required_apis":        [str, ...],          # serviceusage enablement set
    "by_file":              { path: [perms] },   # supports inline PR comments
    "live_state":           { "granted": [...], "missing": [...] } | None,
    "recommendation":       { "roles": [...], "reasoning": str, "alternatives": [...] },
    "grant_commands":       [str, ...],
    "access_request":       { "subject": str, "body": str, "suggested_approvers": [...] },
    "warnings":             [str, ...],          # parser unknowns, catalog gaps, ADC missing, etc.
}
```

Two design notes:

- **`analyze` is intentionally overloaded** (repo / plan JSON / snippet). The CI path uses `kind="plan_json"`; the interactive path uses `kind="repo"`. Both share the code after dispatch.
- **`warnings` is load-bearing.** Catalog misses surface as visible warnings on the PR review — never silently dropped. We over-report rather than under-report.

## 7. Ground-truth catalog

Three datasets, three sources, three freshness profiles.

### 7.1 Dataset 1 — Predefined roles → permissions

- **Source.** `iam.roles.list({view: "FULL"})` via IAM Admin API.
- **Refresh.** Weekly via CI cron running `catalog-build/refresh_roles.py`. Auto-commits an updated snapshot and opens a PR.
- **Output.** `catalog/roles.json`. ~1500 roles.

### 7.2 Dataset 2 — GCP API method → permissions

- **Source.** The official [GCP permissions reference](https://cloud.google.com/iam/docs/permissions-reference) (single-page HTML, stable structure). Scraped at refresh time.
- **Refresh.** Same weekly cron.
- **Output.** `catalog/api_methods.json`. ~5000 method-to-permission bindings.

### 7.3 Dataset 3 — IaC resource → operation → required perms (the curated layer)

- **Source.** Hand-curated YAML, seeded from three places:
  - Pike's existing catalog (Apache-2.0, attributed in NOTICE).
  - The `terraform-provider-google` source — each resource's CRUD calls map to API methods, then resolve via Dataset 2.
  - For ADK / Vertex / Agent Engine / Gemini Enterprise / Discovery Engine: hand-written from the official SDK docs. This is exactly the surface Pike misses.
- **Refresh.** Manual. PRs against `catalog/resources.yaml`. Versioned with semver.
- **Output.** `catalog/resources.yaml`. ~100 curated entries for MVP.

```yaml
google_storage_bucket:
  create: [storage.buckets.create]
  update: [storage.buckets.update]
  delete: [storage.buckets.delete]

google_cloud_run_v2_service:
  create: [run.services.create, iam.serviceAccounts.actAs]
  update: [run.services.update, iam.serviceAccounts.actAs]
  delete: [run.services.delete]

vertex.agent_engine_create:
  create:
    - aiplatform.reasoningEngines.create
    - aiplatform.reasoningEngines.deploy
    - storage.objects.create
    - storage.objects.get
  required_apis: [aiplatform.googleapis.com]

gcloud.run.deploy:
  create: [run.services.create, run.services.update, iam.serviceAccounts.actAs]
```

The three datasets compose at lookup time. The resolver cross-checks every permission in Dataset 3 against Dataset 2 — a curated permission that does not exist in the IAM permissions reference surfaces a build-time warning.

### 7.4 Role recommendation (set-cover + Gemini)

After analysis produces a flat set of required permissions:

1. **Filter** the role catalog to roles whose permission set intersects the requirement set.
2. **Greedy set-cover** with weighted preferences:
   - Prefer per-service roles (`roles/storage.objectAdmin`) over broad roles (`roles/owner`).
   - Penalise roles where `selected.permissions \ required` is large.
   - Hard deny-list: `roles/owner`, `roles/editor`, `roles/viewer`, `roles/iam.securityAdmin` unless explicitly overridden via the `avoid` argument.
3. **Top 2-3 candidate sets → Gemini.** Single prompt: "Given these required perms and these candidate role bundles, pick the smallest sensible set, explain in 2 sentences why this beats `roles/owner`, and surface any concerning grants." Natural-language reasoning flows verbatim into the PR review.

Math is deterministic. LLM handles prose.

### 7.5 Catalog completeness — the warning system

Every gap surfaces. If a parser identifies a resource kind not in `resources.yaml`, the resolver emits a warning. The reviewer turns warnings into visible comments on the PR review — never silently drops them. False negatives in IAM are worse than false positives.

## 8. Deployment and auth

### 8.1 MCP server deployment

One Docker image. Transport chosen at startup by env var. Both transports run on `mcp.server.fastmcp.FastMCP`.

- `IAM_LEGEND_TRANSPORT=stdio` — local MCP clients (Claude Code, Gemini CLI, Cursor). **Privileged mode**: full toolset including live IAM diff and auto-plan, because the process runs as the user and uses their existing ADC.
- `IAM_LEGEND_TRANSPORT=http` — streamable-HTTP MCP server on Cloud Run. **Public read-only mode**: catalog lookups, static analysis on submitted text, recommender, grant-command generation. No live IAM, no auto-plan, no user credentials accepted.

Image: `python:3.13-slim` + the package + the baked catalog snapshot. <50 MB. Single multi-stage Dockerfile.

Cloud Run deploy:

```
gcloud run deploy iam-legend \
  --image=us-docker.pkg.dev/<project>/iam-legend/iam-legend:latest \
  --region=us-central1 \
  --service-account=iam-legend-runtime@<project>.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-env-vars=IAM_LEGEND_TRANSPORT=http,VERTEX_PROJECT=<project>,VERTEX_LOCATION=us-central1
```

Runtime SA has `roles/aiplatform.user` only (for the Vertex Gemini call). It holds no read access to user projects. The hosted instance is intentionally credentialless w.r.t. user projects — see §8.2 for why.

### 8.2 Auth model (security-first)

The earlier draft of this spec proposed forwarding user GCP bearer tokens to the hosted MCP server (via `Authorization` header or an `auth_token` tool argument). That has been removed. Two reasons:

1. **Tool arguments leak.** GCP access tokens passed as MCP tool arguments end up in conversation transcripts, client telemetry, and host-LLM logs. Even with header-based forwarding, no MCP client today reliably implements per-call user-token passthrough — making the feature unusable in practice while widening the attack surface.
2. **Arbitrary code on shared infra.** Running `terraform plan` against user-submitted repo contents inside a shared Cloud Run instance is arbitrary code execution (provider init-time side effects, remote state reads). Not acceptable.

**Resulting auth model — one rule per surface:**

- **Local stdio MCP.** Runs as the local user. `google.auth.default()` resolves to whatever the user set with `gcloud auth application-default login`. Live IAM calls and auto-plan succeed transparently. This is the privileged surface; everything works.
- **Hosted Cloud Run MCP.** Read-only / no credentials. Accepts only inputs that need no GCP access: precomputed plan JSON, snippet text, lookups, recommender input. Live IAM and auto-plan tools are unregistered on this transport.
- **GitHub Action.** Runs after `google-github-actions/auth` in the workflow. That step (via Workload Identity Federation + OIDC) sets ADC to the deployer SA for the remainder of the job. The Python entrypoint calls `google.auth.default()` and gets the deployer SA's credentials. `testIamPermissions` answers for that principal — exactly what we want. No new secrets beyond `GITHUB_TOKEN`. The Action runs the same `core/` code as stdio MCP, not the hosted server.

### 8.3 Where Gemini is called (Vertex AI, not API key)

Two narrow call sites inside `core/`:

1. **`core/recommender/justify.py`** — after set-cover picks candidate role bundles, Gemini explains the choice. Single completion, ~300 in / ~100 out. Gemini Flash-tier.
2. **`core/reviewer/format.py`** — given the structured report + diff context, Gemini writes the prose for the top-level PR review body and the inline comments. Single completion, ~1500 in / ~500 out. Gemini Flash-tier.

Both via Vertex AI Python SDK, ADC-authenticated. Model: current-generation Gemini Flash-tier (specific identifier resolved at deploy time against the Vertex model catalog). No API keys anywhere. Bills against the runtime project.

Gemini is **off the critical path of correctness**. If a Gemini call fails, the reviewer falls back to templated prose using only the deterministic analysis. Catalog correctness — not LLM correctness — determines whether the review is right.

### 8.4 GitHub Action wiring

```yaml
# action.yml
name: iam-legend
description: AI code review for GCP IAM gaps before terraform apply.
inputs:
  terraform-plan:
    description: Path to terraform plan JSON output.
    required: false
  working-directory:
    description: Repo root to scan when no plan provided.
    default: '.'
  project-id:
    description: GCP project the deploy targets.
    required: true
  fail-on-missing:
    description: Exit non-zero when perms are missing.
    default: 'false'
runs:
  using: docker
  image: docker://ghcr.io/<user>/iam-legend-action:v1
```

User-side workflow (6 lines beyond what they already have):

```yaml
permissions:
  contents: read
  pull-requests: write
  id-token: write

- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ...
    service_account: deployer@my-proj.iam.gserviceaccount.com

- run: terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json

- uses: iam-legend/action@v1
  with:
    terraform-plan: plan.json
    project-id: my-proj
```

### 8.5 Failure modes

| Failure | Behaviour |
|---|---|
| Plan JSON missing | Fall back to HCL static parse + warning in the review |
| Catalog miss on a resource | Warning comment ("iam-legend could not analyse `google_x` — please verify") |
| `testIamPermissions` denied | Compute expected perms from project's IAM policy + role catalog; warn that live diff is unavailable |
| Gemini call fails | Fall back to templated review prose; still post the review; exit 0 |
| GitHub token cannot post | Print review to action log; emit `::error::` workflow annotation (visible red X on the job in the GitHub UI without breaking the run); **exit non-zero** so branch protection can treat this as a failed required check. A silent fail-open here would let PRs ship with no IAM signal, which is the exact failure we built the bot to prevent. |

The Action **fails closed only on signalling failure** (its own inability to communicate the result). Every other failure mode posts a partial-but-useful review and exits 0.

## 9. Testing strategy

Three layers. None optional.

### 9.1 Catalog correctness (unit)

- Every entry in `catalog/resources.yaml` cross-checked against `catalog/api_methods.json` — every listed permission must exist.
- Every predefined role mentioned in tests or examples must exist in `catalog/roles.json`.
- Runs on every CI push. A catalog typo cannot ship.

### 9.2 Parser correctness (fixture-based regression)

- `tests/fixtures/terraform/` — 15-20 real `.tf` files: simple, `count`, `for_each`, nested local modules, registry modules, IAM bindings, Cloud Run, Vertex Agent Engine, GKE.
- `tests/fixtures/plan_json/` — captured `terraform plan -json` from each fixture. Snapshot-tested.
- `tests/fixtures/adk_python/` — real ADK patterns from quickstarts + agent_engines docs.
- `tests/fixtures/gcloud_sh/` — common deploy scripts.

Each fixture → expected `list[DetectedGCPResource]`. Snapshot tests catch every regression.

### 9.3 End-to-end (against a real GCP project)

- One throwaway test project provisioned via a setup script.
- One test SA with deliberately incomplete permissions.
- Fixture repo with a Terraform plan that needs perms the test SA lacks.
- `iam-legend review --plan plan.json --project=<test> --dry-run` → assert the report identifies exact missing perms.
- Re-run after granting the recommended role → assert "approved."
- Runs in CI weekly (gated on GCP credentials) and locally on demand.

Gemini calls are stubbed in tests. We assert the deterministic analysis; we do not assert Gemini's prose. Real Gemini calls happen only in manual demo runs.

## 10. Submission deliverables

| Devpost field | What ships |
|---|---|
| Code | GitHub repo. Apache-2.0. `mcp/`, `cli/`, `action/`, `core/`, `examples/`. Honest README with coverage matrix. |
| Video | 90-second YouTube unlisted. See script below. |
| Architecture diagram | Excalidraw PNG. MCP server centre, Cloud Run host, three client surfaces, catalog dataflow, Gemini call points. |
| Testing access | Public demo PR on a public test repo. Hosted Cloud Run MCP URL. |
| Theme | Track 1 — Build (Net-New Agents). MCP language in track description is the strongest fit. |

### Video script (90 seconds)

```
0-10s   Cold open: dev watches CI fail at terraform apply with a 403.
        VO: "GCP IAM. The 4th-deploy-of-the-day problem."

10-25s  Architecture diagram. "iam-legend is an MCP server that makes any
        AI agent IAM-aware — and a GitHub Action that brings that intelligence
        directly to your PRs."

25-55s  Bot demo on a real PR.
        - commit adds Vertex Agent Engine deploy
        - terraform plan succeeds
        - iam-legend posts a review: "Changes requested — deployer SA missing
          aiplatform.reasoningEngines.create"
        - inline comment on deploy.py:23
        - grant roles/aiplatform.user, push again
        - bot posts "Approved ✅"

55-80s  MCP demo. Gemini CLI in a different repo.
        "What IAM do I need to deploy this?"
        Gemini calls MCP tools, returns gap + grant commands + access-request draft.

80-90s  Tagline: "iam-legend. Stop deploying. Start shipping."
        Repo URL and Cloud Run demo URL on screen.
```

### Submission question drafts

**Familiarity with Google Cloud (1-5):** 4. Comfortable with Vertex AI, ADK, IAM, Cloud Run, Cloud Build, GCS, Terraform google provider.

**Familiarity with AI Studio (1-5):** To fill in.

**Readiness for launch:** MCP server deployed on Cloud Run with a public demo endpoint. GitHub Action published to the Marketplace. Catalog covers the top ~100 GCP resources across Terraform, ADK Python, and gcloud — sufficient for the majority of real GCP deploys, with explicit warnings on uncovered resources. Catalog refresh automated weekly via CI. Tested end-to-end against a live GCP project with intentionally incomplete IAM. Ready for early users today; growing the catalog and adding Cloud Build / GitHub Actions YAML parsers are the immediate next steps.

**Most critical Agent Platform feature / what's missing:** Most critical — MCP support in ADK and Gemini CLI, letting our IAM-domain tools compose with any agent without forking a custom client. Missing — a canonical way for an MCP server hosted on Cloud Run to receive the calling user's GCP credentials without each client re-implementing auth-header forwarding. Standardising user-identity passthrough at the MCP layer would unlock a whole class of "GCP-aware MCP" tools.

**One API capability that would have saved 2+ hours:** A first-party endpoint mapping `(terraform google_* resource, operation)` → required IAM permissions in structured JSON. Today this mapping lives implicitly in the terraform-google provider source, gcloud verb behaviour, and the permissions reference HTML — and we had to hand-curate it. Google holds all three sources internally; exposing the joined view would let any tool reason about Terraform IAM correctly.

## 11. Open questions and explicit risks

- **GCP test project setup time.** Provisioning the e2e test project + test SA with intentionally incomplete perms could eat half a day. Mitigation: script it; have it ready before catalog work starts.
- **Catalog quality is the single biggest demo risk.** A wrong permission in `resources.yaml` will be visible in the demo. Mitigation: cross-check every Dataset-3 entry against Dataset 2 at build time; manual review of the curated set the day before recording.
- **Hosted Cloud Run MCP is intentionally credentialless** (see §8.2). It cannot perform live IAM diff or auto-plan. The interactive live-diff demo uses stdio mode against the user's local ADC — which is the realistic deployment pattern anyway. The hosted instance demos catalog lookups, recommender, and static analysis only.
- **9-day timeline is tight.** Solo, with tier-2 and tier-3 scope at risk. Cut order if behind: CI YAML parsers → README extraction → `explain_403` → Policy Simulator.
- **Pike attribution.** Catalog seed from Pike must be attributed in NOTICE; license is Apache-2.0 so compatible.

---

## 12. Validation outcomes (post-build appendix)

This section records the as-built state vs. the design spec above. Added 2026-05-28 after end-to-end validation against Google's `agent-starter-pack`.

### What was built per spec

- **MCP server (FastMCP) on stdio + Cloud Run streamable-HTTP** — §6, §8.1 — built and deployed at `https://iam-legend-935195616837.us-central1.run.app`. Privileged tools (live IAM diff, auto-plan) are gated to stdio per §8.2 security model; verified in production via `tools/list`.
- **Four parsers** — §5 — terraform_plan, terraform_hcl (with line recovery), adk_python (with import-alias resolution), gcloud_sh. All four register against the dispatcher per §5.1.
- **Hybrid recommender** — §7.4 — set-cover proposes 5 candidate bundles using 4 distinct scoring strategies; Gemini picks by index; catalog-verified before return; deterministic fallback if Gemini fails or hallucinates.
- **GitHub Action** — §8.4 — Docker-based, runs as the deployer SA via WIF, posts PR review with PyGithub. Published at `williamomeara/iam-legend@v0.1.1`.
- **Catalog refresh** — §7.1–7.3 — `catalog_build/refresh_roles.py` + `catalog_build/refresh_api_methods.py`.

### Discrepancies vs. spec — what changed during build

- **`api_methods.json` is now derived from `roles.json`**, not from scraping the public permissions reference. The reference page turned out to be JS-rendered, and a naive `urlopen` returns zero perms. Pivoted to deriving the permissions set from the role catalog (every real GCP perm appears in at least one predefined role), plus 9 manually appended perms that no role covers yet (`aiplatform.reasoningEngines.deploy`, `cloudbuild.builds.delete`, `iam.workloadIdentityPools.*`, etc.). More authoritative than the original spec's scrape approach.
- **Set-cover became candidate-generator, not single-picker.** Spec §7.4 step 3 said "top 2-3 candidate sets → Gemini" — but v0.1's `set_cover.cover()` returned a single chosen bundle, leaving Gemini only writing prose. Refactored in v0.1.1 to `propose_candidates()` returning N distinct bundles with metadata, and Gemini picking by index. This is what §7.4 actually wanted; the v0.1 under-implementation caused the `roles/iam.databasesAdmin`-for-non-database-perms bug class.
- **Vertex model identifier:** spec said "Gemini Flash-tier (specific identifier resolved at deploy time)." Reality: `gemini-flash-latest` is an AI Studio alias that 404s on Vertex; the working identifier is `gemini-2.5-flash`. Documented in code.
- **PyGithub create_review wants a Commit OBJECT, not a SHA string.** Spec §8.3 didn't specify; in v0.1 we passed the SHA and got a confusing error. v0.1.1 fetches the Commit object first.
- **Inline PR comments anchored to lines outside the PR diff are rejected** by the GitHub API. v0.1.1 catches this and falls back to top-level-only review with a `::warning::` annotation.

### Catalog as-built

- **Roles:** 2,324 (from live `iam.roles.list`)
- **Permissions:** 13,403 (derived from roles + 9 manually appended)
- **Curated IaC kinds:** 100 — ~45 Terraform `google_*`, ~25 ADK/Vertex/Discovery Engine SDK calls, ~30 gcloud verbs

### Validation coverage

Validated against `0` catalog warnings on every project generated by `uvx agent-starter-pack create`:

| Template | Resources | Warnings |
|---|---|---|
| adk (base) | 44 | 0 |
| agentic_rag | 51 | 0 |
| adk_live | 44 | 0 |
| adk_a2a | 44 | 0 |
| adk_go | 44 | 0 |
| adk_java | 44 | 0 |
| adk_ts | 44 | 0 |

Locked in by `tests/parsers/test_canonical_starter_pack.py`.

### Live demo

- **Public PR with iam-legend posting a real review:** https://github.com/williamomeara/iam-legend-validation-demo/pull/1
- **Hosted MCP endpoint:** https://iam-legend-935195616837.us-central1.run.app (Cloud Run, `iam-legend-runtime` SA with `roles/aiplatform.user` only)
- **Workload Identity Federation:** pool `iam-legend-demo` + provider `github-demo` on `tendermatch-prod`, restricted to `repository_owner == 'williamomeara'`
- **Deployer SA in demo:** `iam-legend-demo-deployer@tendermatch-prod` — intentionally limited to `roles/storage.admin` + `roles/run.admin` + `roles/aiplatform.user` so iam-legend has 13–14 missing perms to surface

### Test count

**68 tests** pass in ~3 seconds. Coverage:
- 7 unit tests for types, catalog loader, catalog validity
- 4 unit tests for the resolver
- 4 unit tests for set-cover
- 2 unit tests for justify (legacy)
- 12 unit tests for the hybrid recommender (set-cover + Gemini + fallback)
- 3 unit tests for grant commands
- 3 unit tests for reviewer format
- 2 unit tests for GitHub posting
- 2 unit tests for GCP auth + IAM clients
- 14 parser tests (terraform_plan, terraform_hcl, adk_python, gcloud_sh, base, line_recovery, canonical_starter_pack)
- 7 integration tests (analyze, CLI, MCP server)

# iam-legend — Devpost submission answers

Final answers to copy-paste into the Devpost submission form.

## Project links

- **Code:** https://github.com/williamomeara/iam-legend
- **Demo PR (live):** https://github.com/williamomeara/iam-legend-validation-demo/pull/1
- **Hosted Cloud Run MCP:** https://iam-legend-372139006998.us-central1.run.app
- **Release:** https://github.com/williamomeara/iam-legend/releases/tag/v0.1.1
- **Architecture diagram:** docs/architecture.md
- **Design spec:** docs/superpowers/specs/2026-05-28-iam-legend-design.md
- **Video:** *(record at the end)*

## Theme

**Build (Net-New Agents)** — Track 1.

## Description sections

### Problem to solve

GCP deployments fail in CI when the deployer service account lacks an IAM permission no human noticed was needed. Real-world process: run `terraform apply`, watch it fail with a 403 halfway through, leave infrastructure half-applied, grant the missing perm, retry. Google's own documented best practice is *literally* "start with no roles, add them as 403s identify what's missing." There's nothing that catches the gap **before** `apply`, against the principal that will actually run it.

### Our solution

**iam-legend** is the GCP IAM toolbelt that lives between `terraform plan` and `terraform apply`. It ships as one Python core consumed by three surfaces: a FastMCP server (so any AI agent — Gemini CLI, Claude Code, Cursor — becomes IAM-aware), a GitHub Action that posts AI code reviews on PRs, and a CLI.

The agent reads your Terraform / ADK Python / gcloud scripts via four parsers, resolves the changes against a baked catalog (2,324 roles + 13,403 perms + 100 curated IaC kinds), diffs the requirement against the live `testIamPermissions` answer for the deployer SA, and posts a code review with role recommendations + ready-to-run `gcloud` grant commands.

Gemini fires at two narrow call sites: the **recommender** (set-cover proposes 5 candidate role bundles with metadata, Gemini picks the best with full context and catalog-grounded verification) and the **review formatter** (composes the natural-language PR review body). Both are off the critical path — deterministic fallbacks ship if Vertex is unreachable.

Validated end-to-end against all 7 official Google ADK starter templates with zero catalog warnings, and posting live reviews on a real PR.

### Technologies used

- **Google Cloud**: Vertex AI Gemini 2.5 Flash (recommender + reviewer); Cloud Run (hosted MCP server); IAM Admin API + `testIamPermissions` + `getIamPolicy`; Workload Identity Federation (GitHub Actions → GCP, no SA keys); Artifact Registry; Cloud Build (Docker image build); Cloud Run source-based deploy.
- **AI / Agent stack**: FastMCP (Model Context Protocol server); Vertex AI Python SDK; `google.genai` JSON-mode response with response_mime_type for structured picker output.
- **Python**: Python 3.13, `python-hcl2` (Terraform HCL parsing), `ast` (ADK Python AST + import-alias resolution), PyYAML, PyGithub (PR review posting), Click (CLI), Rich (terminal output), pytest (68 tests).
- **Open source**: Pike (Apache-2.0) catalog data seed; attributed in NOTICE.

### Data sources / APIs

- `iam.roles.list` (full GCP predefined-role catalog, weekly refresh)
- Permission identifiers derived from `roles.json` + the published [permissions reference](https://cloud.google.com/iam/docs/permissions-reference)
- `terraform-provider-google` source for CRUD-to-API-method mapping
- Hand-curated mapping of ADK / Vertex / Discovery Engine SDK call signatures
- Live `projects.testIamPermissions` and `projects.getIamPolicy` against the user's GCP project at review time

### Findings and learnings

Three things that surprised me:

1. **The agent-starter-pack uses `google_vertex_ai_reasoning_engine`** (Terraform resource), not `vertexai.agent_engines.create()` (the Python SDK call). My initial catalog only had the latter — found this only by running against the actual starter, which I'd never have caught with unit tests. Locked in by a regression fixture now.

2. **Vertex AI model identifiers differ from AI Studio aliases.** `gemini-flash-latest` works on AI Studio but 404s on Vertex AI; use `gemini-2.5-flash`. The Vertex SDK silently failed and dropped to a templated fallback that *looked* like it worked, which made the misconfiguration invisible for half an hour. Added explicit error logging in v0.1.1 so silent fallbacks now surface as `::warning::` annotations.

3. **PyGithub's `create_review(commit=...)` wants a Commit object, not a SHA string.** Passing a string produces an unhelpful error where `str(e)` is literally just the SHA. Also: GitHub rejects inline review comments anchored to lines that aren't in the PR diff — common when iam-legend wants to flag *existing* resources rather than the PR's additions. v0.1.1 catches both and falls back to top-level-only review cleanly.

### Third-party integrations

- [Pike](https://github.com/JamesWoolfenden/pike) — Apache-2.0. Used as seed data for the curated resource → permissions mapping. Attribution in NOTICE.
- [agent-starter-pack](https://github.com/googlecloudplatform/agent-starter-pack) — Apache-2.0. Used as the validation target (unmodified projects from `uvx agent-starter-pack create`).
- `google-cloud-iam`, `google-cloud-aiplatform`, `mcp` (FastMCP), `python-hcl2`, `PyGithub` — standard open-source dependencies; full list in `pyproject.toml`.

## Submission questions (judge-only)

### 1. Familiarity with Google Cloud products (1-5)

**4.** Comfortable with Vertex AI Gemini, ADK, IAM, Cloud Run, Cloud Build, GCS, Workload Identity Federation, the terraform-google provider. Deployed multi-service systems on GCP including this submission.

### 2. Familiarity with Google AI Studio (1-5)

**3.** Have used AI Studio for prompt iteration and rapid prototyping, but Vertex AI is my production target — chose Vertex for iam-legend specifically so the recommender + reviewer can run against the same project as the deploy without an external API key, and so the AI Studio vs Vertex model-identifier mismatch (which we hit during development) doesn't bite users.

### 3. Readiness for launch

Production-ready for early users. The GitHub Action is published at `williamomeara/iam-legend@v0.1.1`; the MCP server is deployed on Cloud Run with a public auth-gated endpoint at https://iam-legend-372139006998.us-central1.run.app; the catalog covers ~100 IaC kinds with `0` catalog warnings on all 7 official Google ADK starter templates; the recommender uses a hybrid set-cover + Gemini-picker architecture with deterministic fallback; 68 tests pass in ~3 seconds; failure modes are exercised and fail-soft. The live demo PR at https://github.com/williamomeara/iam-legend-validation-demo/pull/1 is a real PR with a real review posted by the bot on an unmodified `agent-starter-pack` repo. Next steps for full launch: pre-built GHCR image (eliminate Docker build on every Action run, drops latency from ~50s to ~5s), GitHub Marketplace publication, broader catalog (currently strong on GCP, would extend to AWS/Azure for multi-cloud orgs).

### 4. Most critical Agent Platform feature / what's currently missing

**Most critical:** Model Context Protocol (MCP) support in the Agent Development Kit and in Gemini CLI. Letting our IAM-domain tools compose with any agent — without forking a custom client — is the entire reason iam-legend ships as an MCP server first. The combination of FastMCP's tool decorator + Vertex AI Gemini Flash JSON-mode responses is what made the hybrid recommender (set-cover proposes, Gemini picks-by-index with structured output) tractable in a 9-day window.

**Missing:** A canonical way for an MCP server hosted on Cloud Run to receive the calling user's GCP credentials securely — without each MCP client re-implementing auth-header forwarding, and without putting bearer tokens into tool arguments (where they'd leak in transcripts and host-LLM logs). Standardising user-identity passthrough at the MCP layer — perhaps a sister of the OAuth flow MCP recently added — would unlock a whole class of "GCP-aware MCP tools that work against the user's own project rather than a service-account-managed one."

### 5. One API capability that would have saved 2+ hours

A first-party Google Cloud endpoint exposing the mapping `(terraform google_* resource, operation) → required IAM permissions` as structured JSON. Today this mapping lives implicitly in *three* places: the `terraform-provider-google` source (CRUD methods), the gcloud CLI behaviour (verbs), and the IAM permissions reference HTML page (the perms themselves). We had to hand-curate the join. Google holds all three sources internally — exposing the joined view would let any tool reason about Terraform-IAM relationships correctly without each tool building its own catalog. (This is essentially what iam-legend ships as `catalog/resources.yaml` — would happily upstream it.)

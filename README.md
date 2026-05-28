# iam-legend

> GCP IAM toolbelt for AI agents and CI pipelines.

iam-legend reads your Terraform, ADK Python, and gcloud scripts, figures out which IAM permissions the deploying service account actually needs, checks them against the live project IAM, and either approves the PR or posts a code review listing the gap — before `terraform apply` fails halfway through and leaves your infrastructure half-applied.

Built for the **Google for Startups AI Agents Challenge** (Track 1: Build — Net-New Agents). MCP-first architecture, Gemini Flash in the loop for review prose and role-recommendation justification.

## What it does

Three surfaces share one analysis core:

1. **MCP server** (FastMCP) — plug into Gemini CLI, Claude Code, or Cursor. Ask "what IAM does this repo need?" and get a structured answer.
2. **GitHub Action** — runs after `terraform plan`, posts an AI code review on the PR with inline comments tied to the offending `.tf` / `.py` / `.sh` lines. Blocks deploys with missing permissions instead of letting CI fail halfway through.
3. **CLI** — `iam-legend review --plan plan.json --project my-proj` for ad-hoc local checks.

## How it works

```
parsers/        terraform plan json + .tf static + ADK Python AST + gcloud shell
   ↓
catalog/        100 curated IaC kinds → permissions, cross-checked against 13.4k+ live GCP perms
   ↓
gcp/            testIamPermissions against the deployer SA via ADC
   ↓
recommender/    deterministic greedy set-cover over 2.3k+ predefined roles + Gemini justification
   ↓
reviewer/       Gemini-composed PR review body + deterministic inline comments
```

Gemini is **off the correctness path**. The math is the math; the LLM only writes prose. If Vertex is unreachable, a templated fallback ships the same information slightly drier.

## Quick start — GitHub Action

Add 6 lines to your workflow after `terraform plan`:

```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
    service_account: deployer@my-proj.iam.gserviceaccount.com

- run: terraform plan -out=plan.tfplan && terraform show -json plan.tfplan > plan.json

- uses: iam-legend/iam-legend@v1
  with:
    terraform-plan: plan.json
    project-id: my-proj
```

The Action runs as the deployer SA (because `google-github-actions/auth` ran first), so `testIamPermissions` answers for the principal that actually runs `terraform apply`. No extra secrets, no service-account keys.

## Quick start — MCP server (local)

```bash
pip install iam-legend
```

Then add to your MCP client config (Claude Code, Gemini CLI, Cursor):

```json
{
  "mcpServers": {
    "iam-legend": {
      "command": "iam-legend-mcp"
    }
  }
}
```

The local stdio server runs as your shell user — `gcloud auth application-default login` once and live IAM diff just works. Hosted Cloud Run instances run in **read-only mode** (no live IAM, no auto-plan) by design; see "Security" below.

## CLI

```bash
iam-legend lookup google_storage_bucket          # what perms does this resource need?
iam-legend lookup roles/run.admin                # what's in this role?
iam-legend review --plan plan.json --project my-proj
iam-legend refresh-catalog --what all            # pull fresh GCP roles + perms catalogs
```

## Catalog coverage (MVP)

- **2,324** predefined GCP roles (full catalog from `iam.roles.list`)
- **13,397** distinct IAM permissions (derived from the same source)
- **100** curated IaC kinds (~45 Terraform `google_*` resources, ~25 ADK / Vertex / Gemini Enterprise SDK calls, ~30 gcloud verbs)
- **Refresh**: weekly via `catalog_build/refresh_roles.py` + `catalog_build/refresh_api_methods.py`

## Security

- **Local stdio MCP**: runs as you. Full toolset including live IAM diff. Uses your existing ADC.
- **Hosted Cloud Run MCP**: runs as a credential-less SA. Static analysis only (catalog lookups, set-cover, recommender on submitted text). **Does NOT accept user GCP tokens via tool arguments** — that would leak them in transcripts, and no MCP client today reliably implements header-based passthrough. Don't trust hosted instances with live diff.
- **GitHub Action**: runs as the deployer SA. Same ADC mechanism as local stdio.

## Honest limitations

- Catalog covers ~100 IaC kinds. Anything outside that surfaces a visible warning on the review (no silent drops).
- Terraform registry modules require `terraform init` for static-mode scanning; CI-mode reads plan JSON which always has them resolved.
- Gemini Flash calls add latency to the review (~1-2s) and cost (~free at this volume on Vertex). Both fail-soft.
- We post review prose via the GitHub API; failure to post results in a workflow annotation + non-zero exit (fail closed on signalling failure, fail open on prose generation).

## Architecture

See `docs/architecture.png` for the diagram. Full design spec at `docs/superpowers/specs/2026-05-28-iam-legend-design.md`. Implementation plan at `docs/superpowers/plans/2026-05-28-iam-legend-implementation.md`.

## License

Apache-2.0. Catalog data derived in part from [Pike](https://github.com/JamesWoolfenden/pike) (Apache-2.0); attribution in `NOTICE`.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

54 tests, ~1.5 seconds.

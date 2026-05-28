# iam-legend

GCP IAM toolbelt for AI agents and CI pipelines. Reads Terraform / ADK / gcloud
code and answers "what IAM does this need?" — as an MCP server, a CLI, and a
GitHub Action that posts AI code reviews on PRs.

See `docs/superpowers/specs/2026-05-28-iam-legend-design.md` for the design.

## Install (dev)

```
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

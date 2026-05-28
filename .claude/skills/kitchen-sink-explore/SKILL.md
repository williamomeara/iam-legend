---
name: kitchen-sink-explore
description: "Autonomous exploratory testing for iam-legend. Probes catalog gaps, parser edge cases, MCP tool responses, and the throwaway-PR-review flow looking for things the unit tests can't catch. Self-improving."
user-invocable: true
argument-hint: "[--quick | --full | --focused <area> | --generate-tests]"
allowed-tools: Read, Bash, Glob, Grep, Agent, Skill
---

# kitchen-sink-explore — iam-legend

Project root: `/Users/williamomeara/Dev/google-cloud-for-startups/iam-legend`.

## Critical Execution Rules

1. **Read `patterns.md` BEFORE doing anything.** It encodes what's already been explored and what to skip.
2. **Depth before breadth.** When you find a suspicious area (a parser that returns weird output, a catalog gap, an MCP tool that misbehaves), dig until you understand it — don't just note it and move on.
3. **For every probe: capture the input, the output, and a one-line judgement.** No "looked at it." Either it's correct, it's wrong, or it's surprising-but-explainable.
4. **Prefix any data you create with `iam-legend-explore-`** so cleanup is easy.
5. **Never silently degrade.** If a probe needs ADC and ADC is missing, SKIP and say so — don't fabricate.

## Step 0: Parse Mode & Readiness

```bash
cd /Users/williamomeara/Dev/google-cloud-for-startups/iam-legend
source .venv/bin/activate
which iam-legend iam-legend-mcp pytest
gcloud auth print-access-token >/dev/null 2>&1 && echo "ADC OK" || echo "no ADC — live probes will SKIP"
```

Mode flags:
- `--quick` → charters 1, 2 only (~5 min)
- `--full` → all charters (~15-20 min)
- `--focused <area>` → run only the charter matching `<area>` (e.g. `--focused parsers`, `--focused catalog`, `--focused mcp`, `--focused review-flow`)
- `--generate-tests` → on finishing, write failing tests for each "wrong" finding into `tests/exploratory/`

## Step 1: Load Context

Read these files to ground the exploration:
- `docs/superpowers/specs/2026-05-28-iam-legend-design.md` — the design intent
- `src/iam_legend/catalog/resources.yaml` — what we claim to cover
- `src/iam_legend/parsers/adk_call_signatures.yaml` — the ADK call surface
- Previous `patterns.md` findings — don't re-explore solved areas

## Step 2: Seeding (throwaway test artefacts)

For the review-flow charter, seed a throwaway git repo under `/tmp/iam-legend-explore-<timestamp>/`. Use real-looking Terraform + ADK Python.

```bash
STAMP=$(date +%s)
SEED=/tmp/iam-legend-explore-$STAMP
mkdir -p "$SEED"
trap "rm -rf $SEED" EXIT
```

Populate with:
- A `terraform/main.tf` that exercises 3-4 different `google_*` kinds (storage, run, pubsub, vertex)
- A `deploy.py` that calls a Vertex agent_engines.create AND a non-aliased SDK call (test both code paths in the ADK parser)
- A `scripts/setup.sh` with a known gcloud verb
- A pre-generated `plan.json` (because real `terraform plan` requires auth + a project)

## Step 3: Page Audit Routine

For a CLI/server project, "page audit" reframes as **probe audit**. For every probe:

1. **Input snapshot** — exactly what was sent (command line, MCP request body, file content)
2. **Output snapshot** — exactly what came back (stdout/stderr, MCP response JSON, exit code)
3. **Console errors** — any logged warnings or exceptions
4. **Correctness judgement** — `OK` / `WRONG` / `SURPRISING-BUT-OK` (with one-line reason)
5. **Catalog impact** — did this expose a gap in `resources.yaml`, `api_methods.json`, or the signature map?

## Step 4: Charters

### Charter A — Catalog completeness

**Goal:** Find catalog gaps by feeding real-world IaC through the parsers.

1. **Pick 3 real GCP starter repos** from GitHub (e.g., `terraform-google-modules/cloud-run`, `GoogleCloudPlatform/terraform-google-examples`, an `adk-samples` repo). Clone shallow copies into the seed dir.
2. For each: run `iam-legend review --repo <dir> --format json` and inspect `warnings`. Every warning is a catalog gap.
3. Group warnings by `kind`. Anything appearing in ≥2 distinct repos is high-priority to add to `resources.yaml`.
4. Cross-check: if a kind is detected but unknown, also check whether the underlying perms exist in `api_methods.json` (they may be there but unlinked).

### Charter B — Parser edge cases

**Goal:** Hammer each parser with malformed/ambiguous inputs.

For each of the four parsers, run these probes and record:

**terraform_plan:**
- Empty `resource_changes` → should return `[]`, no crash
- `resource_changes` with only `no-op` actions → should return `[]`
- A `replace` action (`["delete","create"]`) — the implementation picks `create` first; verify this matches intent
- A `google_*` resource with action `["read"]` — should be ignored
- Unknown `google_x_y_z` kind → should appear in output with a warning at resolve time, not crash at parse time

**terraform_hcl:**
- `.tf` with syntax errors → should return `[]` not crash (try `resource "google_storage_bucket" "x" { )`)
- A resource with `count = 0` → currently parsed as a single occurrence; flag if this is wrong
- A `dynamic` block inside a resource → flag what gets emitted
- Module nesting depth 3 — does it recurse correctly?

**adk_python:**
- `import vertexai; vertexai.init(); del vertexai` (dynamic name removal) — verify the parser doesn't crash
- `from vertexai import agent_engines as ae; ae.create(); ae.create()` — verify two distinct detections
- Star imports: `from vertexai import *; agent_engines.create()` — currently the alias resolver won't catch this; confirm it falls through gracefully
- Conditional import: `if x: from vertexai import agent_engines` — both branches' bindings should accumulate

**gcloud_sh:**
- Comment-out a gcloud line: `# gcloud storage buckets create gs://x` — should NOT match (regex respects line boundaries but not comments; flag if this is a bug)
- Heredoc-embedded gcloud: `cat <<EOF\ngcloud run deploy\nEOF` — currently matches; flag whether this is desired
- Backslash-continued long command across two lines — does the line-by-line regex miss it?

### Charter C — MCP tool responses

**Goal:** Make sure the MCP server returns sensible structure under unusual inputs.

Start `iam-legend-mcp` stdio locally. For each tool:

- `analyze` with `kind="auto"` and a `.tf` path → does auto-detection pick HCL or fail?
- `analyze` with `kind="snippet"` → should error with NotImplementedError-equivalent, not crash
- `lookup_permissions_for("definitely-not-a-thing")` → should return `{"kind":"unknown",...}`, not raise
- `find_roles_with("storage.buckets.create")` → should return a non-empty list with `roles/storage.admin`
- `recommend_roles(permissions=[])` → empty input → empty `roles`, no crash
- `recommend_roles(permissions=["compute.instances.create"], avoid=["roles/owner","roles/editor","roles/viewer","roles/iam.securityAdmin","roles/compute.admin","roles/compute.instanceAdmin","roles/compute.instanceAdmin.v1"])` → should return some smaller role or admit it can't cover
- `generate_grant_commands(roles=[], project="p", principal="x@y")` → empty roles → empty commands

Confirm against the live Cloud Run instance too — privileged tools (`test_permissions`, `get_iam_policy`) must NOT appear in `tools/list`.

### Charter D — Throwaway PR-review flow (the hero demo)

**Goal:** Walk the full path that the GitHub Action will follow, locally, end-to-end.

1. Create the throwaway repo (Step 2).
2. Run `iam-legend review --plan plan.json --project tendermatch-prod --format json` against it.
3. Inspect the JSON output for: completeness, sensible role choices, correct grant commands, plausible access-request draft.
4. Manually render the PR review markdown (using `iam_legend.reviewer.format.format_review` with the Gemini fallback forced on for determinism) and ask:
   - Does it read like something a maintainer would accept?
   - Are inline comments anchored to plausible lines?
   - Are the role recommendations sensible? Any over-broad ones?
   - Is the access-request body something you'd actually paste to your platform team?
5. **Now flip one perm to "already granted"** in the live IAM state mock and re-run. The review should switch from REQUEST_CHANGES to a smaller missing-list (or APPROVE if everything is granted). Verify this transition is clean.
6. **Pretend `GITHUB_TOKEN` is set but PR posting fails** (mock by pointing `--repo-full-name` at a non-existent repo). Confirm the CLI exits non-zero with a `::error::` annotation (fail-closed on signalling per spec §8.5).

### Charter E — Failure modes

**Goal:** Exercise the failure paths the unit tests mock out.

- Kill ADC (`unset GOOGLE_APPLICATION_CREDENTIALS; gcloud auth application-default revoke`) and run `iam-legend review --plan plan.json --project x`. The review should still print, with `live IAM diff unavailable` in warnings.
- Point at a project the caller doesn't have access to (`--project some-random-stranger-project-9999`). Should warn cleanly, not crash.
- Provide a plan.json with `resource_changes: null` instead of `[]` — verify graceful handling.

## Step 5: Generate Tests (if --generate-tests)

For every `WRONG` or `SURPRISING-BUT-OK-that-might-bite-us` finding, write a failing test into `tests/exploratory/test_<area>.py`. Use clear `# Found by kitchen-sink-explore on YYYY-MM-DD` comments. Don't fix the underlying issue — that's a separate task.

## Step 6: Learn & Update Patterns

Append findings to `.claude/skills/kitchen-sink-explore/patterns.md`. Three sections to update:

1. **Known Issues** — `WRONG` findings with reproduction steps
2. **Surprising-but-OK Notes** — behaviour that's intentional but counter-intuitive
3. **Catalog Gaps** — kinds/perms that appeared in warnings during exploration

## Step 7: Summary

Print:
```
Charters run: A, B, C, D, E
Probes total: N
Findings: X WRONG, Y SURPRISING, Z OK
Catalog gaps found: K
Tests generated: M (if --generate-tests)
```

## Step 8: Cleanup

```bash
rm -rf /tmp/iam-legend-explore-*
```

---
name: ux-explorer
description: "Developer-UX review for iam-legend. There's no GUI — UX here is the CLI output, the PR-review markdown that maintainers will read, the MCP tool docstrings that LLMs will consume, and the README that hackathon judges will skim. Self-improving."
user-invocable: true
argument-hint: "[--persona <name>] [--surface cli|review|mcp|readme|all] [--quick]"
allowed-tools: Read, Bash, Glob, Grep, Agent
---

# ux-explorer — iam-legend

Project root: `/Users/williamomeara/Dev/google-cloud-for-startups/iam-legend`.

## Purpose

iam-legend has no web UI. But it has **four developer-facing surfaces** whose UX matters more than you'd think for a hackathon submission:

1. **The CLI output** (`iam-legend lookup`, `iam-legend review` in pretty mode). What does the developer see in their terminal?
2. **The PR review markdown** that gets posted on GitHub. The maintainer reading the review is the customer; if the markdown is confusing or condescending, they won't adopt the tool.
3. **The MCP tool docstrings**. These are the LLM-facing UX. A weak docstring makes Gemini/Claude pick the wrong tool or call it with wrong args.
4. **The README + design spec + Devpost description**. The hackathon judge will skim these in 30 seconds. The submission lives or dies on whether the first paragraph lands.

A design critic, not a bug-finder. Ask: *would a stranger pick this up and feel competent in 60 seconds?*

## Self-Improvement

**Read `.claude/skills/ux-explorer/patterns.md` first.** It encodes what's already been reviewed, what suggestions were accepted, and what the user explicitly rejected (so we don't keep re-proposing them).

After the run, update patterns.md with: accepted suggestions (so future runs respect those choices), rejected suggestions (so they aren't re-proposed), and surface-specific notes.

## Execution Rules

- Take a "screenshot" (a captured exact output) of every surface reviewed. No paraphrasing.
- Stay in persona — read each surface as the persona who will encounter it.
- Note the emotional state, not just the bug ("a maintainer who's tired and skimming would miss X").
- Don't fix anything yet — collect suggestions, present them, then implement after sign-off.
- Be specific. "The CLI output looks crowded" is useless. "The grant commands section uses 4 lines per command which means a 3-role grant takes 12 lines and pushes the summary above the fold" is useful.

## Suggestion Categories

- **Clarity** — does the surface say what it means?
- **Hierarchy** — is the most important thing visually most prominent?
- **Efficiency** — can the reader find what they need in under 5 seconds?
- **Feedback** — does the surface react sensibly to weird input?
- **Consistency** — same concept named the same way across surfaces?
- **Confidence** — does the surface feel like a product or like a script?
- **LLM-friendliness** — for MCP tools: would an LLM call this correctly from the docstring alone?
- **Skim-ability** — for README/spec: does a 30-second skim leave the right impression?
- **Trustworthiness** — does the output look like something I'd act on without double-checking?

## Suggestion Format

For every finding:
```
[P1|P2|P3|P4]  [Category]
Surface: <where it appears, with file path or command>
Persona: <who'd hit this, in what mood>
Suggestion: <one paragraph>
Why it matters: <one paragraph>
Concrete proposal: <code/text patch or wireframe>
```

P1 = must fix before submission. P4 = nice-to-have.

## Step 0: Readiness

```bash
cd /Users/williamomeara/Dev/google-cloud-for-startups/iam-legend
source .venv/bin/activate
which iam-legend
```

## Step 1: Capture (no review yet — just capture all surfaces)

For each surface, write the captured output to `/tmp/iam-legend-ux/<surface>.txt` so the review pass can reference exact text.

### Surface A — CLI output (pretty mode)

```bash
mkdir -p /tmp/iam-legend-ux
iam-legend --version            > /tmp/iam-legend-ux/cli-version.txt 2>&1
iam-legend --help               > /tmp/iam-legend-ux/cli-help.txt 2>&1
iam-legend lookup --help        > /tmp/iam-legend-ux/cli-lookup-help.txt 2>&1
iam-legend lookup google_storage_bucket           > /tmp/iam-legend-ux/cli-lookup-bucket.txt 2>&1
iam-legend lookup roles/storage.admin             > /tmp/iam-legend-ux/cli-lookup-role.txt 2>&1
iam-legend lookup storage.buckets.create          > /tmp/iam-legend-ux/cli-lookup-perm.txt 2>&1
iam-legend lookup totally-fake-thing-99999        > /tmp/iam-legend-ux/cli-lookup-unknown.txt 2>&1; true
iam-legend review --plan tests/fixtures/plan_json/simple.json > /tmp/iam-legend-ux/cli-review-pretty.txt 2>&1
iam-legend review --plan tests/fixtures/plan_json/simple.json --format json > /tmp/iam-legend-ux/cli-review-json.txt 2>&1
```

### Surface B — PR-review markdown

Render the templated fallback (deterministic) and, if Vertex Gemini is reachable, also the Gemini-generated version. Diff them.

```bash
python - <<'PY' > /tmp/iam-legend-ux/review-markdown-template.txt
from unittest.mock import patch
from iam_legend.analyze import analyze
from iam_legend.reviewer.format import format_review
from iam_legend.gcp.auth import who_am_i

with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("force fallback")), \
     patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("force fallback")):
    report = analyze("tests/fixtures/plan_json/simple.json", kind="plan_json", project=None)
    pl = format_review(report, deployer="deployer@my-proj.iam.gserviceaccount.com")
print("EVENT:", pl.event)
print()
print(pl.body)
print()
print(f"--- {len(pl.comments)} inline comments ---")
for c in pl.comments:
    print()
    print(f"@@ {c.file}:{c.line} @@")
    print(c.body)
PY
```

Try the same WITHOUT mocking Gemini (write to `/tmp/iam-legend-ux/review-markdown-gemini.txt`). May fail if Vertex isn't configured — that's fine, note it.

### Surface C — MCP tool docstrings

Capture them as the LLM will see them:

```bash
python - <<'PY' > /tmp/iam-legend-ux/mcp-tool-docstrings.txt
import asyncio
from iam_legend.mcp_server import build_server
srv = build_server()
# Use whichever tool-listing API the mcp SDK exposes
tools = list(srv._tool_manager.list_tools())
for t in tools:
    print(f"--- {t.name} ---")
    print(f"description: {t.description}")
    print(f"inputSchema:")
    import json
    print(json.dumps(t.inputSchema, indent=2))
    print()
PY
```

### Surface D — README + spec

```bash
cp README.md                                         /tmp/iam-legend-ux/readme.md
cp docs/superpowers/specs/2026-05-28-iam-legend-design.md /tmp/iam-legend-ux/spec.md
```

## Step 2: Review with personas

For each persona below, walk every surface in `/tmp/iam-legend-ux/` and write suggestions in the format above. Stay in character.

### Persona 1 — The hackathon judge (Avery)

- 30 seconds per project. Skimming the Devpost page + README + watching the 90-second video.
- Looking for: clear problem statement, evidence of working code, sensible architecture diagram, MCP usage (Track 1 thesis), business case.
- Won't read the code. Won't try the CLI. Will scroll the README and click ONE link if intrigued.
- **Surfaces to review:** README, spec doc (first 100 lines), and the video script in the spec.
- **Lens:** would they remember this 10 minutes after watching, or blur it with the other 600 submissions?

### Persona 2 — The platform engineer (Sam)

- Tired Senior SRE at a mid-sized company. Burned by tools before. Will install nothing without a 60-second proof.
- Most likely to actually adopt the GitHub Action.
- **Surfaces to review:** README quick-start sections, the example `.github/workflows/deploy.yml`, the rendered PR-review markdown.
- **Lens:** when they see the review markdown on a PR for the first time, do they (a) trust it, (b) feel patronised, (c) ignore it? The difference between (a) and (c) is whether they roll it out to the whole org.

### Persona 3 — The PR author (Devon)

- Junior-mid engineer. Opened a PR adding a Vertex Agent Engine. iam-legend just posted "Changes requested." They've never heard of this bot.
- **Surfaces to review:** the rendered PR-review markdown, specifically the inline comments and the access-request draft.
- **Lens:** do they know what to do next? Will they paste the gcloud commands or ping their platform lead? Will they feel blamed or guided?

### Persona 4 — The LLM (Gemini-or-Claude-as-MCP-client)

- The MCP host LLM. Sees only `tools/list` output and the user's natural-language question.
- **Surface to review:** the MCP tool docstrings.
- **Lens:** Given a question like "what perms does this Vertex agent need?", does the LLM pick `analyze`, `lookup_permissions_for`, or `recommend_roles`? Are arg schemas unambiguous? Would the LLM hallucinate an arg that doesn't exist?

### Persona 5 — The first-time CLI user (Pat)

- Pip-installed iam-legend on a laptop, ran `iam-legend` with no args. Now what?
- **Surfaces to review:** `--help`, `lookup --help`, the pretty-mode `review` output.
- **Lens:** is the first 30 seconds of interaction reassuring or confusing? Does `iam-legend lookup unknown-thing` produce a helpful error or a stack trace?

## Step 3: Compile & Prioritise

Dedupe across personas — multiple personas hitting the same issue raises its priority. Group findings by surface, then by priority. Print a single ranked list.

Example output shape:
```
PRIORITY 1 (must-fix before submission)
─────────────────────────────────────────
1. [CLI/review] Pretty-mode "Warnings:" section shows raw resource kinds — Devon (PR author) won't understand "vertex.agent_engine_create"; should say "Vertex Agent Engine deploy"
   Concrete fix: ...

PRIORITY 2
──────────
3. [MCP/docstring] analyze's `kind` parameter docstring lists values without explaining auto-detection rules — Gemini will hesitate
   Concrete fix: ...

...
```

## Step 4: Review session

Present the suggestion list to the user. For each P1+P2 suggestion, ask:
- "Implement now?" (yes / no / discuss)

Record decisions in patterns.md immediately so future runs honour them.

## Step 5: After review

Implement all "yes" suggestions. After each, re-capture the corresponding surface so before/after is on record.

## Step 6: Learn & Update Patterns

Append to `.claude/skills/ux-explorer/patterns.md`:
- **Accepted Suggestions** with surface + what changed
- **Rejected Suggestions** with reason (so we don't propose them again)
- **Persona-specific Notes** (e.g., "Avery doesn't read past line 30 of README")
- **Page Quality Notes** (per surface, current quality score: rough / acceptable / good / excellent)

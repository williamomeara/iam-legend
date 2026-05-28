# ux-explorer Patterns — iam-legend

Accumulated developer-UX learnings. Read before each run; update at end.

## Design Principles (project-specific)

- **The review markdown is the product.** If a maintainer doesn't act on it within 5 seconds, the tool failed. Optimise it ruthlessly.
- **The first paragraph of the README is the submission.** Hackathon judges skim. The hook has to land in 3 lines.
- **MCP tool docstrings are LLM UX, not human UX.** Write for a model picking between 8 tools, not for a developer reading docs.
- **CLI emoji budget: ≤1 per top-level message.** ✅ / 🚫 in the verdict line only. Anywhere else feels gimmicky.
- **Honesty over polish.** When the tool doesn't know something (catalog gap, uncovered perm), say so plainly. Trustworthiness > smoothness.

## Known UX Issues

*(None recorded yet — first run will populate.)*

## Persona-Specific Notes

- **Avery (hackathon judge)**: highest leverage surface = README first paragraph + the 90-second video. They will not read the spec.
- **Sam (platform engineer)**: highest leverage surface = the example workflow YAML. If it looks like 50 lines of config, they bounce.
- **Devon (PR author)**: highest leverage surface = the access-request draft. They will literally copy-paste this to Slack.
- **LLM persona**: highest leverage surface = `analyze` tool's docstring. It's the workhorse — if its description is weak, the LLM under-uses it.
- **Pat (CLI first-timer)**: highest leverage surface = `iam-legend --help` and behaviour on no-args/unknown-arg.

## Accepted Suggestions

*(Empty — will populate.)*

## Rejected Suggestions

*(Empty — will populate. Important: re-proposing rejected suggestions is the #1 way this skill annoys the user. Don't.)*

## Page (Surface) Quality Notes

| Surface | Current quality | Last reviewed |
|---|---|---|
| CLI: `iam-legend lookup` pretty output | unreviewed | — |
| CLI: `iam-legend review` pretty output | unreviewed | — |
| PR review markdown (templated fallback) | unreviewed | — |
| PR review markdown (Gemini-generated) | unreviewed | — |
| MCP tool docstrings | unreviewed | — |
| README (root) | rewritten 2026-05-28 by Claude — needs persona-driven review | 2026-05-28 |
| Design spec | unreviewed (probably "good" — design doc audience is small) | — |
| Example workflow YAML | unreviewed | — |

## Known Constraints (Don't Suggest These)

- **No Rich progress bars** in CLI output — `rich.progress` doesn't play well with pipe redirection (`iam-legend review --format json > x.json`). Tables and Panels only.
- **No clickable links in PR review markdown** — GitHub's PR comment renderer doesn't auto-link arbitrary URLs in code fences. Keep grant commands in `bash` fences and link them out-of-band.
- **No prompts in the GitHub Action** — Actions don't have a TTY; never use Click confirmations.

## Run History

*(Entries appended after each run.)*

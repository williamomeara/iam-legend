# iam-legend Polish Plan (Phase 2 — post-validation)

> Submission deadline: **2026-06-05 PT** (8 days from 2026-05-28).
> Demo recording deliberately deferred to the very end.

Builds on the original implementation plan (`2026-05-28-iam-legend-implementation.md`). All 22 core tasks from that plan are complete; this plan covers the remaining work surfaced by real-world validation against Google's `agent-starter-pack` and an initial live PR posting.

## Goals (in priority order)

1. Make Gemini *actually fire* in the GitHub Action runtime (currently always falls back to template)
2. Move the recommender from "set-cover picks → Gemini explains" to "set-cover proposes → Gemini picks" (matches spec §7.4 intent; eliminates `roles/iam.databasesAdmin` for non-database perms class of bug)
3. Broaden catalog validation to all 6 official Google ADK starter templates
4. Polish judge-facing surfaces (README, architecture diagram, Devpost answers)
5. Defensive robustness pass — regression tests, kitchen-sink smoke

---

## Phase 1 — Gemini in production (~1.5 hr) — HARD PREREQUISITE for Phase 2

The deployer SA in the demo workflow can't call Vertex Gemini today, so `_call_gemini()` always raises and the templated fallback fires. Fix:

- **1A.** Grant `roles/aiplatform.user` to `iam-legend-demo-deployer@tendermatch-prod` (5 min)
- **1B.** Add `VERTEX_PROJECT` and `VERTEX_LOCATION` env vars to `action.yml`'s container env. The deployer SA is already auth'd via WIF; setting these env vars activates the Gemini code path. (30 min)
- **1C.** Add a `model` input to `action.yml` (defaults to `gemini-flash-latest`); thread through `docker-entrypoint.sh` (15 min)
- **1D.** Update `docker-entrypoint.sh` to set `VERTEX_MODEL` env var from input (5 min)
- **1E.** Tag `v0.1.1` (clean tag, don't force-move `v0.1.0`). Update demo workflow to `@v0.1.1`. (10 min)
- **1F.** Smoke-test: open a fresh empty commit on the demo PR, confirm the resulting review is Gemini-written, not templated (15 min)
- **1G.** Update the hosted Cloud Run MCP service to the new image (5 min)

## Phase 2 — Hybrid recommender (~5 hr)

Spec §7.4 intent: set-cover proposes 3-5 candidate role bundles → Gemini picks the best one with context → catalog-verification fallback in case of hallucination.

- **2A.** Refactor `recommender/set_cover.py` (1.5 hr). New shape: `cover()` returns `RoleCandidates` with `alternatives: list[list[str]]` populated with top-N (default 5) candidate bundles, ranked by deterministic score. Each candidate annotated with metadata (role count per bundle, perms-covered, perms-wasted, service-prefix breakdown).
- **2B.** Rewrite `recommender/justify.py` → `recommender/recommend.py` (1.5 hr). New flow:
  - Input: required permissions + set-cover candidates with metadata
  - Send to Gemini with structured prompt: "Pick the best bundle. Forbidden patterns: `*ServiceAgent`, `*MigrationAdmin`, `*databasesAdmin` (unless Spanner/Datastore perms requested), roles/owner/editor/viewer. Prefer per-service roles. Surface concerning grants."
  - Output: chosen bundle index + reasoning
- **2C.** Catalog-verification + fallback (45 min). After Gemini picks, verify every recommended role exists in `roles.json` and the union of their perms ≥ required perms. If verification fails (hallucination), fall back to set-cover's top-ranked candidate and log a warning.
- **2D.** Tests (1 hr):
  - Unit: hallucination → fallback path
  - Unit: catalog grounding (LLM can't pick non-existent roles)
  - Integration: against Google sample fixtures, assert no `iam.databasesAdmin` for non-spanner perms
- **2E.** Re-validate against the 3 ADK samples; confirm sensible role choices (30 min)

## Phase 3 — Catalog breadth (~2 hr)

Headline claim worth making: "Validated against all 6 official Google ADK starter templates."

- **3A.** Generate `adk_a2a`, `adk_go`, `adk_java`, `adk_ts` starter projects via `uvx agent-starter-pack create` (20 min)
- **3B.** Run `iam-legend review --repo <each>` and capture catalog gaps (30 min)
- **3C.** Add missing resource entries to `catalog/resources.yaml` and any missing perms to `api_methods.json` (1 hr)
- **3D.** Add regression test asserting 0 catalog gaps across all 6 samples (15 min)

## Phase 4 — Submission packaging (~3.5 hr)

Judge-facing surfaces. Direct Demo + Technical impact.

- **4A.** Architecture diagram in Excalidraw → `docs/architecture.png` (1 hr)
- **4B.** Rewrite `README.md` to lead with validated stats + deployed URLs (1 hr):
  - "Validated against all 6 official Google ADK templates: 0 catalog gaps"
  - "Live deployment: <Cloud Run URL>"
  - "Live demo PR: <iam-legend-validation-demo/pull/1 URL>"
  - 3-line pitch above the fold
- **4C.** Polish demo PR description on iam-legend-validation-demo (15 min)
- **4D.** Fill all 5 Devpost submission question answers (30 min) — including the AI Studio rating left blank in the spec, and update the others with post-validation reality
- **4E.** Update the spec doc with the as-built state — catalog counts, deployed URLs, post-validation findings recorded as a §12 "Validation Outcomes" appendix (45 min)

## Phase 5 — Robustness + smoke (~2 hr)

Reduces blow-up risk during demo recording.

- **5A.** Regression tests for the new resource entries added during validation: `google_vertex_ai_reasoning_engine`, `google_service_account`, `google_service_account_iam_member`, WIF resources, `google_discovery_engine_search_engine` (45 min)
- **5B.** Run `/kitchen-sink --full` and address any surfacing issues (45 min)
- **5C.** Verify deployed Cloud Run answers after re-deploy with the new image (15 min)
- **5D.** Verify the live demo PR workflow still works end-to-end after all upstream changes (15 min)

## Phase 6 — Pre-recording final polish (~1 hr)

Night-before-the-video work.

- **6A.** Open a second demo PR that **modifies an existing `.tf` line** so inline comments land in the diff and aren't dropped — makes for the cleanest demo shot (15 min)
- **6B.** Pre-warm Cloud Run (1 dummy request) before recording (5 min)
- **6C.** Final typo/clarity pass on README, demo PR, Devpost answers (40 min)

## Phase 7 — Demo recording (DEFERRED to the very end)

90 seconds. Architecture diagram → MCP demo → live PR review → close. Recorded after everything above is locked.

---

## Total effort

| Phase | Hours | Cumulative |
|---|---|---|
| 1. Gemini in Action | 1.5 | 1.5 |
| 2. Hybrid recommender | 5 | 6.5 |
| 3. Catalog breadth | 2 | 8.5 |
| 4. Submission packaging | 3.5 | 12 |
| 5. Robustness + smoke | 2 | 14 |
| 6. Pre-recording polish | 1 | 15 |

~15 hours of focused work. ~2 workdays. Deadline gives 8 days. Comfortable margin.

## Sequencing constraints

- **Phase 1 → Phase 2:** hard dependency (Phase 2's hybrid recommender requires Phase 1's Vertex access)
- **Phases 3, 4, 5:** independent of each other after Phase 2; can run in parallel via subagents
- **Phase 6:** requires everything above
- **Phase 7:** explicitly deferred

## Cut order (if time tightens)

In order:
1. Phase 6A (open second demo PR) — first demo PR already works
2. Phase 5A (regression tests for new entries) — nice-to-have
3. Phase 3 items 3-4 (skip Java/Go/TS validation)
4. Phase 2C (skip explicit hallucination fallback; trust Gemini + log warnings only)

## What I will NOT cut under any circumstance

- Phase 1 (Gemini in production) — single biggest rubric lever
- Phase 4B + 4D (README + Devpost answers) — judges' first impression
- Phase 2A + 2B (hybrid recommender) — the spec said we'd do this

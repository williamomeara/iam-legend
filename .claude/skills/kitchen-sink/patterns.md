# kitchen-sink Patterns — iam-legend

Accumulated learnings from runs. **The skill MUST read this file before each run, and MUST update it when new patterns are discovered.**

## Environment Notes

- **Venv lives at `.venv/`** at the project root. Always `source .venv/bin/activate` before running any pytest/iam-legend invocation.
- **Python 3.14.4 in use** (uv picked up the only `>=3.13` interpreter on the box). Constraint says `>=3.13` so 3.14 is fine.
- **ADC** is on `william@tendermatch.ie` → project `tendermatch-prod`. If `gcloud auth print-access-token` fails, Layers 11 and the live-diff path in Layer 12 will SKIP — that's expected, not a failure.
- **Docker daemon often not running** on this dev machine. Layer 8 SKIPs rather than fails when `docker info` errors out.
- **Cloud Run live URL:** `https://iam-legend-372139006998.us-central1.run.app` (project `tendermatch-prod`). Update here if redeployed elsewhere.

## Known Flaky Tests

*(None yet — populate after first false-positive run.)*

## False Positives

- `pytest --collect-only` returns exit code **5** ("no tests collected") on an empty test dir. This is correct pytest behaviour, NOT a failure. The plan text said "exit 0" — that was wrong. Treat exit 5 from `--collect-only` as success when tests are absent.

## Common Failure Patterns

- **`who_am_i()` returns `"unknown-principal"` for user ADC** (not service-account ADC). User credentials don't expose a stable email attr on `google.auth.default()`. Functional for the SA path; informational for the user path. Don't treat this as a failure.
- **Gemini fallback path activates silently** when Vertex isn't reachable. You can tell it's the templated fallback because the prose starts with `"Recommended roles: ..."`. The non-fallback path returns Gemini-generated prose. Recording this so future runs can distinguish.

## Catalog Baseline (from first successful run on 2026-05-28)

- Roles in `roles.json`: **2,324**
- Permissions in `api_methods.json`: **13,397** (including 3 manually appended: `aiplatform.reasoningEngines.deploy`, `cloudbuild.builds.delete`, `spanner.databases.delete`)
- Curated entries in `resources.yaml`: **100**

If any of these drop substantially between runs, investigate before passing the layer.

## Layer 12 (--review-flow) Notes

- We deliberately fabricate the plan.json instead of running real `terraform plan` because the demo-repo requires `var.project_id` and a Google provider auth context the test environment may not have.
- The mocked Gemini fallback in the rendering test is intentional — it makes the markdown deterministic across runs regardless of whether Vertex is reachable.
- Known oddity: when no live diff happens (no `--project` or ADC unavailable), the recommender may suggest `roles/cloudbuild.builds.builder` to cover storage.objects.* perms. Technically correct but a poor security recommendation. This is a catalog/recommender limit, not a bug. A follow-up could weight against roles that cover perms via unrelated functions.

## Performance Baselines

- `pytest -q` (54 tests): ~2.5–3.0s
- `iam-legend lookup google_storage_bucket`: ~0.5s
- Cloud Run cold start (Layer 11 first call): ~3–5s; warm ~150ms
- Docker build via Cloud Build (`gcloud run deploy --source .`): ~3–5 minutes

## Run History

*(Entries appended after each run.)*

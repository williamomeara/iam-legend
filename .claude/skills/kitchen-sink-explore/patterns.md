# kitchen-sink-explore Patterns — iam-legend

Accumulated learnings. Read before each run; update at end.

## Known Issues

*(None yet — first exploration pass will populate this.)*

## Surprising-but-OK Notes

- **`who_am_i()` returns `"unknown-principal"` for user ADC** (not service-account ADC). This is by design — user creds don't expose a stable email attr on `google.auth.default()`. Intentional, but feels broken on first encounter.
- **The HTTP MCP transport hides privileged tools from `tools/list`.** This is the spec §8.2 security model, not a bug. If a probe finds `test_permissions` on the hosted server, THAT is the bug.
- **`recommend_roles` may pick weird-but-technically-correct roles** like `roles/cloudbuild.builds.builder` to cover `storage.objects.*` perms. The set-cover greedy is right; the *security* judgement is poor. Gemini is supposed to filter these, but the fallback path doesn't. Flag as a follow-up if Gemini reliably fixes it.

## Catalog Gaps

*(Empty — Charter A will populate this from real-world repos.)*

Known not-in-any-predefined-role perms (so set-cover will report them as `uncovered`):
- `aiplatform.reasoningEngines.deploy`
- `cloudbuild.builds.delete`
- `spanner.databases.delete`

These were manually added to `api_methods.json` so resources.yaml could reference them, but no predefined role covers them. Don't be alarmed when they show up uncovered.

## Page-Specific Notes (Probe-Specific)

- **Charter B / terraform_hcl / `count = 0`**: untested. python-hcl2 represents this as a single dict; we currently emit one DetectedGCPResource. Whether that's right depends on Terraform semantics (count=0 means 0 instances, so 0 perms needed). Likely a bug; investigate first.
- **Charter B / adk_python / star imports**: the alias resolver only tracks `Import` and `ImportFrom`. A `from x import *` adds names to the local namespace that we don't track, so calls through them will fall through silently. Acceptable for MVP; flag in patterns.md if a real demo repo uses this pattern.

## Data Quality Patterns

- The catalog's `roles.json` is regenerated weekly. Don't be surprised if a role disappeared between runs — Google does deprecate roles occasionally.
- `api_methods.json` is derived from `roles.json` plus a 3-perm manual list. If a perm is in `resources.yaml` but missing from `api_methods.json`, the Layer 3 catalog cross-validation in kitchen-sink will catch it.

## Security Notes

- The hosted Cloud Run service at `https://iam-legend-372139006998.us-central1.run.app` is **--no-allow-unauthenticated**. Anonymous curl returns 403, which is correct. If a probe gets 200 without an auth header, raise the alarm — that means the IAM policy has been changed.

## Run History

*(Entries appended after each run.)*

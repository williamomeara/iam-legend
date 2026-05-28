#!/usr/bin/env bash
set -euo pipefail

MODE="${IAM_LEGEND_MODE:-mcp}"

case "$MODE" in
  mcp)
    exec iam-legend-mcp
    ;;
  action)
    plan="${INPUT_TERRAFORM_PLAN:-}"
    workdir="${INPUT_WORKING_DIRECTORY:-.}"
    project="${INPUT_PROJECT_ID:?project-id is required}"
    repo_full="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY not set}"

    # GitHub Actions exposes the event payload as a JSON file at
    # $GITHUB_EVENT_PATH. For pull_request events, .pull_request.number is
    # the PR id; for issue_comment events targeted at PRs, .issue.number is
    # the PR id. There's no single env var equivalent, so parse it.
    pr_number=""
    if [[ -n "${GITHUB_EVENT_PATH:-}" && -f "$GITHUB_EVENT_PATH" ]]; then
      pr_number=$(python3 -c "
import json, os, sys
try:
    e = json.load(open(os.environ['GITHUB_EVENT_PATH']))
    n = e.get('pull_request', {}).get('number') or e.get('number')
    if n: print(n)
except Exception:
    pass
" 2>/dev/null || true)
    fi

    # Fall back to GITHUB_REF parsing (refs/pull/N/merge -> N) for safety.
    if [[ -z "$pr_number" && "${GITHUB_REF:-}" =~ refs/pull/([0-9]+)/ ]]; then
      pr_number="${BASH_REMATCH[1]}"
    fi

    if [[ -z "$pr_number" ]]; then
      echo "::error title=iam-legend::could not determine PR number from event payload or GITHUB_REF" >&2
      exit 1
    fi

    args=(review --project "$project" --post-pr --pr-number "$pr_number" --repo-full-name "$repo_full")
    if [[ -n "$plan" && -f "$plan" ]]; then
      args+=(--plan "$plan")
    else
      if [[ -n "$plan" ]]; then
        echo "::warning title=iam-legend::plan file '$plan' not found; falling back to static repo scan"
      fi
      args+=(--repo "$workdir")
    fi

    # GitHub Actions sets GITHUB_TOKEN automatically only when actions/checkout
    # opted in; the iam-legend CLI's --post-pr flow expects $GITHUB_TOKEN.
    # The workflow's `permissions: pull-requests: write` enables this; the
    # token is exposed via GITHUB_TOKEN in the calling step's env, but
    # composite/docker actions don't inherit it automatically.
    # Surface a clean error if it's missing.
    if [[ -z "${GITHUB_TOKEN:-}" ]]; then
      echo "::warning title=iam-legend::GITHUB_TOKEN env var not set in the action's container; PR posting will fail. Set 'env: GITHUB_TOKEN: \${{ secrets.GITHUB_TOKEN }}' on the step calling iam-legend."
    fi

    exec iam-legend "${args[@]}"
    ;;
  *)
    echo "unknown IAM_LEGEND_MODE: $MODE" >&2
    exit 2
    ;;
esac

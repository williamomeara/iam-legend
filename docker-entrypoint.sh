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
    pr_number="${GITHUB_EVENT_NUMBER:-${GITHUB_EVENT_PULL_REQUEST_NUMBER:-}}"
    repo_full="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY not set}"

    args=(review --project "$project" --post-pr --pr-number "$pr_number" --repo-full-name "$repo_full")
    if [[ -n "$plan" ]]; then
      args+=(--plan "$plan")
    else
      args+=(--repo "$workdir")
    fi

    exec iam-legend "${args[@]}"
    ;;
  *)
    echo "unknown IAM_LEGEND_MODE: $MODE" >&2
    exit 2
    ;;
esac

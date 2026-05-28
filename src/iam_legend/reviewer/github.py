"""Post a ReviewPayload as a GitHub PR review via PyGithub.

Two real-world quirks the v0.1.0 release didn't account for:

1. PyGithub's create_review(commit=...) expects a Commit OBJECT, not a SHA
   string. Passing a string produces a confusing error where str(e) is just
   the SHA.

2. Inline comments anchored to file lines OUTSIDE the PR's diff are rejected
   by the GitHub API. iam-legend often emits inline comments on existing
   resources (not just lines the PR added), so a substantial fraction of
   the inline comments may fail.

This module tries with inline comments first; on failure it retries with
just the top-level body (which always works). Cleaner than dropping
comments preemptively — PRs that DO modify the relevant lines still get
the inline annotations.
"""
from __future__ import annotations

from typing import Any

from iam_legend.reviewer.format import ReviewPayload


def post_review(
    payload: ReviewPayload,
    repo: Any,
    pull_number: int,
    commit_sha: str | None = None,
) -> None:
    pull = repo.get_pull(pull_number)
    sha = commit_sha or pull.head.sha

    # PyGithub create_review wants a Commit object, not a SHA string.
    commit_obj = repo.get_commit(sha)

    comments = [
        {"path": c.file, "line": c.line, "body": c.body, "side": "RIGHT"}
        for c in payload.comments
    ]

    try:
        pull.create_review(
            commit=commit_obj,
            body=payload.body,
            event=payload.event,
            comments=comments,
        )
    except Exception as e:
        # Most common cause: inline comments anchored to lines that aren't
        # part of this PR's diff. Retry with the top-level body only — that
        # always works and still surfaces the verdict + grant commands.
        if comments:
            print(
                f"::warning title=iam-legend::inline comments rejected by GitHub "
                f"({e!r}); retrying with top-level review body only"
            )
            pull.create_review(
                commit=commit_obj,
                body=payload.body,
                event=payload.event,
            )
        else:
            raise

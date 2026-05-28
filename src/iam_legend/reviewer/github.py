"""Post a ReviewPayload as a GitHub PR review via PyGithub."""
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

    comments = [
        {"path": c.file, "line": c.line, "body": c.body, "side": "RIGHT"}
        for c in payload.comments
    ]

    pull.create_review(
        commit=sha,
        body=payload.body,
        event=payload.event,
        comments=comments,
    )

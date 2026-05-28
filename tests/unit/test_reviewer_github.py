from unittest.mock import MagicMock

from iam_legend.reviewer.format import InlineComment, ReviewPayload
from iam_legend.reviewer.github import post_review


def test_post_review_calls_create_review_with_correct_args():
    pl = ReviewPayload(
        event="REQUEST_CHANGES",
        body="changes requested",
        comments=[InlineComment(file="main.tf", line=12, body="grant x")],
    )
    repo = MagicMock()
    pull = MagicMock()
    repo.get_pull.return_value = pull
    pull.head.sha = "deadbeef"

    post_review(pl, repo, pull_number=42, commit_sha=None)

    pull.create_review.assert_called_once()
    kwargs = pull.create_review.call_args.kwargs
    assert kwargs["event"] == "REQUEST_CHANGES"
    assert kwargs["body"] == "changes requested"
    assert len(kwargs["comments"]) == 1
    c = kwargs["comments"][0]
    assert c["path"] == "main.tf"
    assert c["line"] == 12


def test_post_review_omits_comments_when_none():
    pl = ReviewPayload(event="APPROVE", body="all good", comments=[])
    repo = MagicMock()
    pull = MagicMock()
    repo.get_pull.return_value = pull
    pull.head.sha = "deadbeef"
    post_review(pl, repo, pull_number=1, commit_sha=None)
    kwargs = pull.create_review.call_args.kwargs
    assert kwargs.get("comments") in ([], None) or len(kwargs.get("comments", [])) == 0

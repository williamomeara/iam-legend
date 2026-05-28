from iam_legend.catalog.loader import load_catalog
from iam_legend.recommender.set_cover import cover


def test_single_role_covers_all():
    c = load_catalog()
    res = cover({"storage.buckets.create", "storage.buckets.delete"}, c)
    assert "roles/storage.admin" in res.chosen or len(res.chosen) == 1


def test_owner_is_never_chosen():
    c = load_catalog()
    res = cover({"storage.buckets.create"}, c)
    assert "roles/owner" not in res.chosen
    assert "roles/editor" not in res.chosen


def test_empty_input_returns_empty():
    c = load_catalog()
    res = cover(set(), c)
    assert res.chosen == []


def test_uncoverable_perm_returns_warning():
    c = load_catalog()
    res = cover({"definitely.not.a.permission"}, c)
    assert "definitely.not.a.permission" in res.uncovered

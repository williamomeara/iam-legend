from iam_legend.catalog.loader import load_catalog, Catalog


def test_load_catalog_returns_catalog_object():
    c = load_catalog()
    assert isinstance(c, Catalog)
    assert len(c.roles) > 0
    assert len(c.api_methods) > 0
    assert len(c.resources) > 0


def test_catalog_lookup_resource():
    c = load_catalog()
    perms = c.lookup_resource("google_storage_bucket", "create")
    assert "storage.buckets.create" in perms


def test_catalog_lookup_unknown_returns_none():
    c = load_catalog()
    perms = c.lookup_resource("google_nonexistent_xyz", "create")
    assert perms is None


def test_catalog_lookup_role():
    c = load_catalog()
    role = c.lookup_role("roles/storage.admin")
    assert role is not None
    assert "storage.buckets.create" in role["permissions"]

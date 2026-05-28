from iam_legend.catalog.loader import load_catalog


def test_every_permission_exists_in_api_methods():
    c = load_catalog(reload=True)
    misses: list[str] = []
    for kind, ops in c.resources.items():
        for op, perms in ops.items():
            if op == "required_apis":
                continue
            if not isinstance(perms, list):
                continue
            for p in perms:
                if p not in c.api_methods:
                    misses.append(f"{kind}.{op}: {p}")
    assert not misses, "Curated perms not in api_methods catalog:\n" + "\n".join(misses)


def test_resource_catalog_size():
    c = load_catalog(reload=True)
    assert len(c.resources) >= 90, f"only {len(c.resources)} curated entries, expected >= 90"

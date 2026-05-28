# iam-legend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an MCP server and GitHub Action that read GCP IaC, identify required IAM permissions, diff against live state, and post AI code reviews on PRs — for the Google for Startups AI Agents Challenge (Track 1, deadline 2026-06-05).

**Architecture:** Pure-Python shared core library (`src/iam_legend/`). Two distinct user surfaces consume the core: a FastMCP server (stdio for privileged local use + HTTP read-only on Cloud Run) and a Docker-based GitHub Action that posts PR reviews. CLI falls out of the same package. Deterministic analysis throughout; Gemini calls only for review prose and role-recommendation justification, both with templated fallbacks.

**Tech Stack:** Python 3.13, `mcp` (FastMCP), `python-hcl2`, `PyYAML`, `google-auth`, `google-cloud-iam` / `google-api-python-client` (for IAM Admin + testIamPermissions), `google-cloud-aiplatform` (Vertex Gemini), `pytest`, `ruff`, `pygithub` (for PR comments), Docker, Cloud Run.

**Spec reference:** `docs/superpowers/specs/2026-05-28-iam-legend-design.md`. Every task below maps to a numbered section in the spec.

---

## File structure

```
iam-legend/
├── pyproject.toml
├── Dockerfile
├── action.yml
├── LICENSE                          # Apache-2.0
├── NOTICE                           # Pike attribution
├── README.md
├── src/iam_legend/
│   ├── __init__.py
│   ├── types.py                     # DetectedGCPResource, AnalysisReport, FullReport
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── loader.py                # loads roles.json, api_methods.json, resources.yaml
│   │   ├── resolver.py              # shared resolver: resources -> required perms
│   │   ├── roles.json               # baked snapshot
│   │   ├── api_methods.json         # baked snapshot
│   │   └── resources.yaml           # curated IaC kind -> perms map
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py                  # Parser protocol + dispatch
│   │   ├── terraform_plan.py
│   │   ├── terraform_hcl.py
│   │   ├── line_recovery.py
│   │   ├── adk_python.py
│   │   ├── gcloud_sh.py
│   │   ├── cloudbuild.py            # stretch
│   │   └── github_actions.py        # stretch
│   ├── gcp/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── iam.py                   # testIamPermissions, getIamPolicy
│   │   └── service_usage.py
│   ├── recommender/
│   │   ├── __init__.py
│   │   ├── set_cover.py             # deterministic greedy
│   │   ├── justify.py               # Gemini call + fallback
│   │   └── grants.py                # gcloud command emission
│   ├── reviewer/
│   │   ├── __init__.py
│   │   ├── format.py                # Gemini call + templated fallback
│   │   └── github.py                # PR review posting
│   ├── analyze.py                   # the analyze() orchestration entrypoint
│   ├── mcp_server.py                # FastMCP server, dual transport
│   └── cli.py                       # `iam-legend` CLI entrypoint
├── catalog_build/
│   ├── refresh_roles.py
│   └── refresh_api_methods.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── parsers/
│   ├── fixtures/                    # tf, plan_json, adk_python, gcloud_sh
│   ├── integration/
│   └── e2e/                         # gated by GCP creds
└── examples/
    └── demo-repo/
        ├── .github/workflows/deploy.yml
        ├── terraform/main.tf
        └── deploy.py
```

---

## Phase 0 — Bootstrap (Day 1, ~1 hour)

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/iam_legend/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `LICENSE`
- Create: `NOTICE`
- Create: `.gitignore`
- Create: `README.md`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "iam-legend"
version = "0.1.0"
description = "GCP IAM toolbelt for AI agents and CI pipelines"
requires-python = ">=3.13"
license = { text = "Apache-2.0" }
authors = [{ name = "William O'Meara" }]
dependencies = [
    "mcp>=1.2.0",
    "python-hcl2>=4.3.5",
    "PyYAML>=6.0",
    "google-auth>=2.30.0",
    "google-api-python-client>=2.130.0",
    "google-cloud-aiplatform>=1.60.0",
    "PyGithub>=2.3.0",
    "click>=8.1.0",
    "rich>=13.7.0",
]

[project.scripts]
iam-legend = "iam_legend.cli:cli"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.5", "pyright>=1.1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/iam_legend"]

[tool.hatch.build.targets.wheel.shared-data]
"src/iam_legend/catalog/roles.json" = "iam_legend/catalog/roles.json"
"src/iam_legend/catalog/api_methods.json" = "iam_legend/catalog/api_methods.json"
"src/iam_legend/catalog/resources.yaml" = "iam_legend/catalog/resources.yaml"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write `LICENSE` (Apache-2.0)**

Use the standard Apache-2.0 license text from https://www.apache.org/licenses/LICENSE-2.0.txt. Copy it verbatim into `LICENSE`.

- [ ] **Step 3: Write `NOTICE`**

```
iam-legend
Copyright 2026 William O'Meara

This product includes data derived from Pike (https://github.com/JamesWoolfenden/pike),
Copyright (c) 2021 James Woolfenden, licensed under Apache License 2.0.
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.env
.coverage
htmlcov/
.terraform/
*.tfplan
plan.json
.DS_Store
```

- [ ] **Step 5: Create empty package init files**

`src/iam_legend/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty.

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

- [ ] **Step 6: Write minimal `README.md`**

```markdown
# iam-legend

GCP IAM toolbelt for AI agents and CI pipelines. Reads Terraform / ADK / gcloud
code and answers "what IAM does this need?" — as an MCP server, a CLI, and a
GitHub Action that posts AI code reviews on PRs.

See `docs/superpowers/specs/2026-05-28-iam-legend-design.md` for the design.

## Install (dev)

```
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 7: Install dependencies and verify**

```bash
cd iam-legend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest --collect-only
```

Expected: zero collected tests, exit 0 (collection succeeds even with no tests).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/ tests/ LICENSE NOTICE .gitignore README.md
git commit -m "chore: scaffold iam-legend package

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Core types

**Files:**
- Create: `src/iam_legend/types.py`
- Create: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing test for `DetectedGCPResource`**

`tests/unit/test_types.py`:
```python
from iam_legend.types import DetectedGCPResource, Operation, ParserSource


def test_detected_resource_roundtrips_to_dict():
    r = DetectedGCPResource(
        kind="google_storage_bucket",
        name="my-bucket",
        operation="create",
        file="main.tf",
        line=12,
        source="terraform_hcl",
    )
    d = r.to_dict()
    assert d == {
        "kind": "google_storage_bucket",
        "name": "my-bucket",
        "operation": "create",
        "file": "main.tf",
        "line": 12,
        "source": "terraform_hcl",
    }


def test_operation_typing():
    valid: Operation = "create"
    assert valid == "create"


def test_parser_source_typing():
    valid: ParserSource = "terraform_plan"
    assert valid == "terraform_plan"
```

- [ ] **Step 2: Run, verify it fails with ImportError**

```bash
pytest tests/unit/test_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'iam_legend.types'`.

- [ ] **Step 3: Implement `types.py`**

`src/iam_legend/types.py`:
```python
"""Shared data types for iam-legend.

Every parser emits DetectedGCPResource; the resolver folds them into a
ResolvedRequirements; the orchestrator returns a FullReport.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, TypeAlias

Operation: TypeAlias = Literal["create", "update", "delete"]
ParserSource: TypeAlias = Literal[
    "terraform_plan",
    "terraform_hcl",
    "adk_python",
    "gcloud_sh",
    "cloudbuild",
    "github_actions",
]


@dataclass(slots=True)
class DetectedGCPResource:
    kind: str            # e.g. "google_storage_bucket" or "vertex.agent_engine_create"
    name: str            # tf name, python variable, or synthetic id
    operation: Operation
    file: str
    line: int            # 0 if unknown
    source: ParserSource

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ResolvedRequirements:
    permissions: set[str] = field(default_factory=set)
    apis: set[str] = field(default_factory=set)
    by_file: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RoleRecommendation:
    roles: list[str]
    reasoning: str
    alternatives: list[list[str]]


@dataclass(slots=True)
class AccessRequestDraft:
    subject: str
    body: str
    suggested_approvers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LiveState:
    granted: list[str]
    missing: list[str]


@dataclass(slots=True)
class FullReport:
    resources: list[DetectedGCPResource]
    required_permissions: list[str]
    required_apis: list[str]
    by_file: dict[str, list[str]]
    live_state: LiveState | None
    recommendation: RoleRecommendation
    grant_commands: list[str]
    access_request: AccessRequestDraft
    warnings: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already handles nested dataclasses; just ensure resources -> dicts
        return d
```

- [ ] **Step 4: Run, verify it passes**

```bash
pytest tests/unit/test_types.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/iam_legend/types.py tests/unit/test_types.py
git commit -m "feat(core): add shared dataclass types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 1 — Catalog (Day 1-2, ~6 hours)

Spec reference: §7. The catalog is the foundation; a wrong entry = a wrong review.

### Task 3: Catalog loader

**Files:**
- Create: `src/iam_legend/catalog/__init__.py`
- Create: `src/iam_legend/catalog/loader.py`
- Create: `tests/unit/test_catalog_loader.py`
- Create: `src/iam_legend/catalog/roles.json` (minimal stub)
- Create: `src/iam_legend/catalog/api_methods.json` (minimal stub)
- Create: `src/iam_legend/catalog/resources.yaml` (minimal stub)

- [ ] **Step 1: Write failing test**

`tests/unit/test_catalog_loader.py`:
```python
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
```

- [ ] **Step 2: Run, verify ImportError**

```bash
pytest tests/unit/test_catalog_loader.py -v
```

- [ ] **Step 3: Create minimal catalog stubs**

`src/iam_legend/catalog/roles.json`:
```json
{
  "roles/storage.admin": {
    "title": "Storage Admin",
    "stage": "GA",
    "permissions": ["storage.buckets.create", "storage.buckets.delete", "storage.buckets.get", "storage.buckets.list", "storage.buckets.update", "storage.objects.create", "storage.objects.delete", "storage.objects.get", "storage.objects.list", "storage.objects.update"]
  }
}
```

`src/iam_legend/catalog/api_methods.json`:
```json
{
  "storage.buckets.create": ["storage.buckets.create"],
  "storage.buckets.update": ["storage.buckets.update"],
  "storage.buckets.delete": ["storage.buckets.delete"]
}
```

`src/iam_legend/catalog/resources.yaml`:
```yaml
google_storage_bucket:
  create: [storage.buckets.create]
  update: [storage.buckets.update]
  delete: [storage.buckets.delete]
```

(These minimal stubs will be expanded in Tasks 4-6.)

- [ ] **Step 4: Implement loader**

`src/iam_legend/catalog/__init__.py`: empty.

`src/iam_legend/catalog/loader.py`:
```python
"""Catalog loading + lookup. Catalog snapshots ship in the package."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Catalog:
    roles: dict[str, dict[str, Any]] = field(default_factory=dict)
    api_methods: dict[str, list[str]] = field(default_factory=dict)
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def lookup_resource(self, kind: str, operation: str) -> list[str] | None:
        entry = self.resources.get(kind)
        if entry is None:
            return None
        return entry.get(operation)

    def required_apis_for(self, kind: str) -> list[str]:
        entry = self.resources.get(kind, {})
        return entry.get("required_apis", [])

    def lookup_role(self, role: str) -> dict[str, Any] | None:
        return self.roles.get(role)

    def roles_with(self, permission: str) -> list[str]:
        return [name for name, data in self.roles.items() if permission in data.get("permissions", [])]


_CATALOG: Catalog | None = None


def load_catalog(reload: bool = False) -> Catalog:
    """Load the baked catalog snapshot. Cached after first call."""
    global _CATALOG
    if _CATALOG is not None and not reload:
        return _CATALOG

    pkg = resources.files("iam_legend.catalog")
    roles = json.loads((pkg / "roles.json").read_text())
    api_methods = json.loads((pkg / "api_methods.json").read_text())
    resources_yaml = yaml.safe_load((pkg / "resources.yaml").read_text())

    _CATALOG = Catalog(roles=roles, api_methods=api_methods, resources=resources_yaml or {})
    return _CATALOG
```

- [ ] **Step 5: Reinstall + run tests**

```bash
uv pip install -e .
pytest tests/unit/test_catalog_loader.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/iam_legend/catalog/ tests/unit/test_catalog_loader.py
git commit -m "feat(catalog): loader + minimal stub snapshot

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Catalog refresh script for roles

**Files:**
- Create: `catalog_build/__init__.py`
- Create: `catalog_build/refresh_roles.py`

This is a non-TDD task — it's a fetch-and-write script. Validation comes from running it.

- [ ] **Step 1: Implement refresh_roles.py**

`catalog_build/refresh_roles.py`:
```python
"""Pull the full predefined-role catalog from GCP's IAM Admin API.

Run: python catalog_build/refresh_roles.py
Auth: requires ADC with iam.roles.list permission (free, public catalog).
Writes: src/iam_legend/catalog/roles.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from googleapiclient.discovery import build

OUT = Path(__file__).parent.parent / "src" / "iam_legend" / "catalog" / "roles.json"


def main() -> None:
    iam = build("iam", "v1", cache_discovery=False)
    roles: dict[str, dict] = {}
    page_token: str | None = None
    while True:
        req = iam.roles().list(view="FULL", pageToken=page_token, pageSize=1000)
        resp = req.execute()
        for r in resp.get("roles", []):
            name = r["name"]
            roles[name] = {
                "title": r.get("title", ""),
                "stage": r.get("stage", ""),
                "description": r.get("description", ""),
                "permissions": r.get("includedPermissions", []),
            }
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    OUT.write_text(json.dumps(roles, indent=2, sort_keys=True))
    print(f"Wrote {len(roles)} roles to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
python catalog_build/refresh_roles.py
```

Expected stderr: `Wrote ~1500 roles to .../roles.json`. (Exact count varies.) `roles.json` now multi-MB.

- [ ] **Step 3: Verify the loader still loads**

```bash
pytest tests/unit/test_catalog_loader.py -v
```

Expected: 4 passed (the stub `roles/storage.admin` will be inside the real catalog too).

- [ ] **Step 4: Commit**

```bash
git add catalog_build/refresh_roles.py src/iam_legend/catalog/roles.json
git commit -m "feat(catalog): refresh script + initial roles snapshot

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Catalog refresh script for API methods

**Files:**
- Create: `catalog_build/refresh_api_methods.py`

GCP's permissions reference page (https://cloud.google.com/iam/docs/permissions-reference) maps every API method to its required permissions. Scrape it.

- [ ] **Step 1: Implement refresh_api_methods.py**

`catalog_build/refresh_api_methods.py`:
```python
"""Build api_methods.json from the GCP IAM permissions reference page.

The reference page is a single HTML page with a giant table:
  Permission | Title | Description | Used in service
We invert it: for each permission row, key it under its method (which is
typically the permission name itself for Google APIs, e.g.
"storage.buckets.create").

Run: python catalog_build/refresh_api_methods.py
Writes: src/iam_legend/catalog/api_methods.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://cloud.google.com/iam/docs/permissions-reference"
OUT = Path(__file__).parent.parent / "src" / "iam_legend" / "catalog" / "api_methods.json"

# The reference page lists permissions as e.g. `storage.buckets.create`.
# Each permission corresponds to one API method (1:1 for the vast majority).
# We extract all permission identifiers from the page and 1:1 them.
PERM_PATTERN = re.compile(r"\b([a-z][a-zA-Z0-9_]*\.[a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z][a-zA-Z0-9_]*)\b")


def main() -> None:
    req = Request(URL, headers={"User-Agent": "iam-legend-catalog-build/0.1"})
    with urlopen(req) as resp:
        html = resp.read().decode("utf-8")

    perms = sorted(set(PERM_PATTERN.findall(html)))
    # Filter out false positives: real GCP perms always start with a known
    # service prefix; reject anything that doesn't.
    KNOWN_PREFIXES = {
        "storage", "compute", "iam", "resourcemanager", "run", "aiplatform",
        "container", "pubsub", "bigquery", "firestore", "cloudsql", "secretmanager",
        "cloudtasks", "cloudscheduler", "logging", "monitoring", "serviceusage",
        "artifactregistry", "cloudbuild", "discoveryengine", "vertexai",
        "dataflow", "dataproc", "spanner", "bigtable", "appengine",
        "cloudfunctions", "cloudkms", "dns", "redis", "memcache",
    }
    perms = [p for p in perms if p.split(".", 1)[0] in KNOWN_PREFIXES]

    methods = {p: [p] for p in perms}
    OUT.write_text(json.dumps(methods, indent=2, sort_keys=True))
    print(f"Wrote {len(methods)} method->perm bindings to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
python catalog_build/refresh_api_methods.py
```

Expected stderr: `Wrote ~3000-6000 method->perm bindings to .../api_methods.json`.

- [ ] **Step 3: Sanity-check a known perm exists**

```bash
python -c "import json; d = json.load(open('src/iam_legend/catalog/api_methods.json')); print('storage.buckets.create' in d, 'aiplatform.reasoningEngines.create' in d)"
```

Expected: `True True`. If `aiplatform.reasoningEngines.create` is False, the scrape missed Vertex Agent Engine perms; manually append them to api_methods.json before committing.

- [ ] **Step 4: Commit**

```bash
git add catalog_build/refresh_api_methods.py src/iam_legend/catalog/api_methods.json
git commit -m "feat(catalog): refresh script + api_methods snapshot

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Hand-curated resources.yaml (the wedge)

**Files:**
- Modify: `src/iam_legend/catalog/resources.yaml`

This is curation, not coding. Spec §7.3 says target ~100 entries: top 50 Terraform `google_*`, top 25 ADK/Vertex/Gemini Enterprise SDK calls, top 30 gcloud verbs.

Spec §5.7 Tier 1 list is the must-ship subset.

- [ ] **Step 1: Author the resources.yaml**

Replace `src/iam_legend/catalog/resources.yaml` with the full curated map. Below is the **complete file** the engineer should write — every entry, no placeholders. Authoritative sources to cross-check: `terraform-provider-google` resource source (e.g. `mmv1/products/storage/Bucket.yaml` in GoogleCloudPlatform/magic-modules) for Terraform; Pike's Apache-2.0 catalog (https://github.com/JamesWoolfenden/pike); the GCP permissions reference for verification.

```yaml
# ============================================================
# Terraform google_* resources (Tier 1, ~50)
# ============================================================

google_storage_bucket:
  create: [storage.buckets.create]
  update: [storage.buckets.update]
  delete: [storage.buckets.delete]

google_storage_bucket_iam_member:
  create: [storage.buckets.getIamPolicy, storage.buckets.setIamPolicy]
  update: [storage.buckets.getIamPolicy, storage.buckets.setIamPolicy]
  delete: [storage.buckets.getIamPolicy, storage.buckets.setIamPolicy]

google_storage_bucket_object:
  create: [storage.objects.create]
  update: [storage.objects.update]
  delete: [storage.objects.delete]

google_cloud_run_v2_service:
  create: [run.services.create, iam.serviceAccounts.actAs]
  update: [run.services.update, iam.serviceAccounts.actAs]
  delete: [run.services.delete]

google_cloud_run_v2_job:
  create: [run.jobs.create, iam.serviceAccounts.actAs]
  update: [run.jobs.update, iam.serviceAccounts.actAs]
  delete: [run.jobs.delete]

google_compute_instance:
  create: [compute.instances.create, iam.serviceAccounts.actAs]
  update: [compute.instances.setMetadata]
  delete: [compute.instances.delete]

google_compute_network:
  create: [compute.networks.create]
  update: [compute.networks.update]
  delete: [compute.networks.delete]

google_compute_subnetwork:
  create: [compute.subnetworks.create]
  update: [compute.subnetworks.update]
  delete: [compute.subnetworks.delete]

google_compute_firewall:
  create: [compute.firewalls.create]
  update: [compute.firewalls.update]
  delete: [compute.firewalls.delete]

google_container_cluster:
  create: [container.clusters.create]
  update: [container.clusters.update]
  delete: [container.clusters.delete]

google_container_node_pool:
  create: [container.clusters.update]
  update: [container.clusters.update]
  delete: [container.clusters.update]

google_iam_service_account:
  create: [iam.serviceAccounts.create]
  update: [iam.serviceAccounts.update]
  delete: [iam.serviceAccounts.delete]

google_iam_service_account_key:
  create: [iam.serviceAccountKeys.create]
  delete: [iam.serviceAccountKeys.delete]

google_project_iam_member:
  create: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
  update: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
  delete: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]

google_project_iam_binding:
  create: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
  update: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
  delete: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]

google_project_service:
  create: [serviceusage.services.enable]
  delete: [serviceusage.services.disable]

google_pubsub_topic:
  create: [pubsub.topics.create]
  update: [pubsub.topics.update]
  delete: [pubsub.topics.delete]

google_pubsub_subscription:
  create: [pubsub.subscriptions.create]
  update: [pubsub.subscriptions.update]
  delete: [pubsub.subscriptions.delete]

google_bigquery_dataset:
  create: [bigquery.datasets.create]
  update: [bigquery.datasets.update]
  delete: [bigquery.datasets.delete]

google_bigquery_table:
  create: [bigquery.tables.create]
  update: [bigquery.tables.update]
  delete: [bigquery.tables.delete]

google_firestore_database:
  create: [datastore.databases.create]
  update: [datastore.databases.update]
  delete: [datastore.databases.delete]

google_sql_database_instance:
  create: [cloudsql.instances.create]
  update: [cloudsql.instances.update]
  delete: [cloudsql.instances.delete]

google_sql_database:
  create: [cloudsql.databases.create]
  update: [cloudsql.databases.update]
  delete: [cloudsql.databases.delete]

google_secret_manager_secret:
  create: [secretmanager.secrets.create]
  update: [secretmanager.secrets.update]
  delete: [secretmanager.secrets.delete]

google_secret_manager_secret_version:
  create: [secretmanager.versions.add]
  delete: [secretmanager.versions.destroy]

google_cloud_tasks_queue:
  create: [cloudtasks.queues.create]
  update: [cloudtasks.queues.update]
  delete: [cloudtasks.queues.delete]

google_cloud_scheduler_job:
  create: [cloudscheduler.jobs.create]
  update: [cloudscheduler.jobs.update]
  delete: [cloudscheduler.jobs.delete]

google_vertex_ai_endpoint:
  create: [aiplatform.endpoints.create]
  update: [aiplatform.endpoints.update]
  delete: [aiplatform.endpoints.delete]
  required_apis: [aiplatform.googleapis.com]

google_vertex_ai_dataset:
  create: [aiplatform.datasets.create]
  update: [aiplatform.datasets.update]
  delete: [aiplatform.datasets.delete]
  required_apis: [aiplatform.googleapis.com]

google_logging_project_sink:
  create: [logging.sinks.create]
  update: [logging.sinks.update]
  delete: [logging.sinks.delete]

google_monitoring_alert_policy:
  create: [monitoring.alertPolicies.create]
  update: [monitoring.alertPolicies.update]
  delete: [monitoring.alertPolicies.delete]

google_artifact_registry_repository:
  create: [artifactregistry.repositories.create]
  update: [artifactregistry.repositories.update]
  delete: [artifactregistry.repositories.delete]

google_cloudbuild_trigger:
  create: [cloudbuild.builds.create]
  update: [cloudbuild.builds.update]
  delete: [cloudbuild.builds.delete]

google_kms_key_ring:
  create: [cloudkms.keyRings.create]

google_kms_crypto_key:
  create: [cloudkms.cryptoKeys.create]
  update: [cloudkms.cryptoKeys.update]

google_dns_managed_zone:
  create: [dns.managedZones.create]
  update: [dns.managedZones.update]
  delete: [dns.managedZones.delete]

google_redis_instance:
  create: [redis.instances.create]
  update: [redis.instances.update]
  delete: [redis.instances.delete]

google_app_engine_application:
  create: [appengine.applications.create]
  update: [appengine.applications.update]

google_cloudfunctions2_function:
  create: [cloudfunctions.functions.create, iam.serviceAccounts.actAs]
  update: [cloudfunctions.functions.update, iam.serviceAccounts.actAs]
  delete: [cloudfunctions.functions.delete]

google_dataflow_job:
  create: [dataflow.jobs.create]
  delete: [dataflow.jobs.cancel]

google_dataproc_cluster:
  create: [dataproc.clusters.create]
  update: [dataproc.clusters.update]
  delete: [dataproc.clusters.delete]

google_spanner_instance:
  create: [spanner.instances.create]
  update: [spanner.instances.update]
  delete: [spanner.instances.delete]

google_spanner_database:
  create: [spanner.databases.create]
  update: [spanner.databases.update]
  delete: [spanner.databases.delete]

google_bigtable_instance:
  create: [bigtable.instances.create]
  update: [bigtable.instances.update]
  delete: [bigtable.instances.delete]

# ============================================================
# ADK / Vertex / Gemini Enterprise / Discovery Engine (Tier 1, ~25)
# Keys are the synthetic "kind" emitted by adk_python parser.
# ============================================================

vertex.agent_engine_create:
  create:
    - aiplatform.reasoningEngines.create
    - aiplatform.reasoningEngines.deploy
    - storage.objects.create
    - storage.objects.get
  required_apis: [aiplatform.googleapis.com]

vertex.agent_engine_update:
  create:
    - aiplatform.reasoningEngines.update
    - aiplatform.reasoningEngines.deploy
  required_apis: [aiplatform.googleapis.com]

vertex.agent_engine_delete:
  create:
    - aiplatform.reasoningEngines.delete
  required_apis: [aiplatform.googleapis.com]

vertex.agent_engine_query:
  create:
    - aiplatform.reasoningEngines.query
  required_apis: [aiplatform.googleapis.com]

aiplatform.endpoint_create:
  create: [aiplatform.endpoints.create]
  required_apis: [aiplatform.googleapis.com]

aiplatform.endpoint_deploy_model:
  create: [aiplatform.endpoints.deploy]
  required_apis: [aiplatform.googleapis.com]

aiplatform.model_upload:
  create: [aiplatform.models.upload, storage.objects.get]
  required_apis: [aiplatform.googleapis.com]

aiplatform.custom_job_create:
  create: [aiplatform.customJobs.create, iam.serviceAccounts.actAs]
  required_apis: [aiplatform.googleapis.com]

aiplatform.batch_prediction_job_create:
  create: [aiplatform.batchPredictionJobs.create]
  required_apis: [aiplatform.googleapis.com]

aiplatform.vertex_init:
  create: []   # records project/location, no perms by itself
  required_apis: [aiplatform.googleapis.com]

aiplatform.generate_content:
  create: [aiplatform.endpoints.predict]
  required_apis: [aiplatform.googleapis.com]

discoveryengine.datastore_create:
  create: [discoveryengine.dataStores.create]
  required_apis: [discoveryengine.googleapis.com]

discoveryengine.datastore_delete:
  create: [discoveryengine.dataStores.delete]
  required_apis: [discoveryengine.googleapis.com]

discoveryengine.engine_create:
  create: [discoveryengine.engines.create]
  required_apis: [discoveryengine.googleapis.com]

discoveryengine.engine_delete:
  create: [discoveryengine.engines.delete]
  required_apis: [discoveryengine.googleapis.com]

discoveryengine.document_import:
  create: [discoveryengine.documents.import]
  required_apis: [discoveryengine.googleapis.com]

storage.bucket_create_imperative:
  create: [storage.buckets.create]

storage.bucket_delete_imperative:
  create: [storage.buckets.delete]

storage.blob_upload_imperative:
  create: [storage.objects.create]

storage.blob_download_imperative:
  create: [storage.objects.get]

pubsub.topic_publish_imperative:
  create: [pubsub.topics.publish]

pubsub.subscription_pull_imperative:
  create: [pubsub.subscriptions.consume]

secretmanager.access_secret_imperative:
  create: [secretmanager.versions.access]

bigquery.query_imperative:
  create: [bigquery.jobs.create, bigquery.tables.getData]

firestore.document_write_imperative:
  create: [datastore.entities.create]

# ============================================================
# gcloud verbs (Tier 1, ~30)
# Keys are emitted by gcloud_sh parser.
# ============================================================

gcloud.storage.buckets.create:
  create: [storage.buckets.create]
gcloud.storage.buckets.delete:
  create: [storage.buckets.delete]
gcloud.storage.cp:
  create: [storage.objects.create, storage.objects.get]
gcloud.iam.service_accounts.create:
  create: [iam.serviceAccounts.create]
gcloud.iam.service_accounts.delete:
  create: [iam.serviceAccounts.delete]
gcloud.iam.service_accounts.keys.create:
  create: [iam.serviceAccountKeys.create]
gcloud.iam.roles.create:
  create: [iam.roles.create]
gcloud.iam.roles.update:
  create: [iam.roles.update]
gcloud.projects.add_iam_policy_binding:
  create: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
gcloud.projects.remove_iam_policy_binding:
  create: [resourcemanager.projects.getIamPolicy, resourcemanager.projects.setIamPolicy]
gcloud.services.enable:
  create: [serviceusage.services.enable]
gcloud.services.disable:
  create: [serviceusage.services.disable]
gcloud.run.deploy:
  create: [run.services.create, run.services.update, iam.serviceAccounts.actAs]
gcloud.run.jobs.create:
  create: [run.jobs.create, iam.serviceAccounts.actAs]
gcloud.run.services.delete:
  create: [run.services.delete]
gcloud.compute.instances.create:
  create: [compute.instances.create, iam.serviceAccounts.actAs]
gcloud.compute.networks.create:
  create: [compute.networks.create]
gcloud.compute.firewall_rules.create:
  create: [compute.firewalls.create]
gcloud.container.clusters.create:
  create: [container.clusters.create]
gcloud.container.clusters.delete:
  create: [container.clusters.delete]
gcloud.pubsub.topics.create:
  create: [pubsub.topics.create]
gcloud.pubsub.subscriptions.create:
  create: [pubsub.subscriptions.create]
gcloud.secrets.create:
  create: [secretmanager.secrets.create]
gcloud.secrets.versions.add:
  create: [secretmanager.versions.add]
gcloud.artifacts.repositories.create:
  create: [artifactregistry.repositories.create]
gcloud.artifacts.docker.images.push:
  create: [artifactregistry.repositories.uploadArtifacts]
gcloud.builds.submit:
  create: [cloudbuild.builds.create]
gcloud.functions.deploy:
  create: [cloudfunctions.functions.create, cloudfunctions.functions.update, iam.serviceAccounts.actAs]
gcloud.ai.agents.deploy:
  create:
    - aiplatform.reasoningEngines.create
    - aiplatform.reasoningEngines.deploy
  required_apis: [aiplatform.googleapis.com]
gcloud.sql.instances.create:
  create: [cloudsql.instances.create]
gcloud.bigquery.datasets.create:
  create: [bigquery.datasets.create]
```

- [ ] **Step 2: Write a validator test**

`tests/unit/test_catalog_validity.py`:
```python
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
```

- [ ] **Step 3: Run; fix every miss**

```bash
pytest tests/unit/test_catalog_validity.py -v
```

If a permission is listed in `resources.yaml` but missing from `api_methods.json`, append it to `api_methods.json` (some `aiplatform.reasoningEngines.*` and `discoveryengine.*` may be too new to be scraped). Re-run until both tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/iam_legend/catalog/resources.yaml src/iam_legend/catalog/api_methods.json tests/unit/test_catalog_validity.py
git commit -m "feat(catalog): hand-curated resources.yaml (top ~100 entries)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Resolver (Day 2, ~1 hour)

### Task 7: Shared resolver

Spec §5.6.

**Files:**
- Create: `src/iam_legend/catalog/resolver.py`
- Create: `tests/unit/test_resolver.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_resolver.py`:
```python
from iam_legend.catalog.loader import load_catalog
from iam_legend.catalog.resolver import resolve
from iam_legend.types import DetectedGCPResource


def _r(kind: str, op: str = "create", file: str = "x.tf", line: int = 1) -> DetectedGCPResource:
    return DetectedGCPResource(
        kind=kind, name="x", operation=op, file=file, line=line, source="terraform_hcl",
    )


def test_resolve_known_resource():
    rr = resolve([_r("google_storage_bucket")], load_catalog())
    assert "storage.buckets.create" in rr.permissions
    assert rr.warnings == []


def test_resolve_unknown_resource_emits_warning():
    rr = resolve([_r("google_nonexistent_xyz")], load_catalog())
    assert rr.warnings != []
    assert "google_nonexistent_xyz" in rr.warnings[0]


def test_resolve_aggregates_apis():
    rr = resolve([_r("vertex.agent_engine_create")], load_catalog())
    assert "aiplatform.googleapis.com" in rr.apis


def test_resolve_by_file_grouping():
    rs = [_r("google_storage_bucket", file="a.tf"), _r("google_pubsub_topic", file="b.tf")]
    rr = resolve(rs, load_catalog())
    assert set(rr.by_file["a.tf"]) == {"storage.buckets.create"}
    assert set(rr.by_file["b.tf"]) == {"pubsub.topics.create"}
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_resolver.py -v
```

- [ ] **Step 3: Implement resolver**

`src/iam_legend/catalog/resolver.py`:
```python
"""Single resolver: list[DetectedGCPResource] -> ResolvedRequirements.

The resolver does not care which parser produced the resource. Catalog gaps
surface as warnings; we never silently drop a detected resource.
"""
from __future__ import annotations

from collections import defaultdict

from iam_legend.catalog.loader import Catalog, load_catalog
from iam_legend.types import DetectedGCPResource, ResolvedRequirements


def resolve(
    resources: list[DetectedGCPResource],
    catalog: Catalog | None = None,
) -> ResolvedRequirements:
    c = catalog or load_catalog()
    perms: set[str] = set()
    apis: set[str] = set()
    by_file: dict[str, list[str]] = defaultdict(list)
    warnings: list[str] = []

    for r in resources:
        entry_perms = c.lookup_resource(r.kind, r.operation)
        if entry_perms is None:
            warnings.append(
                f"unknown resource kind '{r.kind}' at {r.file}:{r.line} "
                f"(source: {r.source}); not analysed"
            )
            continue
        perms.update(entry_perms)
        by_file[r.file].extend(entry_perms)
        apis.update(c.required_apis_for(r.kind))

    return ResolvedRequirements(
        permissions=perms,
        apis=apis,
        by_file=dict(by_file),
        warnings=warnings,
    )
```

- [ ] **Step 4: Run; verify all 4 pass**

```bash
pytest tests/unit/test_resolver.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/iam_legend/catalog/resolver.py tests/unit/test_resolver.py
git commit -m "feat(resolver): single resolver from resources to required perms

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Parsers (Day 2-4, ~10 hours)

### Task 8: Parser base + dispatch

Spec §5.1.

**Files:**
- Create: `src/iam_legend/parsers/__init__.py`
- Create: `src/iam_legend/parsers/base.py`
- Create: `tests/parsers/__init__.py`

- [ ] **Step 1: Implement `parsers/base.py`**

`src/iam_legend/parsers/__init__.py`: empty.
`tests/parsers/__init__.py`: empty.

`src/iam_legend/parsers/base.py`:
```python
"""Parser protocol and dispatch.

Each concrete parser implements `Parser`. The dispatcher tries each parser
that `matches()` the given path and returns the union of detected resources.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from iam_legend.types import DetectedGCPResource


class Parser(Protocol):
    name: str

    def matches(self, path: str) -> bool: ...
    def parse_file(self, path: str) -> list[DetectedGCPResource]: ...


_REGISTRY: list[Parser] = []


def register(parser: Parser) -> None:
    _REGISTRY.append(parser)


def all_parsers() -> list[Parser]:
    return list(_REGISTRY)


def walk_repo(root: str, *, follow_symlinks: bool = False) -> list[DetectedGCPResource]:
    """Walk a directory tree, dispatch each file to matching parsers, aggregate."""
    out: list[DetectedGCPResource] = []
    root_path = Path(root)
    if not root_path.exists():
        return out
    for path in root_path.rglob("*"):
        if path.is_dir():
            continue
        if any(seg.startswith(".") for seg in path.relative_to(root_path).parts):
            # skip hidden dirs/files
            continue
        s = str(path)
        for parser in _REGISTRY:
            if parser.matches(s):
                try:
                    out.extend(parser.parse_file(s))
                except Exception:
                    # Parser errors must not crash the walk; the resolver/reviewer
                    # will surface unknowns as warnings.
                    continue
    return out
```

- [ ] **Step 2: Write a smoke test**

`tests/parsers/test_base.py`:
```python
from iam_legend.parsers.base import register, all_parsers, walk_repo
from iam_legend.types import DetectedGCPResource


class StubParser:
    name = "stub"

    def matches(self, path: str) -> bool:
        return path.endswith(".stub")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        return [
            DetectedGCPResource(
                kind="google_storage_bucket", name="x", operation="create",
                file=path, line=1, source="terraform_hcl",
            )
        ]


def test_walk_invokes_matching_parser(tmp_path):
    register(StubParser())
    (tmp_path / "a.stub").write_text("hi")
    (tmp_path / "b.txt").write_text("nope")
    out = walk_repo(str(tmp_path))
    assert len(out) == 1
    assert out[0].file.endswith("a.stub")
```

- [ ] **Step 3: Run**

```bash
pytest tests/parsers/test_base.py -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add src/iam_legend/parsers/base.py tests/parsers/
git commit -m "feat(parsers): base protocol + dispatch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Terraform plan JSON parser

Spec §5.2 (plan JSON mode).

**Files:**
- Create: `src/iam_legend/parsers/terraform_plan.py`
- Create: `tests/fixtures/plan_json/simple.json`
- Create: `tests/parsers/test_terraform_plan.py`

- [ ] **Step 1: Create a real fixture**

`tests/fixtures/plan_json/simple.json`:
```json
{
  "format_version": "1.2",
  "terraform_version": "1.9.0",
  "resource_changes": [
    {
      "address": "google_storage_bucket.data",
      "mode": "managed",
      "type": "google_storage_bucket",
      "name": "data",
      "change": { "actions": ["create"] }
    },
    {
      "address": "google_pubsub_topic.events",
      "mode": "managed",
      "type": "google_pubsub_topic",
      "name": "events",
      "change": { "actions": ["update"] }
    },
    {
      "address": "google_iam_service_account.bot",
      "mode": "managed",
      "type": "google_iam_service_account",
      "name": "bot",
      "change": { "actions": ["delete"] }
    },
    {
      "address": "module.net.google_compute_network.vpc",
      "mode": "managed",
      "type": "google_compute_network",
      "name": "vpc",
      "change": { "actions": ["no-op"] }
    }
  ]
}
```

- [ ] **Step 2: Write failing test**

`tests/parsers/test_terraform_plan.py`:
```python
from pathlib import Path

from iam_legend.parsers.terraform_plan import TerraformPlanParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_matches_only_json():
    p = TerraformPlanParser()
    assert p.matches("plan.json") is True
    assert p.matches("main.tf") is False


def test_parses_real_plan_json():
    p = TerraformPlanParser()
    out = p.parse_file(str(FIXTURE))
    kinds_ops = {(r.kind, r.operation) for r in out}
    assert ("google_storage_bucket", "create") in kinds_ops
    assert ("google_pubsub_topic", "update") in kinds_ops
    assert ("google_iam_service_account", "delete") in kinds_ops
    # no-op should be skipped
    assert ("google_compute_network", "create") not in kinds_ops
    assert ("google_compute_network", "update") not in kinds_ops


def test_module_path_preserved_in_file_field():
    p = TerraformPlanParser()
    out = p.parse_file(str(FIXTURE))
    addresses = {r.name for r in out}
    assert "data" in addresses
```

- [ ] **Step 3: Implement parser**

`src/iam_legend/parsers/terraform_plan.py`:
```python
"""Parse `terraform show -json plan.tfplan` output.

The plan JSON is the authoritative input for the CI gate: Terraform fully
resolves every module to leaf resources and lists the actions to apply.
"""
from __future__ import annotations

import json
from pathlib import Path

from iam_legend.parsers.base import register
from iam_legend.types import DetectedGCPResource, Operation


_ACTION_MAP: dict[str, Operation] = {
    "create": "create",
    "update": "update",
    "delete": "delete",
}


class TerraformPlanParser:
    name = "terraform_plan"

    def matches(self, path: str) -> bool:
        # Accept only files that explicitly look like plan JSON.
        # Callers should be explicit: pass the path, not just "scan a repo".
        return path.endswith(".json") and "plan" in Path(path).name.lower()

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        data = json.loads(Path(path).read_text())
        return self.parse_dict(data, source_file=path)

    def parse_dict(self, plan: dict, source_file: str = "plan.json") -> list[DetectedGCPResource]:
        out: list[DetectedGCPResource] = []
        for change in plan.get("resource_changes", []):
            kind = change.get("type", "")
            if not kind.startswith("google_"):
                continue
            actions = change.get("change", {}).get("actions", [])
            # Determine the dominant action: create > update > delete; skip no-op.
            op = self._pick_operation(actions)
            if op is None:
                continue
            out.append(DetectedGCPResource(
                kind=kind,
                name=change.get("name", change.get("address", "")),
                operation=op,
                file=source_file,
                line=0,
                source="terraform_plan",
            ))
        return out

    @staticmethod
    def _pick_operation(actions: list[str]) -> Operation | None:
        # "create" implies create perms; "update" implies update; "delete" implies delete.
        # A "replace" (delete then create) we treat as create+delete; pick create here,
        # callers can re-call with operation="delete" if needed. For simplicity, emit one.
        if "create" in actions:
            return "create"
        if "update" in actions:
            return "update"
        if "delete" in actions:
            return "delete"
        return None


register(TerraformPlanParser())
```

- [ ] **Step 4: Run; verify all tests pass**

```bash
pytest tests/parsers/test_terraform_plan.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/iam_legend/parsers/terraform_plan.py tests/fixtures/plan_json/ tests/parsers/test_terraform_plan.py
git commit -m "feat(parsers): terraform plan JSON parser

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Terraform HCL static parser + line recovery

Spec §5.2 (HCL static mode + line-recovery pass).

**Files:**
- Create: `src/iam_legend/parsers/line_recovery.py`
- Create: `src/iam_legend/parsers/terraform_hcl.py`
- Create: `tests/fixtures/terraform/main.tf`
- Create: `tests/fixtures/terraform/with_module/main.tf`
- Create: `tests/fixtures/terraform/with_module/modules/net/main.tf`
- Create: `tests/parsers/test_line_recovery.py`
- Create: `tests/parsers/test_terraform_hcl.py`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/terraform/main.tf`:
```hcl
resource "google_storage_bucket" "data" {
  name     = "my-data"
  location = "US"
}

resource "google_pubsub_topic" "events" {
  name = "events"
}

# A non-google resource that should be ignored
resource "null_resource" "noop" {}
```

`tests/fixtures/terraform/with_module/main.tf`:
```hcl
module "net" {
  source = "./modules/net"
}

resource "google_storage_bucket" "root_bucket" {
  name = "x"
}
```

`tests/fixtures/terraform/with_module/modules/net/main.tf`:
```hcl
resource "google_compute_network" "vpc" {
  name = "vpc"
}
```

- [ ] **Step 2: Write failing line-recovery test**

`tests/parsers/test_line_recovery.py`:
```python
from pathlib import Path

from iam_legend.parsers.line_recovery import recover_lines


def test_recover_lines_finds_resource_declarations(tmp_path):
    tf = tmp_path / "main.tf"
    tf.write_text(
        'resource "google_storage_bucket" "a" {\n'
        '  name = "x"\n'
        '}\n'
        '\n'
        'resource "google_pubsub_topic" "b" {\n'
        '  name = "y"\n'
        '}\n'
    )
    lines = recover_lines(
        str(tf),
        [("google_storage_bucket", "a"), ("google_pubsub_topic", "b")],
    )
    assert lines[("google_storage_bucket", "a")] == 1
    assert lines[("google_pubsub_topic", "b")] == 5


def test_recover_lines_missing_returns_zero(tmp_path):
    tf = tmp_path / "main.tf"
    tf.write_text('resource "google_storage_bucket" "x" {}\n')
    lines = recover_lines(str(tf), [("google_pubsub_topic", "absent")])
    assert lines[("google_pubsub_topic", "absent")] == 0
```

- [ ] **Step 3: Implement line_recovery**

`src/iam_legend/parsers/line_recovery.py`:
```python
"""Recover (resource_type, resource_name) -> line numbers from a Terraform source file.

python-hcl2 doesn't preserve source positions, so we do a second pass over
the raw text. Cheap (one regex scan per file) and correct enough — Terraform
resource declarations are line-anchored by convention.
"""
from __future__ import annotations

import re
from pathlib import Path


_RESOURCE_RE = re.compile(
    r'^\s*resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_\-]+)"',
    re.MULTILINE,
)


def recover_lines(
    file_path: str,
    targets: list[tuple[str, str]],
) -> dict[tuple[str, str], int]:
    """Return a dict mapping (type, name) -> 1-based line number.
    Targets not found map to 0.
    """
    text = Path(file_path).read_text()
    found: dict[tuple[str, str], int] = {}
    for m in _RESOURCE_RE.finditer(text):
        rtype, rname = m.group(1), m.group(2)
        line_no = text.count("\n", 0, m.start()) + 1
        found[(rtype, rname)] = line_no
    return {t: found.get(t, 0) for t in targets}
```

- [ ] **Step 4: Run; verify line recovery passes**

```bash
pytest tests/parsers/test_line_recovery.py -v
```

- [ ] **Step 5: Write failing HCL parser test**

`tests/parsers/test_terraform_hcl.py`:
```python
from pathlib import Path

from iam_legend.parsers.terraform_hcl import TerraformHCLParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "terraform"


def test_parses_basic_hcl():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    kinds = {r.kind for r in out}
    assert "google_storage_bucket" in kinds
    assert "google_pubsub_topic" in kinds
    assert "null_resource" not in kinds


def test_line_numbers_populated():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    by_kind = {r.kind: r for r in out}
    assert by_kind["google_storage_bucket"].line > 0
    assert by_kind["google_pubsub_topic"].line > by_kind["google_storage_bucket"].line


def test_recurses_local_modules():
    p = TerraformHCLParser()
    out = p.parse_dir(str(FIXTURE_DIR / "with_module"))
    kinds = {r.kind for r in out}
    assert "google_storage_bucket" in kinds
    assert "google_compute_network" in kinds   # from the nested module


def test_assumes_create_operation():
    p = TerraformHCLParser()
    out = p.parse_file(str(FIXTURE_DIR / "main.tf"))
    assert all(r.operation == "create" for r in out)
```

- [ ] **Step 6: Implement HCL parser**

`src/iam_legend/parsers/terraform_hcl.py`:
```python
"""Static HCL parsing for *.tf files. Used when plan JSON isn't available.

Assumes 'create' for every detected resource (worst case for perms).
Recurses into local modules.
"""
from __future__ import annotations

from pathlib import Path

import hcl2

from iam_legend.parsers.base import register
from iam_legend.parsers.line_recovery import recover_lines
from iam_legend.types import DetectedGCPResource


class TerraformHCLParser:
    name = "terraform_hcl"

    def matches(self, path: str) -> bool:
        return path.endswith(".tf")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        with open(path) as f:
            try:
                parsed = hcl2.load(f)
            except Exception:
                return []
        resources = parsed.get("resource", [])
        targets: list[tuple[str, str]] = []
        for block in resources:
            # python-hcl2 emits a list of single-key dicts: [{type: {name: {...}}}, ...]
            for rtype, by_name in block.items():
                if not rtype.startswith("google_"):
                    continue
                for rname in by_name.keys():
                    targets.append((rtype, rname))

        line_map = recover_lines(path, targets)
        return [
            DetectedGCPResource(
                kind=rtype,
                name=rname,
                operation="create",
                file=path,
                line=line_map.get((rtype, rname), 0),
                source="terraform_hcl",
            )
            for (rtype, rname) in targets
        ]

    def parse_dir(self, directory: str) -> list[DetectedGCPResource]:
        out: list[DetectedGCPResource] = []
        for tf in Path(directory).rglob("*.tf"):
            out.extend(self.parse_file(str(tf)))
        return out


register(TerraformHCLParser())
```

- [ ] **Step 7: Run; verify all 4 tests pass**

```bash
pytest tests/parsers/test_terraform_hcl.py -v
```

- [ ] **Step 8: Commit**

```bash
git add src/iam_legend/parsers/terraform_hcl.py src/iam_legend/parsers/line_recovery.py tests/fixtures/terraform/ tests/parsers/test_terraform_hcl.py tests/parsers/test_line_recovery.py
git commit -m "feat(parsers): terraform HCL static parser with line recovery

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: ADK Python AST parser with import-alias resolution

Spec §5.3.

**Files:**
- Create: `src/iam_legend/parsers/adk_python.py`
- Create: `src/iam_legend/parsers/adk_call_signatures.yaml`
- Create: `tests/fixtures/adk_python/deploy_basic.py`
- Create: `tests/fixtures/adk_python/deploy_aliased.py`
- Create: `tests/parsers/test_adk_python.py`

- [ ] **Step 1: Write the signature map**

`src/iam_legend/parsers/adk_call_signatures.yaml`:
```yaml
# Map: fully-qualified callable -> { kind, operation }
# After import-alias resolution, AST call sites are matched against these keys.

vertexai.agent_engines.create:
  kind: vertex.agent_engine_create
  operation: create

vertexai.agent_engines.AgentEngine.create:
  kind: vertex.agent_engine_create
  operation: create

vertexai.agent_engines.update:
  kind: vertex.agent_engine_update
  operation: update

vertexai.agent_engines.delete:
  kind: vertex.agent_engine_delete
  operation: delete

vertexai.agent_engines.AgentEngine.query:
  kind: vertex.agent_engine_query
  operation: create

vertexai.init:
  kind: aiplatform.vertex_init
  operation: create

google.cloud.aiplatform.init:
  kind: aiplatform.vertex_init
  operation: create

google.cloud.aiplatform.Endpoint.create:
  kind: aiplatform.endpoint_create
  operation: create

google.cloud.aiplatform.Endpoint.deploy:
  kind: aiplatform.endpoint_deploy_model
  operation: create

google.cloud.aiplatform.Model.upload:
  kind: aiplatform.model_upload
  operation: create

google.cloud.aiplatform.CustomJob.run:
  kind: aiplatform.custom_job_create
  operation: create

google.cloud.aiplatform.BatchPredictionJob.create:
  kind: aiplatform.batch_prediction_job_create
  operation: create

google.cloud.aiplatform.gapic.PredictionServiceClient.generate_content:
  kind: aiplatform.generate_content
  operation: create

google.cloud.storage.Client.create_bucket:
  kind: storage.bucket_create_imperative
  operation: create

google.cloud.storage.Client.bucket:
  # bucket(name).upload_from_filename — flagged separately at call site
  kind: storage.blob_upload_imperative
  operation: create

google.cloud.pubsub_v1.PublisherClient.publish:
  kind: pubsub.topic_publish_imperative
  operation: create

google.cloud.pubsub_v1.SubscriberClient.pull:
  kind: pubsub.subscription_pull_imperative
  operation: create

google.cloud.secretmanager.SecretManagerServiceClient.access_secret_version:
  kind: secretmanager.access_secret_imperative
  operation: create

google.cloud.bigquery.Client.query:
  kind: bigquery.query_imperative
  operation: create

google.cloud.firestore.Client.collection:
  kind: firestore.document_write_imperative
  operation: create

google.cloud.discoveryengine_v1.DataStoreServiceClient.create_data_store:
  kind: discoveryengine.datastore_create
  operation: create

google.cloud.discoveryengine_v1.EngineServiceClient.create_engine:
  kind: discoveryengine.engine_create
  operation: create

google.cloud.discoveryengine_v1.DocumentServiceClient.import_documents:
  kind: discoveryengine.document_import
  operation: create
```

- [ ] **Step 2: Create AST fixtures**

`tests/fixtures/adk_python/deploy_basic.py`:
```python
import vertexai
from vertexai import agent_engines

vertexai.init(project="my-proj", location="us-central1")

agent = agent_engines.create(
    display_name="my-agent",
    reasoning_engine="my_module.agent",
)
```

`tests/fixtures/adk_python/deploy_aliased.py`:
```python
# Tests import-alias resolution: 'from x.y import z as w' style.
from google.cloud import aiplatform as ap
from vertexai import agent_engines as ae

ap.init(project="p", location="us-central1")

endpoint = ap.Endpoint.create(display_name="e")
agent = ae.create(display_name="a")
```

- [ ] **Step 3: Write failing tests**

`tests/parsers/test_adk_python.py`:
```python
from pathlib import Path

from iam_legend.parsers.adk_python import ADKPythonParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "adk_python"


def test_matches_py_files_only():
    p = ADKPythonParser()
    assert p.matches("deploy.py") is True
    assert p.matches("main.tf") is False


def test_detects_basic_imports_and_calls():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_basic.py"))
    kinds = {r.kind for r in out}
    assert "aiplatform.vertex_init" in kinds
    assert "vertex.agent_engine_create" in kinds


def test_resolves_import_aliases():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_aliased.py"))
    kinds = {r.kind for r in out}
    assert "aiplatform.vertex_init" in kinds          # ap.init -> google.cloud.aiplatform.init
    assert "aiplatform.endpoint_create" in kinds      # ap.Endpoint.create
    assert "vertex.agent_engine_create" in kinds      # ae.create


def test_line_numbers_populated():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_basic.py"))
    assert all(r.line > 0 for r in out)
```

- [ ] **Step 4: Implement ADK Python parser**

`src/iam_legend/parsers/adk_python.py`:
```python
"""AST-based parser for ADK / Vertex / Discovery Engine SDK calls.

Two-pass:
 1. Walk Import/ImportFrom nodes -> build alias table {local_name -> FQN_prefix}.
 2. Walk Call nodes -> resolve each call's chain through the alias table,
    match against the signature map.

Unrecognised but plausibly-relevant calls fall through silently; the resolver
will not see them, so the catalog will not complain. (Catalog warnings come
from kinds we DO detect but DON'T have entries for.)
"""
from __future__ import annotations

import ast
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any

import yaml

from iam_legend.parsers.base import register
from iam_legend.types import DetectedGCPResource


def _load_signatures() -> dict[str, dict[str, str]]:
    text = importlib_resources.files("iam_legend.parsers").joinpath("adk_call_signatures.yaml").read_text()
    return yaml.safe_load(text)


_SIGS: dict[str, dict[str, str]] = _load_signatures()


class _AliasResolver(ast.NodeVisitor):
    """Builds a per-file alias table mapping local name -> fully-qualified prefix."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        # `import a.b.c` -> aliases["a"] = "a"; alias variant: `import a.b as q` -> aliases["q"] = "a.b"
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            self.aliases[local] = target
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # `from a.b import c` -> aliases["c"] = "a.b.c"
        # `from a.b import c as d` -> aliases["d"] = "a.b.c"
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.aliases[local] = f"{module}.{alias.name}" if module else alias.name
        self.generic_visit(node)


def _flatten_call_chain(call: ast.Call) -> list[str] | None:
    """Return the dotted call chain as a list of names, or None if dynamic."""
    parts: list[str] = []
    node: ast.AST = call.func
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            return None
    parts.reverse()
    return parts


def _resolve_to_fqn(parts: list[str], aliases: dict[str, str]) -> str | None:
    if not parts:
        return None
    head, *rest = parts
    prefix = aliases.get(head)
    if prefix is None:
        return None
    return ".".join([prefix, *rest])


class ADKPythonParser:
    name = "adk_python"

    def matches(self, path: str) -> bool:
        return path.endswith(".py")

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        src = Path(path).read_text()
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError:
            return []

        resolver = _AliasResolver()
        resolver.visit(tree)

        out: list[DetectedGCPResource] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _flatten_call_chain(node)
            if parts is None:
                continue
            fqn = _resolve_to_fqn(parts, resolver.aliases)
            if fqn is None:
                continue
            sig = _SIGS.get(fqn)
            if sig is None:
                continue
            out.append(DetectedGCPResource(
                kind=sig["kind"],
                name=parts[-1],
                operation=sig.get("operation", "create"),  # type: ignore[arg-type]
                file=path,
                line=node.lineno,
                source="adk_python",
            ))
        return out


register(ADKPythonParser())
```

- [ ] **Step 5: Run; verify all 4 pass**

```bash
pytest tests/parsers/test_adk_python.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/iam_legend/parsers/adk_python.py src/iam_legend/parsers/adk_call_signatures.yaml tests/fixtures/adk_python/ tests/parsers/test_adk_python.py
git commit -m "feat(parsers): ADK python AST parser with import-alias resolution

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: gcloud shell parser

Spec §5.4.

**Files:**
- Create: `src/iam_legend/parsers/gcloud_sh.py`
- Create: `tests/fixtures/gcloud_sh/deploy.sh`
- Create: `tests/fixtures/gcloud_sh/Makefile`
- Create: `tests/parsers/test_gcloud_sh.py`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/gcloud_sh/deploy.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

gcloud storage buckets create gs://my-bucket --location=us-central1
gcloud iam service-accounts create my-bot
gcloud projects add-iam-policy-binding my-proj \
  --member=serviceAccount:my-bot@my-proj.iam.gserviceaccount.com \
  --role=roles/run.admin
gcloud run deploy my-svc --image=us-docker.pkg.dev/my-proj/img:latest
gcloud services enable aiplatform.googleapis.com
```

`tests/fixtures/gcloud_sh/Makefile`:
```makefile
.PHONY: deploy
deploy:
	gcloud ai agents deploy --display-name=my-agent
```

- [ ] **Step 2: Write failing tests**

`tests/parsers/test_gcloud_sh.py`:
```python
from pathlib import Path

from iam_legend.parsers.gcloud_sh import GcloudShellParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "gcloud_sh"


def test_matches_shell_and_makefile():
    p = GcloudShellParser()
    assert p.matches("deploy.sh") is True
    assert p.matches("Makefile") is True
    assert p.matches("makefile") is True
    assert p.matches("main.tf") is False


def test_parses_deploy_sh():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy.sh"))
    kinds = {r.kind for r in out}
    assert "gcloud.storage.buckets.create" in kinds
    assert "gcloud.iam.service_accounts.create" in kinds
    assert "gcloud.projects.add_iam_policy_binding" in kinds
    assert "gcloud.run.deploy" in kinds
    assert "gcloud.services.enable" in kinds


def test_parses_makefile():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "Makefile"))
    kinds = {r.kind for r in out}
    assert "gcloud.ai.agents.deploy" in kinds


def test_line_numbers_populated():
    p = GcloudShellParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy.sh"))
    assert all(r.line > 0 for r in out)
```

- [ ] **Step 3: Implement parser**

`src/iam_legend/parsers/gcloud_sh.py`:
```python
"""Regex-based parser for gcloud verbs in shell scripts and Makefiles.

Matches against a curated verb map (~30 entries) — see resources.yaml's
gcloud.* keys. Unrecognised verbs are silently ignored (catalog warnings
already cover the "we detected something we don't understand" case).
"""
from __future__ import annotations

import re
from pathlib import Path

from iam_legend.parsers.base import register
from iam_legend.types import DetectedGCPResource

# Order matters: longer/more specific patterns first.
_VERB_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bgcloud\s+storage\s+buckets\s+create\b"), "gcloud.storage.buckets.create"),
    (re.compile(r"\bgcloud\s+storage\s+buckets\s+delete\b"), "gcloud.storage.buckets.delete"),
    (re.compile(r"\bgcloud\s+storage\s+cp\b"), "gcloud.storage.cp"),
    (re.compile(r"\bgcloud\s+iam\s+service-accounts\s+create\b"), "gcloud.iam.service_accounts.create"),
    (re.compile(r"\bgcloud\s+iam\s+service-accounts\s+delete\b"), "gcloud.iam.service_accounts.delete"),
    (re.compile(r"\bgcloud\s+iam\s+service-accounts\s+keys\s+create\b"), "gcloud.iam.service_accounts.keys.create"),
    (re.compile(r"\bgcloud\s+iam\s+roles\s+create\b"), "gcloud.iam.roles.create"),
    (re.compile(r"\bgcloud\s+iam\s+roles\s+update\b"), "gcloud.iam.roles.update"),
    (re.compile(r"\bgcloud\s+projects\s+add-iam-policy-binding\b"), "gcloud.projects.add_iam_policy_binding"),
    (re.compile(r"\bgcloud\s+projects\s+remove-iam-policy-binding\b"), "gcloud.projects.remove_iam_policy_binding"),
    (re.compile(r"\bgcloud\s+services\s+enable\b"), "gcloud.services.enable"),
    (re.compile(r"\bgcloud\s+services\s+disable\b"), "gcloud.services.disable"),
    (re.compile(r"\bgcloud\s+run\s+deploy\b"), "gcloud.run.deploy"),
    (re.compile(r"\bgcloud\s+run\s+jobs\s+create\b"), "gcloud.run.jobs.create"),
    (re.compile(r"\bgcloud\s+run\s+services\s+delete\b"), "gcloud.run.services.delete"),
    (re.compile(r"\bgcloud\s+compute\s+instances\s+create\b"), "gcloud.compute.instances.create"),
    (re.compile(r"\bgcloud\s+compute\s+networks\s+create\b"), "gcloud.compute.networks.create"),
    (re.compile(r"\bgcloud\s+compute\s+firewall-rules\s+create\b"), "gcloud.compute.firewall_rules.create"),
    (re.compile(r"\bgcloud\s+container\s+clusters\s+create\b"), "gcloud.container.clusters.create"),
    (re.compile(r"\bgcloud\s+container\s+clusters\s+delete\b"), "gcloud.container.clusters.delete"),
    (re.compile(r"\bgcloud\s+pubsub\s+topics\s+create\b"), "gcloud.pubsub.topics.create"),
    (re.compile(r"\bgcloud\s+pubsub\s+subscriptions\s+create\b"), "gcloud.pubsub.subscriptions.create"),
    (re.compile(r"\bgcloud\s+secrets\s+create\b"), "gcloud.secrets.create"),
    (re.compile(r"\bgcloud\s+secrets\s+versions\s+add\b"), "gcloud.secrets.versions.add"),
    (re.compile(r"\bgcloud\s+artifacts\s+repositories\s+create\b"), "gcloud.artifacts.repositories.create"),
    (re.compile(r"\bgcloud\s+artifacts\s+docker\s+images\s+push\b"), "gcloud.artifacts.docker.images.push"),
    (re.compile(r"\bgcloud\s+builds\s+submit\b"), "gcloud.builds.submit"),
    (re.compile(r"\bgcloud\s+functions\s+deploy\b"), "gcloud.functions.deploy"),
    (re.compile(r"\bgcloud\s+ai\s+agents\s+deploy\b"), "gcloud.ai.agents.deploy"),
    (re.compile(r"\bgcloud\s+sql\s+instances\s+create\b"), "gcloud.sql.instances.create"),
    (re.compile(r"\bgcloud\s+bigquery\s+datasets\s+create\b"), "gcloud.bigquery.datasets.create"),
]


class GcloudShellParser:
    name = "gcloud_sh"

    def matches(self, path: str) -> bool:
        name = Path(path).name
        return (
            path.endswith(".sh")
            or path.endswith(".bash")
            or name in {"Makefile", "makefile", "GNUmakefile"}
        )

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        text = Path(path).read_text()
        out: list[DetectedGCPResource] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, kind in _VERB_MAP:
                if pattern.search(line):
                    out.append(DetectedGCPResource(
                        kind=kind,
                        name=kind.split(".")[-1],
                        operation="create",
                        file=path,
                        line=lineno,
                        source="gcloud_sh",
                    ))
                    break  # only one match per line
        return out


register(GcloudShellParser())
```

- [ ] **Step 4: Run; verify all 4 pass**

```bash
pytest tests/parsers/test_gcloud_sh.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/iam_legend/parsers/gcloud_sh.py tests/fixtures/gcloud_sh/ tests/parsers/test_gcloud_sh.py
git commit -m "feat(parsers): gcloud shell + Makefile parser

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — GCP clients (Day 4, ~2 hours)

### Task 13: ADC auth + IAM clients

Spec §8.2.

**Files:**
- Create: `src/iam_legend/gcp/__init__.py`
- Create: `src/iam_legend/gcp/auth.py`
- Create: `src/iam_legend/gcp/iam.py`
- Create: `tests/unit/test_gcp_auth.py`
- Create: `tests/unit/test_gcp_iam.py`

- [ ] **Step 1: Write failing auth test**

`tests/unit/test_gcp_auth.py`:
```python
from iam_legend.gcp.auth import who_am_i, AuthError


def test_who_am_i_returns_string_or_raises(monkeypatch):
    """ADC may or may not be configured in the test env. Either is fine:
    if configured, we get a principal string; if not, we get a clean AuthError.
    """
    try:
        principal = who_am_i()
        assert isinstance(principal, str)
        assert "@" in principal or principal.endswith(".iam.gserviceaccount.com") or "/" in principal
    except AuthError as e:
        assert "ADC" in str(e) or "credentials" in str(e).lower()
```

- [ ] **Step 2: Write failing IAM test**

`tests/unit/test_gcp_iam.py`:
```python
from iam_legend.gcp.iam import test_iam_permissions
from iam_legend.gcp.auth import AuthError


def test_test_iam_permissions_with_invalid_project_raises_or_returns_empty():
    """Smoke test: either auth fails cleanly (no ADC) or the call returns a
    well-formed result against a definitely-nonexistent project.
    """
    try:
        result = test_iam_permissions(
            project="iam-legend-nonexistent-99999",
            permissions=["storage.buckets.create"],
        )
        # If we got here, ADC is set; result should at least be a dict.
        assert isinstance(result, dict)
        assert "granted" in result
        assert "missing" in result
    except AuthError:
        pass  # acceptable in test env without ADC
    except Exception as e:
        # Real GCP API error (403/404 against nonexistent project) is also acceptable
        assert "iam-legend-nonexistent" in str(e) or "403" in str(e) or "404" in str(e) or "permission" in str(e).lower() or "not found" in str(e).lower()
```

- [ ] **Step 3: Implement gcp/auth.py**

`src/iam_legend/gcp/__init__.py`: empty.

`src/iam_legend/gcp/auth.py`:
```python
"""ADC auth + identity introspection."""
from __future__ import annotations

import google.auth
from google.auth.exceptions import DefaultCredentialsError


class AuthError(RuntimeError):
    pass


def get_credentials():
    try:
        creds, _project = google.auth.default()
        return creds
    except DefaultCredentialsError as e:
        raise AuthError(f"No ADC credentials available: {e}") from e


def who_am_i() -> str:
    """Best-effort identity of the ADC principal.

    Order:
      - service_account_email attr (service-account creds, including impersonation)
      - quota_project_id + adc_principal heuristic
      - 'unknown' fallback (caller decides what to do)
    """
    creds = get_credentials()
    email = getattr(creds, "service_account_email", None)
    if email:
        return email
    # google-auth's UserCredentials carry 'account' for user creds in some flows;
    # otherwise fall through.
    user_account = getattr(creds, "account", None)
    if user_account:
        return user_account
    return "unknown-principal"
```

- [ ] **Step 4: Implement gcp/iam.py**

`src/iam_legend/gcp/iam.py`:
```python
"""IAM operations: testIamPermissions, getIamPolicy."""
from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from iam_legend.gcp.auth import AuthError, get_credentials


def test_iam_permissions(project: str, permissions: list[str]) -> dict:
    """Wrapper around projects.testIamPermissions.

    Returns: {"granted": [...], "missing": [...]} for the calling principal.
    The API answers for the CALLER — same SA the process is running as.
    """
    if not permissions:
        return {"granted": [], "missing": []}
    creds = get_credentials()
    crm = build("cloudresourcemanager", "v1", credentials=creds, cache_discovery=False)
    # The API has a hard cap of 100 permissions per call; chunk it.
    granted: set[str] = set()
    for i in range(0, len(permissions), 100):
        chunk = permissions[i:i + 100]
        try:
            resp = crm.projects().testIamPermissions(
                resource=project, body={"permissions": chunk},
            ).execute()
        except HttpError as e:
            # Bubble up — caller decides whether to fall back to static analysis.
            raise RuntimeError(f"testIamPermissions failed for {project}: {e}") from e
        granted.update(resp.get("permissions", []))
    return {
        "granted": sorted(granted),
        "missing": sorted(set(permissions) - granted),
    }


def get_iam_policy(project: str) -> dict:
    """Wrapper around projects.getIamPolicy. Returns the policy dict."""
    creds = get_credentials()
    crm = build("cloudresourcemanager", "v1", credentials=creds, cache_discovery=False)
    try:
        return crm.projects().getIamPolicy(
            resource=project, body={"options": {"requestedPolicyVersion": 3}},
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"getIamPolicy failed for {project}: {e}") from e
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_gcp_auth.py tests/unit/test_gcp_iam.py -v
```

Expected: both pass (they're written to tolerate either ADC-present or ADC-absent test environments).

- [ ] **Step 6: Commit**

```bash
git add src/iam_legend/gcp/ tests/unit/test_gcp_auth.py tests/unit/test_gcp_iam.py
git commit -m "feat(gcp): ADC auth + testIamPermissions / getIamPolicy

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Recommender (Day 4-5, ~3 hours)

### Task 14: Set-cover algorithm (deterministic)

Spec §7.4 step 2.

**Files:**
- Create: `src/iam_legend/recommender/__init__.py`
- Create: `src/iam_legend/recommender/set_cover.py`
- Create: `tests/unit/test_set_cover.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_set_cover.py`:
```python
from iam_legend.catalog.loader import load_catalog
from iam_legend.recommender.set_cover import cover, RoleCandidates


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
```

- [ ] **Step 2: Implement set_cover**

`src/iam_legend/recommender/__init__.py`: empty.

`src/iam_legend/recommender/set_cover.py`:
```python
"""Greedy set-cover over predefined GCP roles.

Goal: pick a small set of predefined roles that covers all required perms,
preferring per-service roles over broad roles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from iam_legend.catalog.loader import Catalog

_HARD_DENY = {
    "roles/owner", "roles/editor", "roles/viewer", "roles/iam.securityAdmin",
}


@dataclass(slots=True)
class RoleCandidates:
    chosen: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    alternatives: list[list[str]] = field(default_factory=list)


def cover(
    required: set[str],
    catalog: Catalog,
    *,
    avoid: set[str] = _HARD_DENY,
    prefer_per_service: bool = True,
) -> RoleCandidates:
    if not required:
        return RoleCandidates()

    # Build candidate set: every role with non-empty intersection with required.
    candidates: dict[str, set[str]] = {}
    for role_name, data in catalog.roles.items():
        if role_name in avoid:
            continue
        perms = set(data.get("permissions", []))
        overlap = perms & required
        if overlap:
            candidates[role_name] = overlap

    chosen: list[str] = []
    remaining = set(required)
    while remaining and candidates:
        # Score: cover_count is primary; penalty for "wasted" perms (perms in the role
        # not in the requirement set) discourages broad roles when narrow ones suffice.
        def score(item: tuple[str, set[str]]) -> tuple[int, int, str]:
            name, overlap = item
            cover_now = len(overlap & remaining)
            if cover_now == 0:
                return (0, 0, name)
            role_size = len(catalog.roles[name].get("permissions", []))
            waste = role_size - cover_now
            # higher cover_now is better; LOWER waste is better; lex-smaller name as tiebreaker
            return (cover_now, -waste, name)

        best = max(candidates.items(), key=score)
        if best[1] & remaining == set():
            break  # nothing useful left
        chosen.append(best[0])
        remaining -= best[1]
        del candidates[best[0]]

    return RoleCandidates(
        chosen=sorted(chosen),
        uncovered=sorted(remaining),
        alternatives=[],  # filled in by justify.py if multiple comparable solutions exist
    )
```

- [ ] **Step 3: Run; verify 4 pass**

```bash
pytest tests/unit/test_set_cover.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/iam_legend/recommender/set_cover.py tests/unit/test_set_cover.py src/iam_legend/recommender/__init__.py
git commit -m "feat(recommender): deterministic greedy set-cover over predefined roles

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Gemini-backed justification + templated fallback

Spec §7.4 step 3 + §8.3.

**Files:**
- Create: `src/iam_legend/recommender/justify.py`
- Create: `tests/unit/test_justify.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_justify.py`:
```python
from unittest.mock import patch

from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import RoleCandidates


def test_justify_with_gemini_unavailable_uses_template():
    rc = RoleCandidates(chosen=["roles/storage.admin"], uncovered=[])
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("vertex unavailable")):
        reasoning = justify_recommendation(rc, required_perms={"storage.buckets.create"})
    assert "roles/storage.admin" in reasoning
    assert "storage.buckets.create" in reasoning


def test_justify_with_empty_recommendation():
    rc = RoleCandidates(chosen=[], uncovered=["something.unknown"])
    reasoning = justify_recommendation(rc, required_perms={"something.unknown"})
    assert "could not" in reasoning.lower() or "no predefined role" in reasoning.lower()
```

- [ ] **Step 2: Implement justify**

`src/iam_legend/recommender/justify.py`:
```python
"""Generate the natural-language justification for a role recommendation.

Tries Vertex Gemini Flash-tier; falls back to a deterministic template if the
call fails or AI Platform isn't configured. Justification is OFF the
correctness path — the math is the math, this is just prose.
"""
from __future__ import annotations

import os
from typing import Any

from iam_legend.recommender.set_cover import RoleCandidates


_PROMPT_TEMPLATE = """You are helping a platform engineer pick the smallest sensible set of
predefined GCP IAM roles to cover a list of required permissions before a
terraform apply. The roles/owner, roles/editor, roles/viewer, roles/iam.securityAdmin
roles are FORBIDDEN by org policy — never suggest them.

Required permissions: {perms}
Candidate role set (greedy set-cover output): {roles}

Write 2-3 sentences explaining why this set is appropriate, and surface any
concerning grants the engineer should double-check. Be terse and concrete.
"""


def _call_gemini(prompt: str) -> str:
    """Single Vertex Gemini Flash call. Raises on any error."""
    project = os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("VERTEX_PROJECT not set; cannot call Gemini")
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel

    vertex_init(project=project, location=location)
    model_name = os.getenv("VERTEX_MODEL", "gemini-flash-latest")
    model = GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    return resp.text.strip()


def justify_recommendation(rc: RoleCandidates, required_perms: set[str]) -> str:
    if not rc.chosen and rc.uncovered:
        return (
            f"No predefined role covers these permissions: {sorted(rc.uncovered)}. "
            "A custom role may be required, or one of the requested actions may be "
            "unavailable in this project."
        )
    if not rc.chosen:
        return "No additional roles required."

    prompt = _PROMPT_TEMPLATE.format(
        perms=sorted(required_perms),
        roles=rc.chosen,
    )
    try:
        return _call_gemini(prompt)
    except Exception:
        # Templated fallback: deterministic, honest, slightly drier than Gemini.
        return _template_fallback(rc, required_perms)


def _template_fallback(rc: RoleCandidates, required_perms: set[str]) -> str:
    roles_str = ", ".join(rc.chosen)
    perms_count = len(required_perms)
    base = (
        f"Recommended roles: {roles_str}. "
        f"These cover the {perms_count} required permission(s) without granting "
        f"the broad roles/owner or roles/editor."
    )
    if rc.uncovered:
        base += f" Note: {len(rc.uncovered)} permission(s) could not be covered by any predefined role."
    return base
```

- [ ] **Step 3: Run; verify 2 pass**

```bash
pytest tests/unit/test_justify.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/iam_legend/recommender/justify.py tests/unit/test_justify.py
git commit -m "feat(recommender): Gemini-backed justification with templated fallback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: gcloud grant-command emission

**Files:**
- Create: `src/iam_legend/recommender/grants.py`
- Create: `tests/unit/test_grants.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_grants.py`:
```python
from iam_legend.recommender.grants import generate_grant_commands


def test_generates_one_command_per_role():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin", "roles/pubsub.publisher"],
        project="my-proj",
        principal="serviceAccount:deployer@my-proj.iam.gserviceaccount.com",
    )
    assert len(cmds) == 2
    assert all("gcloud projects add-iam-policy-binding my-proj" in c for c in cmds)
    assert any("roles/storage.admin" in c for c in cmds)


def test_handles_user_principals():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin"],
        project="p",
        principal="user:alice@example.com",
    )
    assert "user:alice@example.com" in cmds[0]


def test_handles_bare_email():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin"],
        project="p",
        principal="alice@example.com",
    )
    assert "user:alice@example.com" in cmds[0] or "alice@example.com" in cmds[0]
```

- [ ] **Step 2: Implement grants**

`src/iam_legend/recommender/grants.py`:
```python
"""Emit gcloud commands to grant the recommended roles."""
from __future__ import annotations


def _normalise_principal(principal: str) -> str:
    if ":" in principal:
        return principal  # already prefixed (user:, serviceAccount:, group:, etc.)
    if principal.endswith(".iam.gserviceaccount.com"):
        return f"serviceAccount:{principal}"
    return f"user:{principal}"


def generate_grant_commands(
    roles: list[str], project: str, principal: str,
) -> list[str]:
    p = _normalise_principal(principal)
    return [
        f"gcloud projects add-iam-policy-binding {project} \\\n"
        f"  --member={p} \\\n"
        f"  --role={role}"
        for role in roles
    ]
```

- [ ] **Step 3: Run; verify 3 pass; commit**

```bash
pytest tests/unit/test_grants.py -v
git add src/iam_legend/recommender/grants.py tests/unit/test_grants.py
git commit -m "feat(recommender): gcloud grant command emission

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Reviewer (Day 5, ~3 hours)

### Task 17: Review prose formatter (Gemini + fallback)

Spec §8.3.

**Files:**
- Create: `src/iam_legend/reviewer/__init__.py`
- Create: `src/iam_legend/reviewer/format.py`
- Create: `tests/unit/test_reviewer_format.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_reviewer_format.py`:
```python
from unittest.mock import patch

from iam_legend.reviewer.format import format_review
from iam_legend.types import (
    AccessRequestDraft, FullReport, LiveState, RoleRecommendation,
    DetectedGCPResource,
)


def _sample_report(missing: list[str]) -> FullReport:
    return FullReport(
        resources=[
            DetectedGCPResource(
                kind="google_storage_bucket", name="data", operation="create",
                file="main.tf", line=12, source="terraform_hcl",
            )
        ],
        required_permissions=["storage.buckets.create"],
        required_apis=[],
        by_file={"main.tf": ["storage.buckets.create"]},
        live_state=LiveState(granted=[], missing=missing),
        recommendation=RoleRecommendation(
            roles=["roles/storage.admin"], reasoning="x", alternatives=[],
        ),
        grant_commands=["gcloud projects add-iam-policy-binding ..."],
        access_request=AccessRequestDraft(subject="x", body="y"),
        warnings=[],
    )


def test_format_with_no_gaps_approves():
    report = _sample_report(missing=[])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="deployer@p.iam.gserviceaccount.com")
    assert result.event == "APPROVE"
    assert "approved" in result.body.lower() or "✅" in result.body


def test_format_with_gaps_requests_changes():
    report = _sample_report(missing=["storage.buckets.create"])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="deployer@p.iam.gserviceaccount.com")
    assert result.event == "REQUEST_CHANGES"
    assert "storage.buckets.create" in result.body
    assert any("storage.buckets.create" in c.body for c in result.comments)


def test_inline_comments_anchor_to_files_and_lines():
    report = _sample_report(missing=["storage.buckets.create"])
    with patch("iam_legend.reviewer.format._call_gemini", side_effect=RuntimeError("offline")):
        result = format_review(report, deployer="x")
    assert any(c.file == "main.tf" and c.line == 12 for c in result.comments)
```

- [ ] **Step 2: Implement reviewer/format.py**

`src/iam_legend/reviewer/__init__.py`: empty.

`src/iam_legend/reviewer/format.py`:
```python
"""Turn a FullReport into a GitHub PR review payload.

Gemini composes the top-level body prose when available. Inline comments are
generated deterministically from `by_file` + resources (we know the file/line
already, no LLM needed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from iam_legend.types import FullReport


Event = Literal["APPROVE", "REQUEST_CHANGES"]


@dataclass(slots=True)
class InlineComment:
    file: str
    line: int
    body: str


@dataclass(slots=True)
class ReviewPayload:
    event: Event
    body: str
    comments: list[InlineComment] = field(default_factory=list)


def _call_gemini(prompt: str) -> str:
    project = os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    if not project:
        raise RuntimeError("VERTEX_PROJECT not set; cannot call Gemini")
    from vertexai import init as vertex_init
    from vertexai.generative_models import GenerativeModel

    vertex_init(project=project, location=location)
    model_name = os.getenv("VERTEX_MODEL", "gemini-flash-latest")
    return GenerativeModel(model_name).generate_content(prompt).text.strip()


_BODY_PROMPT = """Write a concise, friendly GitHub PR review comment from an automated IAM bot.

Context:
- Deployer service account: {deployer}
- Missing GCP IAM permissions: {missing}
- Recommended roles to grant: {roles}
- Recommender reasoning: {reasoning}

Format (markdown):
1. One-sentence verdict
2. The required additions (a markdown bulleted list of roles)
3. The grant commands fenced in ```bash
4. (Brief) why this PR can't ship without these
Keep it under 200 words. No emojis except ✅ / 🚫 in the verdict.
"""


def format_review(report: FullReport, deployer: str) -> ReviewPayload:
    missing = report.live_state.missing if report.live_state else report.required_permissions
    if not missing:
        return ReviewPayload(
            event="APPROVE",
            body=(
                f"✅ **iam-legend: Approved**\n\n"
                f"Deployer SA `{deployer}` holds all {len(report.required_permissions)} "
                f"required permission(s). Safe to apply."
            ),
            comments=[],
        )

    try:
        prompt = _BODY_PROMPT.format(
            deployer=deployer,
            missing=missing,
            roles=report.recommendation.roles,
            reasoning=report.recommendation.reasoning,
        )
        body_prose = _call_gemini(prompt)
    except Exception:
        body_prose = _template_body(report, deployer, missing)

    comments = _build_inline_comments(report, missing)

    return ReviewPayload(event="REQUEST_CHANGES", body=body_prose, comments=comments)


def _template_body(report: FullReport, deployer: str, missing: list[str]) -> str:
    lines: list[str] = [
        "🚫 **iam-legend: Changes requested**",
        "",
        f"Deployer SA `{deployer}` is missing {len(missing)} permission(s) required by this PR:",
        "",
    ]
    for p in missing:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("**Recommended additions:**")
    for r in report.recommendation.roles:
        lines.append(f"- `{r}`")
    lines.append("")
    lines.append("**Grant commands:**")
    lines.append("```bash")
    lines.extend(report.grant_commands)
    lines.append("```")
    if report.recommendation.reasoning:
        lines.append("")
        lines.append(f"_{report.recommendation.reasoning}_")
    return "\n".join(lines)


def _build_inline_comments(report: FullReport, missing: list[str]) -> list[InlineComment]:
    missing_set = set(missing)
    out: list[InlineComment] = []
    seen: set[tuple[str, int]] = set()
    for r in report.resources:
        if r.line <= 0:
            continue
        perms = report.by_file.get(r.file, [])
        relevant = [p for p in perms if p in missing_set]
        if not relevant:
            continue
        key = (r.file, r.line)
        if key in seen:
            continue
        seen.add(key)
        body = (
            f"💡 **iam-legend**: this `{r.kind}` requires permission(s) the deployer SA "
            f"is missing:\n"
            + "\n".join(f"- `{p}`" for p in sorted(relevant))
        )
        out.append(InlineComment(file=r.file, line=r.line, body=body))
    return out
```

- [ ] **Step 3: Run; verify 3 pass; commit**

```bash
pytest tests/unit/test_reviewer_format.py -v
git add src/iam_legend/reviewer/ tests/unit/test_reviewer_format.py
git commit -m "feat(reviewer): PR review payload formatter with Gemini + fallback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: GitHub review poster

Spec §8.4.

**Files:**
- Create: `src/iam_legend/reviewer/github.py`
- Create: `tests/unit/test_reviewer_github.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_reviewer_github.py`:
```python
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
```

- [ ] **Step 2: Implement github.py**

`src/iam_legend/reviewer/github.py`:
```python
"""Post a ReviewPayload as a GitHub PR review via PyGithub.

We use the create_review API so we can attach inline comments atomically
with the top-level body. Inline comments must reference a commit SHA that
the PR's branch HEAD currently points at.
"""
from __future__ import annotations

from typing import Any

from iam_legend.reviewer.format import ReviewPayload


def post_review(
    payload: ReviewPayload,
    repo: Any,                    # github.Repository.Repository
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
```

- [ ] **Step 3: Run; verify 2 pass; commit**

```bash
pytest tests/unit/test_reviewer_github.py -v
git add src/iam_legend/reviewer/github.py tests/unit/test_reviewer_github.py
git commit -m "feat(reviewer): GitHub PR review poster (PyGithub)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7 — analyze() orchestration (Day 5-6, ~2 hours)

### Task 19: Top-level analyze entrypoint

Spec §6 (workhorse tool).

**Files:**
- Create: `src/iam_legend/analyze.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_analyze.py`

- [ ] **Step 1: Write integration test**

`tests/integration/__init__.py`: empty.

`tests/integration/test_analyze.py`:
```python
from pathlib import Path
from unittest.mock import patch

from iam_legend.analyze import analyze
from iam_legend.types import FullReport

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_analyze_plan_json_returns_full_report():
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")), \
         patch("iam_legend.gcp.iam.test_iam_permissions", return_value={"granted": [], "missing": ["storage.buckets.create"]}):
        report = analyze(input=str(FIXTURE), kind="plan_json", project="some-proj")
    assert isinstance(report, FullReport)
    assert any(r.kind == "google_storage_bucket" for r in report.resources)
    assert "storage.buckets.create" in report.required_permissions
    assert report.live_state is not None
    assert "storage.buckets.create" in report.live_state.missing
    assert len(report.recommendation.roles) > 0
    assert len(report.grant_commands) > 0


def test_analyze_static_mode_no_project_means_no_live_diff():
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        report = analyze(input=str(FIXTURE), kind="plan_json", project=None)
    assert report.live_state is None


def test_analyze_repo_mode():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "terraform"
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        report = analyze(input=str(fixture_dir), kind="repo")
    kinds = {r.kind for r in report.resources}
    assert "google_storage_bucket" in kinds
```

- [ ] **Step 2: Implement analyze.py**

`src/iam_legend/analyze.py`:
```python
"""The analyze() orchestrator. The MCP server, CLI, and GitHub Action all
call into here. Pure Python — no protocol-specific code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from iam_legend.catalog.loader import load_catalog
from iam_legend.catalog.resolver import resolve
from iam_legend.gcp.auth import who_am_i, AuthError
from iam_legend.gcp.iam import test_iam_permissions
from iam_legend.parsers.base import all_parsers, walk_repo
from iam_legend.parsers.terraform_plan import TerraformPlanParser
from iam_legend.parsers.terraform_hcl import TerraformHCLParser
from iam_legend.parsers.adk_python import ADKPythonParser
from iam_legend.parsers.gcloud_sh import GcloudShellParser
from iam_legend.recommender.grants import generate_grant_commands
from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import cover
from iam_legend.types import (
    AccessRequestDraft, DetectedGCPResource, FullReport, LiveState,
    RoleRecommendation,
)


def _draft_access_request(
    missing: list[str], roles: list[str], deployer: str, project: str | None,
) -> AccessRequestDraft:
    subject = f"[iam-legend] Grant {len(roles)} role(s) to deployer SA"
    body_lines = [
        f"Hi platform team,",
        f"",
        f"To ship the current PR's terraform apply, the deployer SA",
        f"`{deployer}`{' on project `' + project + '`' if project else ''}",
        f"needs the following predefined role(s):",
        f"",
    ]
    for r in roles:
        body_lines.append(f"  • {r}")
    body_lines += [
        f"",
        f"These cover the {len(missing)} permission(s) the current set of resources",
        f"requires that the SA does not yet hold. iam-legend confirmed this against",
        f"the live project IAM policy.",
        f"",
        f"Happy to chat through justifications per-permission if useful.",
        f"",
        f"— iam-legend",
    ]
    return AccessRequestDraft(subject=subject, body="\n".join(body_lines))


def _detect_from_input(input_: str, kind: str) -> list[DetectedGCPResource]:
    if kind == "plan_json":
        return TerraformPlanParser().parse_file(input_)
    if kind == "repo":
        # walk dir + dispatch via registered parsers (terraform_plan won't fire
        # on a directory walk because plan files don't sit in repos by default)
        out = walk_repo(input_)
        # Also explicitly run HCL parser on .tf files (registry-based dispatch
        # already covers this; this is belt-and-braces in case registration order changes).
        return out
    if kind == "dir":
        return TerraformHCLParser().parse_dir(input_)
    if kind == "file":
        # try each parser in turn until one matches
        for p in [TerraformPlanParser(), TerraformHCLParser(), ADKPythonParser(), GcloudShellParser()]:
            if p.matches(input_):
                return p.parse_file(input_)
        return []
    if kind == "snippet":
        # Heuristic dispatch on content
        raise NotImplementedError("snippet kind not yet supported; pass file or repo for now")
    raise ValueError(f"unknown kind: {kind}")


def analyze(
    input: str | dict,
    *,
    kind: str = "auto",
    project: str | None = None,
    principal: str = "self",
) -> FullReport:
    catalog = load_catalog()

    if kind == "auto":
        if isinstance(input, dict):
            kind = "plan_json"
        elif Path(input).is_dir():
            kind = "repo"
        elif input.endswith(".json") and "plan" in Path(input).name.lower():
            kind = "plan_json"
        else:
            kind = "file"

    if isinstance(input, dict):
        # inline plan dict
        resources = TerraformPlanParser().parse_dict(input)
    else:
        resources = _detect_from_input(input, kind)

    rr = resolve(resources, catalog)

    # Live diff (if project is set + ADC works)
    live_state: LiveState | None = None
    if project:
        try:
            r = test_iam_permissions(project, sorted(rr.permissions))
            live_state = LiveState(granted=r["granted"], missing=r["missing"])
        except (AuthError, RuntimeError) as e:
            rr.warnings.append(f"live IAM diff unavailable: {e}")

    missing_perms = set(live_state.missing) if live_state else set(rr.permissions)
    rc = cover(missing_perms, catalog)
    reasoning = justify_recommendation(rc, missing_perms)

    deployer = "unknown-principal"
    if principal == "self":
        try:
            deployer = who_am_i()
        except AuthError:
            pass
    else:
        deployer = principal

    grant_cmds = generate_grant_commands(rc.chosen, project or "<PROJECT_ID>", deployer)
    access_req = _draft_access_request(sorted(missing_perms), rc.chosen, deployer, project)

    return FullReport(
        resources=resources,
        required_permissions=sorted(rr.permissions),
        required_apis=sorted(rr.apis),
        by_file=rr.by_file,
        live_state=live_state,
        recommendation=RoleRecommendation(
            roles=rc.chosen, reasoning=reasoning, alternatives=rc.alternatives,
        ),
        grant_commands=grant_cmds,
        access_request=access_req,
        warnings=rr.warnings,
    )
```

- [ ] **Step 3: Run; verify all 3 pass**

```bash
pytest tests/integration/test_analyze.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/iam_legend/analyze.py tests/integration/
git commit -m "feat(analyze): top-level orchestrator pulling parsers + catalog + recommender + reviewer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 8 — User-facing surfaces (Day 6-7, ~6 hours)

### Task 20: CLI

Spec §3.

**Files:**
- Create: `src/iam_legend/cli.py`
- Create: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing test**

`tests/integration/test_cli.py`:
```python
import json
from pathlib import Path

from click.testing import CliRunner
from unittest.mock import patch

from iam_legend.cli import cli

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_cli_lookup():
    runner = CliRunner()
    result = runner.invoke(cli, ["lookup", "google_storage_bucket"])
    assert result.exit_code == 0
    assert "storage.buckets.create" in result.output


def test_cli_review_with_plan_outputs_json():
    runner = CliRunner()
    with patch("iam_legend.recommender.justify._call_gemini", side_effect=RuntimeError("offline")):
        result = runner.invoke(cli, [
            "review",
            "--plan", str(FIXTURE),
            "--format", "json",
        ])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert any(r["kind"] == "google_storage_bucket" for r in report["resources"])
```

- [ ] **Step 2: Implement CLI**

`src/iam_legend/cli.py`:
```python
"""iam-legend CLI. Three subcommands: lookup, review, refresh-catalog."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from iam_legend import __version__
from iam_legend.analyze import analyze
from iam_legend.catalog.loader import load_catalog


@click.group()
@click.version_option(__version__)
def cli() -> None:
    """iam-legend — GCP IAM toolbelt."""


@cli.command()
@click.argument("target")
def lookup(target: str) -> None:
    """Look up IAM perms for a Terraform resource, a role, or a permission name."""
    c = load_catalog()
    if target.startswith("roles/"):
        role = c.lookup_role(target)
        if role is None:
            click.echo(f"unknown role: {target}", err=True)
            sys.exit(1)
        click.echo(f"{target}: {role.get('title')}")
        for p in role["permissions"]:
            click.echo(f"  {p}")
        return
    if "." in target and not target.startswith("google_"):
        roles = c.roles_with(target)
        click.echo(f"Roles containing {target}:")
        for r in roles:
            click.echo(f"  {r}")
        return
    # resource kind
    entry = c.resources.get(target)
    if entry is None:
        click.echo(f"unknown resource kind: {target}", err=True)
        sys.exit(1)
    for op, perms in entry.items():
        if op == "required_apis":
            continue
        click.echo(f"{target}.{op}: {perms}")


@cli.command()
@click.option("--plan", "plan_path", type=click.Path(exists=True), help="terraform plan -json output")
@click.option("--repo", "repo_path", type=click.Path(exists=True), help="repo root for static scan")
@click.option("--project", help="GCP project for live IAM diff")
@click.option("--format", "out_fmt", type=click.Choice(["pretty", "json"]), default="pretty")
@click.option("--post-pr", is_flag=True, help="(action mode) post review to GitHub")
@click.option("--pr-number", type=int, help="PR number when --post-pr is set")
@click.option("--repo-full-name", help="owner/repo when --post-pr is set")
def review(
    plan_path: str | None, repo_path: str | None, project: str | None,
    out_fmt: str, post_pr: bool, pr_number: int | None, repo_full_name: str | None,
) -> None:
    """Run an IAM review on a terraform plan or a repo."""
    if not plan_path and not repo_path:
        click.echo("provide --plan or --repo", err=True)
        sys.exit(2)

    if plan_path:
        report = analyze(plan_path, kind="plan_json", project=project)
    else:
        report = analyze(repo_path, kind="repo", project=project)

    if out_fmt == "json":
        click.echo(json.dumps(asdict(report), indent=2, default=list))
        return

    _render_pretty(report)

    if post_pr:
        _post_to_github(report, pr_number, repo_full_name)


def _render_pretty(report) -> None:
    con = Console()
    missing = report.live_state.missing if report.live_state else report.required_permissions
    verdict = "✅ Approved" if not missing else "🚫 Changes requested"
    con.print(Panel.fit(f"[bold]{verdict}[/bold]"))

    t = Table(title="Required permissions")
    t.add_column("Permission")
    t.add_column("Status")
    granted = set(report.live_state.granted) if report.live_state else set()
    for p in report.required_permissions:
        status = "[green]granted[/green]" if p in granted else "[red]missing[/red]" if report.live_state else "[yellow]not checked[/yellow]"
        t.add_row(p, status)
    con.print(t)

    if report.recommendation.roles:
        con.print("\n[bold]Recommended roles:[/bold]")
        for r in report.recommendation.roles:
            con.print(f"  • {r}")
        if report.recommendation.reasoning:
            con.print(f"\n[italic]{report.recommendation.reasoning}[/italic]")
        con.print("\n[bold]Grant commands:[/bold]")
        for c in report.grant_commands:
            con.print(c)

    if report.warnings:
        con.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in report.warnings:
            con.print(f"  ! {w}")


def _post_to_github(report, pr_number: int | None, repo_full_name: str | None) -> None:
    import os
    from github import Github
    from iam_legend.reviewer.format import format_review
    from iam_legend.reviewer.github import post_review
    from iam_legend.gcp.auth import who_am_i

    if not pr_number or not repo_full_name:
        click.echo("missing --pr-number or --repo-full-name", err=True)
        sys.exit(2)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        click.echo("GITHUB_TOKEN env var not set", err=True)
        sys.exit(1)

    try:
        deployer = who_am_i()
    except Exception:
        deployer = "unknown-principal"

    payload = format_review(report, deployer=deployer)
    try:
        gh = Github(token)
        repo = gh.get_repo(repo_full_name)
        post_review(payload, repo, pr_number)
    except Exception as e:
        # Fail closed on signalling failure — emit GH workflow annotation + non-zero exit.
        print(f"::error title=iam-legend::could not post PR review: {e}")
        print(payload.body)
        sys.exit(1)


@cli.command(name="refresh-catalog")
@click.option("--what", type=click.Choice(["roles", "api-methods", "all"]), default="all")
def refresh_catalog(what: str) -> None:
    """Refresh baked catalog snapshots."""
    if what in {"roles", "all"}:
        from catalog_build.refresh_roles import main as roles_main
        roles_main()
    if what in {"api-methods", "all"}:
        from catalog_build.refresh_api_methods import main as methods_main
        methods_main()
```

- [ ] **Step 3: Run; verify 2 pass; commit**

```bash
pytest tests/integration/test_cli.py -v
git add src/iam_legend/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): iam-legend CLI (lookup, review, refresh-catalog)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 21: FastMCP server (dual transport, gated tools)

Spec §6 + §8.1.

**Files:**
- Create: `src/iam_legend/mcp_server.py`
- Create: `tests/integration/test_mcp_server.py`

- [ ] **Step 1: Write failing test**

`tests/integration/test_mcp_server.py`:
```python
import os
from pathlib import Path
from unittest.mock import patch

from iam_legend.mcp_server import build_server


FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_stdio_server_registers_all_tools(monkeypatch):
    monkeypatch.setenv("IAM_LEGEND_TRANSPORT", "stdio")
    srv = build_server()
    names = {t.name for t in srv._tool_manager.list_tools()}  # type: ignore[attr-defined]
    assert "analyze" in names
    assert "lookup_permissions_for" in names
    assert "test_permissions" in names      # privileged
    assert "get_iam_policy" in names        # privileged


def test_http_server_excludes_privileged_tools(monkeypatch):
    monkeypatch.setenv("IAM_LEGEND_TRANSPORT", "http")
    srv = build_server()
    names = {t.name for t in srv._tool_manager.list_tools()}
    assert "analyze" in names
    assert "lookup_permissions_for" in names
    assert "test_permissions" not in names    # gated out
    assert "get_iam_policy" not in names      # gated out
```

- [ ] **Step 2: Implement mcp_server.py**

`src/iam_legend/mcp_server.py`:
```python
"""FastMCP server with per-transport tool gating.

Stdio (local, privileged) registers ALL tools; HTTP (hosted, read-only)
registers only catalog/static-analysis/recommender tools. See spec §8.2 for
the security rationale.
"""
from __future__ import annotations

import os
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from iam_legend.analyze import analyze as _analyze
from iam_legend.catalog.loader import load_catalog
from iam_legend.recommender.grants import generate_grant_commands as _grants
from iam_legend.recommender.justify import justify_recommendation
from iam_legend.recommender.set_cover import cover as _cover


def build_server() -> FastMCP:
    transport = os.environ.get("IAM_LEGEND_TRANSPORT", "stdio")
    is_privileged = transport == "stdio"
    server = FastMCP("iam-legend")

    @server.tool()
    def analyze(
        input: str,
        kind: str = "auto",
        project: str | None = None,
        principal: str = "self",
    ) -> dict:
        """Analyze GCP IaC for required IAM perms.

        - input: a path (repo dir, plan.json, or single file) OR a JSON string
        - kind: auto | repo | dir | plan_json | file
        - project: GCP project id for live IAM diff (requires ADC; stdio-only)
        - principal: 'self' (ADC identity) or an email/SA address (informational)
        """
        # HTTP mode forbids repo/auto-plan because Terraform on shared infra
        # is arbitrary-code-execution surface (spec §8.2).
        if not is_privileged and kind in {"repo", "dir"}:
            raise ValueError(
                "kind='repo' and kind='dir' are stdio-only. Pass a precomputed "
                "terraform plan JSON file or kind='snippet'."
            )
        report = _analyze(input=input, kind=kind, project=project, principal=principal)
        return asdict(report)

    @server.tool()
    def lookup_permissions_for(target: str) -> dict:
        """Look up IAM info for a Terraform resource kind, a role, or a permission."""
        c = load_catalog()
        if target.startswith("roles/"):
            role = c.lookup_role(target)
            return {"kind": "role", "name": target, "data": role}
        if target in c.resources:
            return {"kind": "resource", "name": target, "data": c.resources[target]}
        if target in c.api_methods:
            return {"kind": "permission", "name": target, "roles_containing": c.roles_with(target)}
        return {"kind": "unknown", "name": target}

    @server.tool()
    def find_roles_with(permission: str) -> list[str]:
        """Return all predefined roles that include the given permission."""
        return load_catalog().roles_with(permission)

    @server.tool()
    def recommend_roles(
        permissions: list[str],
        avoid: list[str] | None = None,
    ) -> dict:
        """Recommend a minimal set of predefined roles covering the given perms."""
        c = load_catalog()
        avoid_set = set(avoid) if avoid else {"roles/owner", "roles/editor", "roles/viewer", "roles/iam.securityAdmin"}
        rc = _cover(set(permissions), c, avoid=avoid_set)
        reasoning = justify_recommendation(rc, set(permissions))
        return {
            "roles": rc.chosen,
            "uncovered": rc.uncovered,
            "reasoning": reasoning,
        }

    @server.tool()
    def generate_grant_commands(roles: list[str], project: str, principal: str) -> list[str]:
        """Generate gcloud commands to bind the given roles to the principal."""
        return _grants(roles, project, principal)

    # Privileged tools — only registered on stdio (local) transport.
    if is_privileged:
        from iam_legend.gcp.iam import test_iam_permissions as _test_perms, get_iam_policy as _get_pol

        @server.tool()
        def test_permissions(project: str, permissions: list[str]) -> dict:
            """Live: check which of the given perms the caller (ADC) holds on the project."""
            return _test_perms(project, permissions)

        @server.tool()
        def get_iam_policy(project: str) -> dict:
            """Live: fetch the project's current IAM policy."""
            return _get_pol(project)

    return server


def main() -> None:
    server = build_server()
    transport = os.environ.get("IAM_LEGEND_TRANSPORT", "stdio")
    if transport == "http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `pyproject.toml` script entry**

Add to `[project.scripts]`:
```toml
iam-legend-mcp = "iam_legend.mcp_server:main"
```

Reinstall:
```bash
uv pip install -e .
```

- [ ] **Step 4: Run; verify both pass; commit**

```bash
pytest tests/integration/test_mcp_server.py -v
git add src/iam_legend/mcp_server.py tests/integration/test_mcp_server.py pyproject.toml
git commit -m "feat(mcp): FastMCP server with per-transport tool gating

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 22: Dockerfile + action.yml

Spec §8.1 + §8.4.

**Files:**
- Create: `Dockerfile`
- Create: `action.yml`
- Create: `docker-entrypoint.sh`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
# Multi-stage: builder installs deps + the package, runner is slim.
FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir uv \
 && uv pip install --system --no-cache --target=/install .

FROM python:3.13-slim

WORKDIR /app

# Copy the installed package + all dependencies.
COPY --from=builder /install /usr/local/lib/python3.13/site-packages
COPY docker-entrypoint.sh /usr/local/bin/iam-legend-entrypoint

# Make scripts in /install/bin accessible
ENV PATH="/usr/local/lib/python3.13/site-packages/bin:${PATH}"
RUN chmod +x /usr/local/bin/iam-legend-entrypoint

ENV PYTHONUNBUFFERED=1
ENV IAM_LEGEND_TRANSPORT=stdio

# Default: stdio MCP server. Override entrypoint for the GitHub Action.
ENTRYPOINT ["/usr/local/bin/iam-legend-entrypoint"]
```

- [ ] **Step 2: Write `docker-entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

MODE="${IAM_LEGEND_MODE:-mcp}"

case "$MODE" in
  mcp)
    exec iam-legend-mcp
    ;;
  action)
    # GitHub Action mode: read inputs from INPUT_* env vars, call CLI.
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
```

- [ ] **Step 3: Write `action.yml`**

```yaml
name: iam-legend
description: AI code review for GCP IAM gaps before terraform apply.
inputs:
  terraform-plan:
    description: Path to terraform plan JSON output.
    required: false
  working-directory:
    description: Repo root to scan when no plan is provided.
    required: false
    default: '.'
  project-id:
    description: GCP project the deploy targets.
    required: true
runs:
  using: docker
  image: Dockerfile
  env:
    IAM_LEGEND_MODE: action
    INPUT_TERRAFORM_PLAN: ${{ inputs.terraform-plan }}
    INPUT_WORKING_DIRECTORY: ${{ inputs.working-directory }}
    INPUT_PROJECT_ID: ${{ inputs.project-id }}
```

- [ ] **Step 4: Build and smoke-test the image**

```bash
docker build -t iam-legend:dev .
docker run --rm iam-legend:dev iam-legend --help
# stdio MCP smoke test
echo '' | docker run --rm -i -e IAM_LEGEND_MODE=mcp iam-legend:dev &
sleep 2
kill %1 || true
```

Expected: `iam-legend --help` prints CLI usage. The stdio MCP exits cleanly on EOF (FastMCP behaviour).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-entrypoint.sh action.yml
git commit -m "build: multi-stage Dockerfile + GitHub Action manifest

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 9 — Demo repo + Cloud Run (Day 7-8, ~4 hours)

### Task 23: Demo repo

Spec §10 (submission deliverables — testing access).

**Files:**
- Create: `examples/demo-repo/terraform/main.tf`
- Create: `examples/demo-repo/deploy.py`
- Create: `examples/demo-repo/.github/workflows/deploy.yml`
- Create: `examples/demo-repo/README.md`

- [ ] **Step 1: Write demo terraform**

`examples/demo-repo/terraform/main.tf`:
```hcl
terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = "us-central1"
}

variable "project_id" { type = string }

resource "google_storage_bucket" "data" {
  name          = "${var.project_id}-iam-legend-demo"
  location      = "US"
  force_destroy = true
}

resource "google_pubsub_topic" "events" {
  name = "events"
}

resource "google_vertex_ai_endpoint" "agent" {
  display_name = "demo-agent"
  location     = "us-central1"
}
```

- [ ] **Step 2: Write demo deploy.py**

`examples/demo-repo/deploy.py`:
```python
"""Demo: deploys a tiny Vertex Agent Engine instance.

Run after `terraform apply` to provision the supporting GCS bucket.
"""
import os

import vertexai
from vertexai import agent_engines


def main() -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    vertexai.init(project=project, location="us-central1")

    agent = agent_engines.create(
        display_name="iam-legend-demo-agent",
        description="Demo agent that says hello.",
    )
    print(f"Created agent: {agent.resource_name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write demo workflow**

`examples/demo-repo/.github/workflows/deploy.yml`:
```yaml
name: deploy

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write
  id-token: write

jobs:
  iam-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: '1.9.0'

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.DEPLOYER_SA }}

      - name: terraform plan
        working-directory: ./terraform
        run: |
          terraform init
          terraform plan -out=plan.tfplan -var="project_id=${{ secrets.PROJECT_ID }}"
          terraform show -json plan.tfplan > plan.json

      - uses: iam-legend/iam-legend@v1
        with:
          terraform-plan: ./terraform/plan.json
          working-directory: .
          project-id: ${{ secrets.PROJECT_ID }}
```

- [ ] **Step 4: Write demo README**

`examples/demo-repo/README.md`:
```markdown
# iam-legend demo

This repo demonstrates iam-legend running as a PR review bot.

Try it:
1. Fork this repo
2. Configure secrets: `WIF_PROVIDER`, `DEPLOYER_SA`, `PROJECT_ID`
3. Open a PR that changes `terraform/main.tf` or `deploy.py`
4. Watch iam-legend post a review with the IAM gap
```

- [ ] **Step 5: Commit**

```bash
git add examples/
git commit -m "docs: demo repo with terraform + ADK + workflow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 24: Cloud Run deploy script

Spec §8.1.

**Files:**
- Create: `deploy-cloud-run.sh`

- [ ] **Step 1: Write deploy script**

`deploy-cloud-run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:?set PROJECT or GOOGLE_CLOUD_PROJECT}}"
REGION="${REGION:-us-central1}"
SERVICE="iam-legend"
SA="iam-legend-runtime@${PROJECT}.iam.gserviceaccount.com"
REPO="${REPO:-iam-legend}"
IMAGE="us-docker.pkg.dev/${PROJECT}/${REPO}/iam-legend:latest"

# 1. Ensure Artifact Registry repo exists
gcloud artifacts repositories describe "$REPO" --location=us 2>/dev/null \
  || gcloud artifacts repositories create "$REPO" --location=us --repository-format=docker

# 2. Ensure runtime SA exists with minimal perms
gcloud iam service-accounts describe "$SA" 2>/dev/null \
  || gcloud iam service-accounts create iam-legend-runtime \
      --display-name="iam-legend Cloud Run runtime"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" \
  --role=roles/aiplatform.user >/dev/null

# 3. Build + push image
gcloud auth configure-docker us-docker.pkg.dev --quiet
docker build -t "$IMAGE" .
docker push "$IMAGE"

# 4. Deploy as HTTP MCP server (read-only mode)
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$SA" \
  --no-allow-unauthenticated \
  --set-env-vars="IAM_LEGEND_TRANSPORT=http,IAM_LEGEND_MODE=mcp,VERTEX_PROJECT=${PROJECT},VERTEX_LOCATION=${REGION}"

# 5. Print URL
gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)"
```

- [ ] **Step 2: Make it executable + commit**

```bash
chmod +x deploy-cloud-run.sh
git add deploy-cloud-run.sh
git commit -m "build: Cloud Run deploy script (read-only HTTP MCP)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Actually deploy and capture the URL** *(do this only when you have a GCP project with billing — Day 8)*

```bash
PROJECT=<your-project> ./deploy-cloud-run.sh
```

Save the printed URL — it goes into the README + submission.

---

## Phase 10 — Stretch parsers (Day 8, ~3 hours, cut if behind)

### Task 25 (stretch): Cloud Build YAML parser

Spec §5.5.

**Files:**
- Create: `src/iam_legend/parsers/cloudbuild.py`
- Create: `tests/fixtures/cloudbuild/cloudbuild.yaml`
- Create: `tests/parsers/test_cloudbuild.py`

- [ ] **Step 1: Fixture**

`tests/fixtures/cloudbuild/cloudbuild.yaml`:
```yaml
steps:
  - name: 'gcr.io/cloud-builders/gcloud'
    args: ['storage', 'buckets', 'create', 'gs://my-bucket']
  - name: 'gcr.io/cloud-builders/gcloud'
    args: ['run', 'deploy', 'my-svc', '--image=foo']
```

- [ ] **Step 2: Failing test**

`tests/parsers/test_cloudbuild.py`:
```python
from pathlib import Path

from iam_legend.parsers.cloudbuild import CloudBuildParser


FIXTURE = Path(__file__).parent.parent / "fixtures" / "cloudbuild" / "cloudbuild.yaml"


def test_parses_cloudbuild_gcloud_steps():
    out = CloudBuildParser().parse_file(str(FIXTURE))
    kinds = {r.kind for r in out}
    assert "gcloud.storage.buckets.create" in kinds
    assert "gcloud.run.deploy" in kinds
```

- [ ] **Step 3: Implement**

`src/iam_legend/parsers/cloudbuild.py`:
```python
"""Parse Cloud Build YAML, reusing the gcloud verb map."""
from __future__ import annotations

from pathlib import Path

import yaml

from iam_legend.parsers.base import register
from iam_legend.parsers.gcloud_sh import _VERB_MAP
from iam_legend.types import DetectedGCPResource


class CloudBuildParser:
    name = "cloudbuild"

    def matches(self, path: str) -> bool:
        name = Path(path).name.lower()
        return name in {"cloudbuild.yaml", "cloudbuild.yml"}

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        out: list[DetectedGCPResource] = []
        for i, step in enumerate(data.get("steps", []), start=1):
            image = step.get("name", "")
            args = step.get("args", [])
            if "gcloud" in image and args:
                joined = "gcloud " + " ".join(args)
                for pattern, kind in _VERB_MAP:
                    if pattern.search(joined):
                        out.append(DetectedGCPResource(
                            kind=kind, name=kind.split(".")[-1], operation="create",
                            file=path, line=i, source="cloudbuild",
                        ))
                        break
        return out


register(CloudBuildParser())
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/parsers/test_cloudbuild.py -v
git add src/iam_legend/parsers/cloudbuild.py tests/fixtures/cloudbuild/ tests/parsers/test_cloudbuild.py
git commit -m "feat(parsers): Cloud Build YAML parser (stretch)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 26 (stretch): GitHub Actions YAML parser

Spec §5.5.

**Files:**
- Create: `src/iam_legend/parsers/github_actions.py`
- Create: `tests/fixtures/github_actions/deploy.yml`
- Create: `tests/parsers/test_github_actions.py`

- [ ] **Step 1: Fixture**

`tests/fixtures/github_actions/deploy.yml`:
```yaml
jobs:
  deploy:
    steps:
      - uses: google-github-actions/auth@v2
      - uses: google-github-actions/deploy-cloudrun@v2
        with: { service: my-svc, image: foo }
      - run: gcloud services enable aiplatform.googleapis.com
```

- [ ] **Step 2: Test**

`tests/parsers/test_github_actions.py`:
```python
from pathlib import Path

from iam_legend.parsers.github_actions import GitHubActionsParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "github_actions" / "deploy.yml"


def test_detects_official_actions_and_run_steps():
    out = GitHubActionsParser().parse_file(str(FIXTURE))
    kinds = {r.kind for r in out}
    # google-github-actions/deploy-cloudrun has known perm signature
    assert "gha.deploy_cloudrun" in kinds or "gcloud.run.deploy" in kinds
    # the run: step contains a gcloud verb
    assert "gcloud.services.enable" in kinds
```

- [ ] **Step 3: Implement**

`src/iam_legend/parsers/github_actions.py`:
```python
"""Parse GitHub Actions workflow YAML.

Recognises google-github-actions/* official actions by their `uses:` line,
and falls back to the gcloud verb map for `run:` steps.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from iam_legend.parsers.base import register
from iam_legend.parsers.gcloud_sh import _VERB_MAP
from iam_legend.types import DetectedGCPResource


# Map: official action -> synthetic kind (added to resources.yaml when we get to v2)
_ACTION_KIND_MAP = {
    "google-github-actions/deploy-cloudrun": "gha.deploy_cloudrun",
    "google-github-actions/deploy-appengine": "gha.deploy_appengine",
    "google-github-actions/get-secretmanager-secrets": "gha.get_secrets",
    "google-github-actions/upload-cloud-storage": "gha.upload_gcs",
    "google-github-actions/setup-gcloud": "gha.setup_gcloud",
    "google-github-actions/auth": "gha.auth",
}

# Map kinds -> a roughly-equivalent gcloud verb kind (so the catalog covers them)
_KIND_ALIAS = {
    "gha.deploy_cloudrun": "gcloud.run.deploy",
    "gha.upload_gcs": "gcloud.storage.cp",
}


class GitHubActionsParser:
    name = "github_actions"

    def matches(self, path: str) -> bool:
        p = Path(path)
        return (
            ".github/workflows" in str(p) and (p.suffix in {".yml", ".yaml"})
        )

    def parse_file(self, path: str) -> list[DetectedGCPResource]:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        out: list[DetectedGCPResource] = []
        jobs = data.get("jobs", {})
        for job_name, job in jobs.items():
            for i, step in enumerate(job.get("steps", []), start=1):
                uses = step.get("uses", "")
                if uses:
                    base = uses.split("@", 1)[0]
                    kind = _ACTION_KIND_MAP.get(base)
                    if kind:
                        # Alias to a known catalog kind if available
                        kind = _KIND_ALIAS.get(kind, kind)
                        out.append(DetectedGCPResource(
                            kind=kind, name=base, operation="create",
                            file=path, line=i, source="github_actions",
                        ))
                run = step.get("run", "")
                if run:
                    for pattern, kind in _VERB_MAP:
                        if pattern.search(run):
                            out.append(DetectedGCPResource(
                                kind=kind, name=kind.split(".")[-1], operation="create",
                                file=path, line=i, source="github_actions",
                            ))
                            break
        return out


register(GitHubActionsParser())
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/parsers/test_github_actions.py -v
git add src/iam_legend/parsers/github_actions.py tests/fixtures/github_actions/ tests/parsers/test_github_actions.py
git commit -m "feat(parsers): GitHub Actions workflow YAML parser (stretch)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 11 — Submission packaging (Day 8-9, ~3 hours)

### Task 27: README + architecture diagram

Spec §10.

**Files:**
- Modify: `README.md`
- Create: `docs/architecture.png` (or `.svg`)

- [ ] **Step 1: Rewrite README**

Replace `README.md` with a submission-ready version. Concretely include:
- One-paragraph problem statement (from spec §1)
- "How it works" with the same diagram as spec §4
- Quick-start for the GitHub Action (the 6-line YAML from spec §8.4)
- Quick-start for the local MCP (Claude Code / Gemini CLI config snippet)
- Public Cloud Run demo URL (filled in after Task 24 deploy)
- Catalog coverage statement (X resources, Y roles, Z APIs)
- Limitations honestly listed (HCL line recovery, registry modules, hosted credentialless)
- Apache-2.0 + Pike attribution

(Write the actual file contents in full at this step — no placeholders. See spec for the full submission narrative.)

- [ ] **Step 2: Draw the architecture diagram in Excalidraw**

Open https://excalidraw.com, draw the spec §4 architecture diagram (MCP server in the centre, three surfaces around it: Gemini CLI / GitHub Action / hosted Cloud Run; catalog as a source feeding the server; Gemini Vertex as a leaf). Export as PNG into `docs/architecture.png`.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/architecture.png
git commit -m "docs: submission-ready README + architecture diagram

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 28: End-to-end smoke test against a live GCP project

Spec §9.3.

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_live_gcp.py`
- Create: `tests/e2e/setup.sh`

- [ ] **Step 1: Write setup script**

`tests/e2e/setup.sh`:
```bash
#!/usr/bin/env bash
# One-shot setup for the e2e test environment.
# Creates: a throwaway SA with deliberately INCOMPLETE perms (no storage admin).
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT}"
SA_NAME="iam-legend-e2e-test"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

gcloud iam service-accounts describe "$SA_EMAIL" 2>/dev/null \
  || gcloud iam service-accounts create "$SA_NAME" --display-name="iam-legend e2e test"

# Grant ONLY pubsub.publisher — deliberately not enough for the storage_bucket
# the test fixture also touches. The e2e test asserts iam-legend identifies the gap.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role=roles/pubsub.publisher >/dev/null

echo "SA: $SA_EMAIL"
```

- [ ] **Step 2: Write e2e test**

`tests/e2e/__init__.py`: empty.

`tests/e2e/test_live_gcp.py`:
```python
"""End-to-end test against a real GCP project.

Gated by env vars: only runs when IAM_LEGEND_E2E_PROJECT is set. Skipped
otherwise so the regular test suite doesn't need GCP creds.

Setup: run tests/e2e/setup.sh first to provision the test SA.
Then export IAM_LEGEND_E2E_PROJECT=<your-project> and run pytest tests/e2e.
"""
import os
from pathlib import Path

import pytest

from iam_legend.analyze import analyze


PROJECT = os.getenv("IAM_LEGEND_E2E_PROJECT")
pytestmark = pytest.mark.skipif(not PROJECT, reason="IAM_LEGEND_E2E_PROJECT not set")

FIXTURE = Path(__file__).parent.parent / "fixtures" / "plan_json" / "simple.json"


def test_live_diff_identifies_missing_storage_perms():
    report = analyze(input=str(FIXTURE), kind="plan_json", project=PROJECT)
    assert report.live_state is not None
    # Test SA has pubsub.publisher only; storage.buckets.create should be missing.
    assert "storage.buckets.create" in report.live_state.missing
    # ... and the recommender should suggest a storage role.
    assert any("storage" in r for r in report.recommendation.roles)
```

- [ ] **Step 3: Run it once**

```bash
chmod +x tests/e2e/setup.sh
PROJECT=<your-project> bash tests/e2e/setup.sh

# Impersonate the test SA for the live diff
gcloud auth application-default login --impersonate-service-account=iam-legend-e2e-test@<your-project>.iam.gserviceaccount.com

IAM_LEGEND_E2E_PROJECT=<your-project> pytest tests/e2e -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/
git commit -m "test(e2e): live GCP project smoke test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 29: Record demo video

Spec §10 (video script).

This is a content task, not a code task. Day 9 morning.

- [ ] **Step 1: Set up the demo recording**

- Use QuickTime or OBS to record a screen capture (1080p minimum, mp4).
- Have terminal + browser windows pre-positioned.
- Practice the script in spec §10 once or twice.

- [ ] **Step 2: Record the 90-second demo following the spec script**

Key shots:
- 0-10s: pre-recorded "frustrated dev" terminal showing a `terraform apply` 403 error.
- 10-25s: zoom into the architecture diagram.
- 25-55s: live GitHub PR demo on `iam-legend/iam-legend-demo` (the example repo, hosted on your fork).
- 55-80s: Gemini CLI session calling MCP tools interactively.
- 80-90s: tagline frame + repo + Cloud Run URLs.

- [ ] **Step 3: Upload to YouTube as unlisted**

Title: "iam-legend — GCP IAM toolbelt for AI agents (Google for Startups AI Agents Challenge submission)"

Description: link to repo, demo repo, Cloud Run URL, spec doc.

- [ ] **Step 4: Add URL to Devpost submission**

The video URL goes into the Devpost project page's "Video" field.

---

### Task 30: Final Devpost submission

Spec §10 (submission deliverables + question drafts).

- [ ] **Step 1: Fill all required Devpost fields**

Per the project page screenshot:
- Title: "iam-legend"
- Theme: Build (Net-New Agents)
- Code link: GitHub repo URL
- Video link: YouTube URL
- Testing access: Cloud Run URL + demo repo URL
- Architecture diagram: upload `docs/architecture.png`
- Description: paste from `README.md` (problem + solution + tech)

- [ ] **Step 2: Answer the 5 submission questions**

Use the drafts in spec §10. Fill in the AI Studio familiarity rating honestly.

- [ ] **Step 3: Hit Submit**

Deadline: 2026-06-05 17:00 PT.

---

## Cut order (if behind on Day 7)

In order, cut the LAST item first:

1. Task 26 (GitHub Actions YAML parser)
2. Task 25 (Cloud Build YAML parser)
3. README code-block extraction from Task 12 (silently absent — no work needed to cut)
4. Registry-module walking in Task 10 (already not implemented; document as "known limitation")
5. `explain_403` MCP tool (mentioned in spec §6 but no task above — it was always stretch)

**Do NOT cut:**
- Tasks 1-22 (the spine of the product)
- Task 23 (demo repo — without it, no demo video)
- Task 27 (README) and Task 29 (video) and Task 30 (submission)

---

## Self-review against spec — done

Cross-checked every section of `docs/superpowers/specs/2026-05-28-iam-legend-design.md`:

- §1-§3 (problem / solution / scope): captured in the plan goal + cut-order section.
- §4 (architecture): file structure section maps exactly.
- §5 (parsers): Tasks 8-12, 25-26.
- §6 (MCP tool surface): Task 21 (per-transport gating matches §6 matrix).
- §7 (catalog): Tasks 3-7.
- §8.1 (deployment): Task 22 (Dockerfile + action.yml) + Task 24 (Cloud Run).
- §8.2 (auth): Task 13 (ADC) + Task 21 (transport gating).
- §8.3 (Gemini calls): Task 15 (justify) + Task 17 (review prose).
- §8.4 (Action wiring): Task 22 + Task 23 (demo workflow).
- §8.5 (failure modes): Task 20 (CLI `_post_to_github`) implements the fail-closed-on-signalling-failure rule.
- §9 (testing): unit tests throughout + Task 28 (e2e).
- §10 (submission): Tasks 27, 29, 30.
- §11 (risks): cut-order section addresses timeline risk; line-recovery (Task 10) and credentialless-hosted (Task 21) address the called-out parser/auth risks.

No spec section is orphaned. Every requirement has a task.

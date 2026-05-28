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
                    break
        return out


register(GcloudShellParser())

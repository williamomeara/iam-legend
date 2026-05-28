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

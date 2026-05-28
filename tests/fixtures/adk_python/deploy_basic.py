import vertexai
from vertexai import agent_engines

vertexai.init(project="my-proj", location="us-central1")

agent = agent_engines.create(
    display_name="my-agent",
    reasoning_engine="my_module.agent",
)

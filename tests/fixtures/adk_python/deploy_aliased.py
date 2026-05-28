# Tests import-alias resolution: 'from x.y import z as w' style.
from google.cloud import aiplatform as ap
from vertexai import agent_engines as ae

ap.init(project="p", location="us-central1")

endpoint = ap.Endpoint.create(display_name="e")
agent = ae.create(display_name="a")

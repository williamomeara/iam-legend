#!/usr/bin/env bash
# Deploy iam-legend MCP server to Cloud Run in HTTP read-only mode.
# Uses `gcloud run deploy --source .` so Cloud Build does the build remotely
# (no local docker daemon required). The repo's Dockerfile is honoured.
#
# Required env: PROJECT (or GOOGLE_CLOUD_PROJECT)
# Optional env: REGION (default us-central1)
set -euo pipefail

PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:?set PROJECT or GOOGLE_CLOUD_PROJECT}}"
REGION="${REGION:-us-central1}"
SERVICE="iam-legend"
SA_NAME="iam-legend-runtime"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

echo "==> Project: $PROJECT  Region: $REGION  Service: $SERVICE"

echo "==> Enabling required APIs"
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  aiplatform.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$PROJECT"

echo "==> Ensuring runtime SA exists: $SA"
gcloud iam service-accounts describe "$SA" --project="$PROJECT" 2>/dev/null \
  || gcloud iam service-accounts create "$SA_NAME" \
       --display-name="iam-legend Cloud Run runtime" \
       --project="$PROJECT"

echo "==> Binding roles/aiplatform.user to runtime SA"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" \
  --role=roles/aiplatform.user \
  --condition=None \
  --quiet >/dev/null

echo "==> Deploying via Cloud Build (uses repo Dockerfile)"
gcloud run deploy "$SERVICE" \
  --source=. \
  --region="$REGION" \
  --service-account="$SA" \
  --no-allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --timeout=300 \
  --set-env-vars="IAM_LEGEND_TRANSPORT=http,IAM_LEGEND_MODE=mcp,VERTEX_PROJECT=${PROJECT},VERTEX_LOCATION=${REGION}" \
  --project="$PROJECT"

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format='value(status.url)')"
echo
echo "==> Deployed: $URL"
echo "==> Test (with your identity):"
echo "    curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" $URL/mcp"

#!/usr/bin/env bash
set -euo pipefail

gcloud storage buckets create gs://my-bucket --location=us-central1
gcloud iam service-accounts create my-bot
gcloud projects add-iam-policy-binding my-proj \
  --member=serviceAccount:my-bot@my-proj.iam.gserviceaccount.com \
  --role=roles/run.admin
gcloud run deploy my-svc --image=us-docker.pkg.dev/my-proj/img:latest
gcloud services enable aiplatform.googleapis.com

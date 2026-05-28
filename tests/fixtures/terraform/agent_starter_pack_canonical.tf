# Canonical set of resource kinds used across the agent-starter-pack templates
# (adk, agentic_rag, adk_live, adk_a2a, adk_go, adk_java, adk_ts).
#
# This fixture is the regression-test surface for catalog coverage of the
# official Google ADK starters. If iam-legend's catalog ever drops one of
# these kinds, the catalog cross-check + repo-parse tests should fail.

# === Core infra ===
resource "google_project_service" "aiplatform" {
  service = "aiplatform.googleapis.com"
}

resource "google_storage_bucket" "logs" {
  name     = "asp-canonical-logs"
  location = "US"
}

resource "google_storage_bucket_iam_member" "logs_writer" {
  bucket = google_storage_bucket.logs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:example@example.iam.gserviceaccount.com"
}

# === Service accounts (both naming forms used across templates) ===
resource "google_service_account" "app_sa" {
  account_id = "asp-canonical-app"
}

resource "google_iam_service_account" "old_form" {
  account_id = "asp-canonical-old-form"
}

resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.app_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/foo/*"
}

resource "google_project_iam_member" "app_sa_aiplatform" {
  project = "asp-canonical"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

# === Workload Identity Federation ===
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "asp-canonical-github"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-demo"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# === Vertex Agent Engine (the wedge) ===
resource "google_vertex_ai_reasoning_engine" "main" {
  display_name = "asp-canonical-agent"
}

# === Discovery Engine (Gemini Enterprise search) ===
resource "google_discovery_engine_data_store" "docs" {
  data_store_id = "asp-canonical-docs"
}

resource "google_discovery_engine_search_engine" "docs" {
  engine_id     = "asp-canonical-docs-engine"
  data_store_ids = [google_discovery_engine_data_store.docs.data_store_id]
}

# === Pub/Sub for event flow ===
resource "google_pubsub_topic" "events" {
  name = "asp-canonical-events"
}

# === Logging telemetry sinks ===
resource "google_logging_project_sink" "telemetry" {
  name        = "asp-canonical-telemetry-sink"
  destination = "logging.googleapis.com/projects/asp-canonical/locations/global/buckets/asp-canonical"
}

resource "google_logging_project_bucket_config" "telemetry_bucket" {
  bucket_id = "asp-canonical-telemetry"
  location  = "global"
}

resource "google_logging_linked_dataset" "telemetry_bq" {
  link_id     = "asp-canonical-link"
  bucket      = google_logging_project_bucket_config.telemetry_bucket.id
  description = "BQ linked dataset for telemetry"
}

# === BigQuery for analytics ===
resource "google_bigquery_dataset" "analytics" {
  dataset_id = "asp_canonical_analytics"
  location   = "US"
}

resource "google_bigquery_table" "events" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "events"
}

resource "google_bigquery_connection" "vertex" {
  connection_id = "asp-canonical-vertex"
  location      = "us-central1"
}

# === Cloud Run service ===
resource "google_cloud_run_v2_service" "main" {
  name     = "asp-canonical-svc"
  location = "us-central1"
}

# === Service identity helper used by Vertex etc. ===
resource "google_project_service_identity" "vertex" {
  service = "aiplatform.googleapis.com"
}

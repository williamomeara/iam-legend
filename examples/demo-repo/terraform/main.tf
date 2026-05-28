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

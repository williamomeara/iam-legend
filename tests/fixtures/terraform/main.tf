resource "google_storage_bucket" "data" {
  name     = "my-data"
  location = "US"
}

resource "google_pubsub_topic" "events" {
  name = "events"
}

# A non-google resource that should be ignored
resource "null_resource" "noop" {}

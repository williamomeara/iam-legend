module "net" {
  source = "./modules/net"
}

resource "google_storage_bucket" "root_bucket" {
  name = "x"
}

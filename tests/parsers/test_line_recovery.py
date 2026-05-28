from pathlib import Path

from iam_legend.parsers.line_recovery import recover_lines


def test_recover_lines_finds_resource_declarations(tmp_path):
    tf = tmp_path / "main.tf"
    tf.write_text(
        'resource "google_storage_bucket" "a" {\n'
        '  name = "x"\n'
        '}\n'
        '\n'
        'resource "google_pubsub_topic" "b" {\n'
        '  name = "y"\n'
        '}\n'
    )
    lines = recover_lines(
        str(tf),
        [("google_storage_bucket", "a"), ("google_pubsub_topic", "b")],
    )
    assert lines[("google_storage_bucket", "a")] == 1
    assert lines[("google_pubsub_topic", "b")] == 5


def test_recover_lines_missing_returns_zero(tmp_path):
    tf = tmp_path / "main.tf"
    tf.write_text('resource "google_storage_bucket" "x" {}\n')
    lines = recover_lines(str(tf), [("google_pubsub_topic", "absent")])
    assert lines[("google_pubsub_topic", "absent")] == 0

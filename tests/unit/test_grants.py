from iam_legend.recommender.grants import generate_grant_commands


def test_generates_one_command_per_role():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin", "roles/pubsub.publisher"],
        project="my-proj",
        principal="serviceAccount:deployer@my-proj.iam.gserviceaccount.com",
    )
    assert len(cmds) == 2
    assert all("gcloud projects add-iam-policy-binding my-proj" in c for c in cmds)
    assert any("roles/storage.admin" in c for c in cmds)


def test_handles_user_principals():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin"],
        project="p",
        principal="user:alice@example.com",
    )
    assert "user:alice@example.com" in cmds[0]


def test_handles_bare_email():
    cmds = generate_grant_commands(
        roles=["roles/storage.admin"],
        project="p",
        principal="alice@example.com",
    )
    assert "user:alice@example.com" in cmds[0] or "alice@example.com" in cmds[0]

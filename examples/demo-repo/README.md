# iam-legend demo

This repo demonstrates iam-legend running as a PR review bot.

Try it:
1. Fork this repo
2. Configure secrets: `WIF_PROVIDER`, `DEPLOYER_SA`, `PROJECT_ID`
3. Open a PR that changes `terraform/main.tf` or `deploy.py`
4. Watch iam-legend post a review with the IAM gap

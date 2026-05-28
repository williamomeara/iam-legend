"""iam-legend CLI. Three subcommands: lookup, review, refresh-catalog."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from iam_legend import __version__
from iam_legend.analyze import analyze
from iam_legend.catalog.loader import load_catalog


@click.group()
@click.version_option(__version__)
def cli() -> None:
    """iam-legend — GCP IAM toolbelt."""


@cli.command()
@click.argument("target")
def lookup(target: str) -> None:
    """Look up IAM perms for a Terraform resource, a role, or a permission name."""
    c = load_catalog()
    if target.startswith("roles/"):
        role = c.lookup_role(target)
        if role is None:
            click.echo(f"unknown role: {target}", err=True)
            sys.exit(1)
        click.echo(f"{target}: {role.get('title')}")
        for p in role["permissions"]:
            click.echo(f"  {p}")
        return
    if "." in target and not target.startswith("google_"):
        roles = c.roles_with(target)
        click.echo(f"Roles containing {target}:")
        for r in roles:
            click.echo(f"  {r}")
        return
    entry = c.resources.get(target)
    if entry is None:
        click.echo(f"unknown resource kind: {target}", err=True)
        sys.exit(1)
    for op, perms in entry.items():
        if op == "required_apis":
            continue
        click.echo(f"{target}.{op}: {perms}")


@cli.command()
@click.option("--plan", "plan_path", type=click.Path(exists=True), help="terraform plan -json output")
@click.option("--repo", "repo_path", type=click.Path(exists=True), help="repo root for static scan")
@click.option("--project", help="GCP project for live IAM diff")
@click.option("--format", "out_fmt", type=click.Choice(["pretty", "json"]), default="pretty")
@click.option("--post-pr", is_flag=True, help="(action mode) post review to GitHub")
@click.option("--pr-number", type=int, help="PR number when --post-pr is set")
@click.option("--repo-full-name", help="owner/repo when --post-pr is set")
def review(
    plan_path: str | None, repo_path: str | None, project: str | None,
    out_fmt: str, post_pr: bool, pr_number: int | None, repo_full_name: str | None,
) -> None:
    """Run an IAM review on a terraform plan or a repo."""
    if not plan_path and not repo_path:
        click.echo("provide --plan or --repo", err=True)
        sys.exit(2)

    if plan_path:
        report = analyze(plan_path, kind="plan_json", project=project)
    else:
        report = analyze(repo_path, kind="repo", project=project)

    if out_fmt == "json":
        click.echo(json.dumps(asdict(report), indent=2, default=list))
        return

    _render_pretty(report)

    if post_pr:
        _post_to_github(report, pr_number, repo_full_name)


def _render_pretty(report) -> None:
    con = Console()
    missing = report.live_state.missing if report.live_state else report.required_permissions
    verdict = "✅ Approved" if not missing else "🚫 Changes requested"
    con.print(Panel.fit(f"[bold]{verdict}[/bold]"))

    t = Table(title="Required permissions")
    t.add_column("Permission")
    t.add_column("Status")
    granted = set(report.live_state.granted) if report.live_state else set()
    for p in report.required_permissions:
        status = (
            "[green]granted[/green]" if p in granted
            else ("[red]missing[/red]" if report.live_state else "[yellow]not checked[/yellow]")
        )
        t.add_row(p, status)
    con.print(t)

    if report.recommendation.roles:
        con.print("\n[bold]Recommended roles:[/bold]")
        for r in report.recommendation.roles:
            con.print(f"  • {r}")
        if report.recommendation.reasoning:
            con.print(f"\n[italic]{report.recommendation.reasoning}[/italic]")
        con.print("\n[bold]Grant commands:[/bold]")
        for c in report.grant_commands:
            con.print(c)

    if report.warnings:
        con.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in report.warnings:
            con.print(f"  ! {w}")


def _post_to_github(report, pr_number: int | None, repo_full_name: str | None) -> None:
    import os
    from github import Github
    from iam_legend.reviewer.format import format_review
    from iam_legend.reviewer.github import post_review
    from iam_legend.gcp.auth import who_am_i

    if not pr_number or not repo_full_name:
        click.echo("missing --pr-number or --repo-full-name", err=True)
        sys.exit(2)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        click.echo("GITHUB_TOKEN env var not set", err=True)
        sys.exit(1)

    try:
        deployer = who_am_i()
    except Exception:
        deployer = "unknown-principal"

    payload = format_review(report, deployer=deployer)
    try:
        gh = Github(token)
        repo = gh.get_repo(repo_full_name)
        post_review(payload, repo, pr_number)
    except Exception as e:
        print(f"::error title=iam-legend::could not post PR review: {e}")
        print(payload.body)
        sys.exit(1)

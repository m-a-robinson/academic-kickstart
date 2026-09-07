#!/usr/bin/env python3
"""Open one pull request per new publication found by orcid_sync.py.

Run this immediately after orcid_sync.py, in the same checkout, on the
branch that should be the PR base (e.g. master). It looks at git's
working-tree status for newly-added content/publication/*/ directories,
and for each one:

  1. creates a dedicated branch (orcid-sync/<slug>) from the current HEAD,
  2. commits just that publication's files onto it,
  3. pushes the branch,
  4. opens a pull request for it against the base branch (or, if a PR for
     that branch already exists, just leaves the push to update it).

This means each new paper can be independently merged (accept it) or
closed without merging (reject it - see orcid-sync-reject.yml, which
records that decision so it isn't suggested again), rather than bundling
every new paper from a run into a single all-or-nothing pull request.

Requires GITHUB_TOKEN in the environment and a git working tree with a
remote 'origin' that has push access (as is the case inside the
orcid-sync.yml GitHub Actions workflow, which sets both up already).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import requests
import yaml

PUBLICATION_DIR = Path(__file__).resolve().parent.parent / "content" / "publication"
API_ROOT = "https://api.github.com"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def newly_added_publication_slugs() -> list[str]:
    """Slugs of content/publication/<slug>/ directories git sees as untracked."""
    result = run("git", "status", "--porcelain", str(PUBLICATION_DIR))
    slugs: list[str] = []
    for line in result.stdout.splitlines():
        if not line.startswith("??"):
            continue  # only newly-added (untracked) directories are new publications
        path = line[3:].strip().strip('"')
        rel = Path(path).relative_to("content/publication")
        slug = rel.parts[0]
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def load_title(slug: str) -> str:
    text = (PUBLICATION_DIR / slug / "index.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    front_matter = (yaml.safe_load(match.group(1)) if match else {}) or {}
    return front_matter.get("title", slug)


def find_existing_pr(session: requests.Session, repo: str, owner: str, branch: str) -> int | None:
    resp = session.get(
        f"{API_ROOT}/repos/{repo}/pulls",
        params={"head": f"{owner}:{branch}", "state": "all"},
        timeout=30,
    )
    resp.raise_for_status()
    prs = resp.json()
    return prs[0]["number"] if prs else None


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]  # "owner/name"
    owner = repo.split("/", 1)[0]
    base_branch = os.environ.get("GITHUB_REF_NAME", "master")
    token = os.environ["GITHUB_TOKEN"]

    slugs = newly_added_publication_slugs()
    if not slugs:
        print("No newly-added publications to open PRs for.")
        return 0

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })

    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    base_sha = run("git", "rev-parse", "HEAD").stdout.strip()

    opened, updated, failed = 0, 0, 0
    for slug in slugs:
        title = load_title(slug)
        branch = f"orcid-sync/{slug}"
        print(f"--- {slug}: {title!r} -> {branch}")

        run("git", "checkout", "-B", branch, base_sha)
        run("git", "add", f"content/publication/{slug}")
        commit = run("git", "commit", "-m", f"Add publication: {title}", check=False)
        if commit.returncode != 0:
            print(f"  ! nothing to commit for {slug}, skipping: {commit.stdout}{commit.stderr}", file=sys.stderr)
            run("git", "checkout", base_branch)
            failed += 1
            continue
        push = run("git", "push", "-f", "origin", branch, check=False)
        if push.returncode != 0:
            print(f"  ! could not push {branch}: {push.stderr}", file=sys.stderr)
            run("git", "checkout", base_branch)
            failed += 1
            continue

        try:
            existing = find_existing_pr(session, repo, owner, branch)
        except requests.RequestException as exc:
            print(f"  ! could not check for an existing PR: {exc!r}", file=sys.stderr)
            existing = None

        if existing:
            print(f"  Updated existing PR #{existing}.")
            updated += 1
        else:
            create_resp = session.post(
                f"{API_ROOT}/repos/{repo}/pulls",
                json={
                    "title": f"New publication: {title}",
                    "head": branch,
                    "base": base_branch,
                    "body": (
                        f"Proposed by the ORCID sync (`{slug}`).\n\n"
                        "Review the authors, venue, DOI, tags and project, then:\n"
                        "- set `draft: false` and merge to publish it, or\n"
                        "- close this PR without merging to reject it - that's "
                        "recorded automatically so it won't be suggested again."
                    ),
                },
                timeout=30,
            )
            if create_resp.status_code >= 300:
                print(f"  ! could not open PR for {slug}: {create_resp.status_code} {create_resp.text}", file=sys.stderr)
                failed += 1
            else:
                print(f"  Opened {create_resp.json()['html_url']}")
                opened += 1

        run("git", "checkout", base_branch)

    print(f"\n{opened} PR(s) opened, {updated} updated, {failed} failed, out of {len(slugs)} new publication(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

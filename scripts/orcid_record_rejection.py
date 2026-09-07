#!/usr/bin/env python3
"""Record publications declined via a closed (not merged) ORCID-sync PR.

Reads the closed pull request's newly-added content/publication/*/index.md
files via the GitHub API and appends their title/DOI to
scripts/orcid_ignore.yml, so orcid_sync.py stops suggesting them again.

Invoked by .github/workflows/orcid-sync-reject.yml whenever a
"New publications from ORCID" pull request is closed without merging -
i.e. closing such a PR is how you reject a suggested publication.

Usage:
    python scripts/orcid_record_rejection.py --repo owner/repo \
        --pr-number 123 --head-sha abc123...
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

import requests
import yaml

IGNORE_FILE = Path(__file__).resolve().parent / "orcid_ignore.yml"
API_ROOT = "https://api.github.com"


def normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def normalise_doi(doi: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()

    token = os.environ["GITHUB_TOKEN"]
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })

    files_resp = session.get(
        f"{API_ROOT}/repos/{args.repo}/pulls/{args.pr_number}/files",
        params={"per_page": 100},
        timeout=30,
    )
    files_resp.raise_for_status()
    added_index_files = [
        f["filename"] for f in files_resp.json()
        if f["status"] == "added"
        and f["filename"].startswith("content/publication/")
        and f["filename"].endswith("/index.md")
    ]

    if not added_index_files:
        print("No newly-added publication files found on this PR - nothing to record.")
        return 0

    ignore_data = {"ignored": []}
    if IGNORE_FILE.exists():
        ignore_data = yaml.safe_load(IGNORE_FILE.read_text(encoding="utf-8")) or {"ignored": []}
    ignore_data.setdefault("ignored", [])

    existing_dois = {normalise_doi(e["doi"]) for e in ignore_data["ignored"] if e.get("doi")}
    existing_titles = {normalise_title(e["title"]) for e in ignore_data["ignored"] if e.get("title")}

    added_count = 0
    for path in added_index_files:
        content_resp = session.get(
            f"{API_ROOT}/repos/{args.repo}/contents/{path}",
            params={"ref": args.head_sha},
            timeout=30,
        )
        if content_resp.status_code != 200:
            print(f"  ! could not fetch {path} at {args.head_sha}: {content_resp.status_code}", file=sys.stderr)
            continue
        raw = base64.b64decode(content_resp.json()["content"]).decode("utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
        if not match:
            continue
        front_matter = yaml.safe_load(match.group(1)) or {}
        title = front_matter.get("title")
        doi = front_matter.get("doi")

        norm_doi = normalise_doi(doi) if doi else None
        norm_title = normalise_title(title) if title else None
        if not norm_doi and not norm_title:
            continue
        if (norm_doi and norm_doi in existing_dois) or (norm_title and norm_title in existing_titles):
            continue  # already recorded

        entry = {}
        if title:
            entry["title"] = title
        if doi:
            entry["doi"] = doi
        ignore_data["ignored"].append(entry)
        if norm_doi:
            existing_dois.add(norm_doi)
        if norm_title:
            existing_titles.add(norm_title)
        added_count += 1
        print(f"  + recorded rejection: {title or doi}")

    if added_count:
        IGNORE_FILE.write_text(
            yaml.dump(ignore_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"Recorded {added_count} declined publication(s) in {IGNORE_FILE.name}.")
    else:
        print("Nothing new to record.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

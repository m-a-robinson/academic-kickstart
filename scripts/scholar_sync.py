#!/usr/bin/env python3
"""Sync new publications from a Google Scholar profile into content/publication/.

Fetches the publication list for a Google Scholar author profile and creates a
new Hugo content file (content/publication/<slug>/index.md) for any paper that
isn't already present in the repository (matched by normalised title).

New entries are written with `draft: true` and a "Needs review" tag so nothing
goes live automatically - they're intended to be checked (DOI, authors,
venue, tags, project) and then flipped to `draft: false` before merging.

Usage:
    python scripts/scholar_sync.py [--scholar-id ID] [--dry-run]

Google Scholar has no official API and `scholarly` scrapes the public profile
page, which Google occasionally rate-limits or CAPTCHA-blocks - especially
from shared CI IP ranges. A failure here is usually transient; re-run later
or trigger the workflow manually.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_SCHOLAR_ID = "sqCJJ7wAAAAJ"  # Mark A Robinson - Google Scholar profile
PUBLICATION_DIR = Path(__file__).resolve().parent.parent / "content" / "publication"


def normalise_title(title: str) -> str:
    """Lowercase and strip punctuation/whitespace so titles can be compared."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", text)


def load_existing_titles() -> set[str]:
    """Return the set of normalised titles already present in content/publication/."""
    titles = set()
    for index_file in PUBLICATION_DIR.glob("*/index.md"):
        text = index_file.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            continue
        try:
            front_matter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        title = front_matter.get("title")
        if title:
            titles.add(normalise_title(title))
    return titles


def existing_slugs() -> set[str]:
    return {p.name for p in PUBLICATION_DIR.glob("*") if p.is_dir()}


def unique_slug(base_slug: str, taken: set[str]) -> str:
    slug = base_slug
    n = 2
    while slug in taken:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def keyword_from_title(title: str) -> str:
    stopwords = {
        "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with",
        "using", "is", "are", "vs", "vs.", "from", "during", "based", "via",
    }
    words = re.findall(r"[a-zA-Z]+", title.lower())
    for word in words:
        if word not in stopwords and len(word) > 2:
            return word
    return words[0] if words else "paper"


def build_front_matter(pub: dict) -> tuple[str, dict]:
    bib = pub.get("bib", {})
    title = bib.get("title", "Untitled").strip()
    authors_raw = bib.get("author", "")
    authors = [a.strip() for a in authors_raw.split(" and ") if a.strip()] or ["Unknown"]
    year = bib.get("pub_year")
    date = f"{year}-01-01" if year else None

    first_author_lastname = slugify(authors[0].split()[-1]) if authors[0] else "unknown"
    slug_base = f"{first_author_lastname}-{keyword_from_title(title)}-{year or 'nd'}"

    front_matter = {
        "title": title,
        "authors": authors,
        "publication_types": ["2"],  # 2 = Journal article; adjust after review.
        "abstract": bib.get("abstract", ""),
        "featured": False,
        "publication": bib.get("venue", ""),
        "url_pdf": pub.get("eprint_url") or bib.get("url", "") or "",
        "doi": "",
        "tags": ["Needs review"],
        "projects": [],
        "draft": True,
    }
    if date:
        front_matter = {"date": date, **front_matter}
    return slug_base, front_matter


def write_publication(slug: str, front_matter: dict, dry_run: bool) -> Path:
    target_dir = PUBLICATION_DIR / slug
    content = "---\n" + yaml.dump(front_matter, sort_keys=False, allow_unicode=True) + "---\n"
    if dry_run:
        print(f"--- would write {target_dir / 'index.md'} ---")
        print(content)
        return target_dir / "index.md"
    target_dir.mkdir(parents=True, exist_ok=True)
    index_file = target_dir / "index.md"
    index_file.write_text(content, encoding="utf-8")
    return index_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scholar-id", default=DEFAULT_SCHOLAR_ID, help="Google Scholar author ID")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without writing files")
    args = parser.parse_args()

    from scholarly import scholarly  # imported lazily so --help doesn't need network deps

    print(f"Fetching Google Scholar profile {args.scholar_id} ...")
    author = scholarly.search_author_id(args.scholar_id)
    author = scholarly.fill(author, sections=["publications"])
    scholar_pubs = author.get("publications", [])
    print(f"Found {len(scholar_pubs)} publications on Scholar profile.")

    known_titles = load_existing_titles()
    taken_slugs = existing_slugs()

    added = []
    for pub in scholar_pubs:
        bib = pub.get("bib", {})
        title = bib.get("title")
        if not title:
            continue
        if normalise_title(title) in known_titles:
            continue

        try:
            pub = scholarly.fill(pub)
        except Exception as exc:  # scholarly can fail per-item (rate limit, missing page, etc.)
            print(f"  ! could not fetch full details for '{title}': {exc}", file=sys.stderr)

        slug_base, front_matter = build_front_matter(pub)
        slug = unique_slug(slug_base, taken_slugs)
        taken_slugs.add(slug)

        index_file = write_publication(slug, front_matter, args.dry_run)
        added.append((slug, front_matter["title"]))
        print(f"  + {index_file}")

    if not added:
        print("No new publications found - repository is up to date with Scholar.")
        return 0

    print(f"\nAdded {len(added)} new publication(s), all marked draft: true for review:")
    for slug, title in added:
        print(f"  - {slug}: {title}")

    summary_path = Path(__file__).resolve().parent / "scholar_sync_summary.md"
    if not args.dry_run:
        lines = [
            "New publications were found on Google Scholar and added as drafts:",
            "",
        ]
        lines += [f"- `{slug}`: {title}" for slug, title in added]
        lines += [
            "",
            "Each entry is created with `draft: true` and tagged `Needs review`. "
            "Please check the authors, venue, DOI, tags and project before setting "
            "`draft: false`.",
        ]
        summary_path.write_text("\n".join(lines), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

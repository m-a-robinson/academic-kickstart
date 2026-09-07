#!/usr/bin/env python3
"""Sync new publications from an ORCID profile into content/publication/.

Fetches the works list for an ORCID iD via ORCID's public API, enriches each
new entry via Crossref (looked up by DOI) for authors/journal/abstract, and
creates a new Hugo content file (content/publication/<slug>/index.md) for
each paper that isn't already present in the repository.

Both ORCID's public API and Crossref's API are official, key-free REST APIs
- unlike scraping Google Scholar, there's no CAPTCHA/blocking risk here.

New entries are written with `draft: true` and a "Needs review" tag so
nothing goes live automatically - they're intended to be checked (venue,
tags, project, publication type) and then flipped to `draft: false` before
merging.

Usage:
    python scripts/orcid_sync.py [--orcid-id ID] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests
import yaml

DEFAULT_ORCID_ID = "0000-0002-5627-492X"  # Mark A Robinson - ORCID iD
PUBLICATION_DIR = Path(__file__).resolve().parent.parent / "content" / "publication"

ORCID_API = "https://pub.orcid.org/v3.0"
CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "academic-kickstart-orcid-sync/1.0 (+https://github.com/m-a-robinson/academic-kickstart)"


def normalise_title(title: str) -> str:
    """Lowercase and strip punctuation/whitespace so titles can be compared."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def normalise_doi(doi: str) -> str:
    """Strip any URL prefix so DOIs compare equal regardless of formatting."""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", text)


def load_existing_publications() -> tuple[set[str], set[str]]:
    """Return (normalised titles, normalised DOIs) already in content/publication/."""
    titles = set()
    dois = set()
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
        doi = front_matter.get("doi")
        if doi:
            dois.add(normalise_doi(doi))
    return titles, dois


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


def fetch_orcid_works(orcid_id: str, session: requests.Session) -> list[dict]:
    """Return one summary dict per distinct work group on the ORCID record."""
    resp = session.get(f"{ORCID_API}/{orcid_id}/works", headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    works = []
    for group in data.get("group", []):
        summaries = group.get("work-summary", [])
        if not summaries:
            continue
        summary = summaries[0]  # ORCID's preferred source for this work group
        title = ((summary.get("title") or {}).get("title") or {}).get("value")
        if not title:
            continue

        doi = None
        for ext_id in group.get("external-ids", {}).get("external-id", []):
            if ext_id.get("external-id-type") == "doi":
                doi = ext_id.get("external-id-value")
                break

        pub_date = summary.get("publication-date") or {}
        year = (pub_date.get("year") or {}).get("value")

        works.append({
            "title": title,
            "doi": doi,
            "year": year,
            "journal": (summary.get("journal-title") or {}).get("value"),
            "url": (summary.get("url") or {}).get("value"),
        })
    return works


def fetch_crossref_metadata(doi: str, session: requests.Session) -> dict:
    """Best-effort lookup of authors/journal/abstract/date for a DOI via Crossref."""
    resp = session.get(f"{CROSSREF_API}/{doi}", headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    message = resp.json().get("message", {})

    authors = []
    for author in message.get("author", []) or []:
        name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
        if name:
            authors.append(name)

    abstract = message.get("abstract", "")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()  # strip JATS/XML tags

    published = message.get("published") or message.get("published-print") or message.get("published-online") or {}
    date_parts = (published.get("date-parts") or [[None]])[0]
    year = date_parts[0] if len(date_parts) > 0 else None
    month = date_parts[1] if len(date_parts) > 1 else 1
    day = date_parts[2] if len(date_parts) > 2 else 1

    return {
        "authors": authors,
        "journal": (message.get("container-title") or [None])[0],
        "abstract": abstract,
        "url": message.get("URL", ""),
        "year": year,
        "month": month or 1,
        "day": day or 1,
    }


def build_front_matter(work: dict, crossref: dict | None) -> tuple[str, dict]:
    title = work["title"].strip()
    authors = (crossref or {}).get("authors") or ["Unknown"]
    journal = (crossref or {}).get("journal") or work.get("journal") or ""
    abstract = (crossref or {}).get("abstract") or ""
    doi = work.get("doi") or ""
    url = (crossref or {}).get("url") or work.get("url") or ""

    year = (crossref or {}).get("year") or work.get("year")
    month = (crossref or {}).get("month") or 1
    day = (crossref or {}).get("day") or 1
    date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}" if year else None

    first_author_lastname = slugify(authors[0].split()[-1]) if authors[0] != "Unknown" else "unknown"
    slug_base = f"{first_author_lastname}-{keyword_from_title(title)}-{year or 'nd'}"

    front_matter = {"title": title}
    if date:
        front_matter["date"] = date
    front_matter.update({
        "authors": authors,
        "publication_types": ["2"],  # 2 = Journal article; adjust after review.
        "abstract": abstract,
        "featured": False,
        "publication": journal,
        "url_pdf": url,
        "doi": f"https://doi.org/{doi}" if doi else "",
        "tags": ["Needs review"],
        "projects": [],
        "draft": True,
    })
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
    parser.add_argument("--orcid-id", default=DEFAULT_ORCID_ID, help="ORCID iD, e.g. 0000-0002-5627-492X")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without writing files")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    print(f"Fetching ORCID works for {args.orcid_id} ...")
    try:
        works = fetch_orcid_works(args.orcid_id, session)
    except requests.RequestException as exc:
        print(f"Failed to fetch ORCID profile: {exc!r}", file=sys.stderr)
        return 1
    print(f"Found {len(works)} works on ORCID record.")

    known_titles, known_dois = load_existing_publications()
    taken_slugs = existing_slugs()

    added = []
    for work in works:
        title = work["title"]
        doi = normalise_doi(work["doi"]) if work.get("doi") else None

        if doi and doi in known_dois:
            continue
        if normalise_title(title) in known_titles:
            continue

        crossref = None
        if work.get("doi"):
            try:
                crossref = fetch_crossref_metadata(work["doi"], session)
            except requests.RequestException as exc:
                print(f"  ! could not fetch Crossref details for '{title}': {exc}", file=sys.stderr)
            time.sleep(1)  # be polite to Crossref's shared API pool

        slug_base, front_matter = build_front_matter(work, crossref)
        slug = unique_slug(slug_base, taken_slugs)
        taken_slugs.add(slug)

        index_file = write_publication(slug, front_matter, args.dry_run)
        added.append((slug, front_matter["title"]))
        print(f"  + {index_file}")

    if not added:
        print("No new publications found - repository is up to date with ORCID.")
        return 0

    print(f"\nAdded {len(added)} new publication(s), all marked draft: true for review:")
    for slug, title in added:
        print(f"  - {slug}: {title}")

    summary_path = Path(__file__).resolve().parent / "orcid_sync_summary.md"
    if not args.dry_run:
        lines = [
            "New publications were found on ORCID and added as drafts:",
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

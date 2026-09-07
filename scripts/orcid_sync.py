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

By default only works published in the last few years are considered (see
DEFAULT_YEARS_BACK) - older ORCID entries are far more likely to already be
on the site under a slightly different title, and are lower-value to add
retroactively. Use --all-years to see the full ORCID history instead.

Conference abstracts/posters are excluded by default (see
DEFAULT_EXCLUDED_TYPES) - these are usually a secondary listing of a paper
presented properly elsewhere (e.g. as a journal-article), so including them
mostly adds review-queue noise. Use --include-all-types to see everything.

Each new entry gets a best-guess `tags`/`projects` based on keyword
matching against the site's existing taxonomy (see TAXONOMY) - a starting
point for the reviewer, not a substitute for review.

Usage:
    python scripts/orcid_sync.py [--orcid-id ID] [--dry-run]
                                  [--min-year YEAR | --all-years]
                                  [--exclude-types T1,T2 | --include-all-types]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import requests
import yaml

DEFAULT_ORCID_ID = "0000-0002-5627-492X"  # Mark A Robinson - ORCID iD
PUBLICATION_DIR = Path(__file__).resolve().parent.parent / "content" / "publication"
IGNORE_FILE = Path(__file__).resolve().parent / "orcid_ignore.yml"

ORCID_API = "https://pub.orcid.org/v3.0"
CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "academic-kickstart-orcid-sync/1.0 (+https://github.com/m-a-robinson/academic-kickstart)"

# Many ORCID work records (especially older/imported ones) have no DOI
# attached, so title comparison is often the only way to spot a duplicate.
# Titles rarely match byte-for-byte between ORCID/Crossref and the
# hand-written repo copy (quote styles, ampersands, subtitles, stray
# whitespace), so use fuzzy similarity rather than exact string equality.
TITLE_SIMILARITY_THRESHOLD = 0.90

# ORCID work types (https://info.orcid.org/documentation/) that are excluded
# by default: secondary listings of a paper that's presented properly
# elsewhere (as a journal-article, say), which mostly just add noise/
# duplicates to the review queue.
DEFAULT_EXCLUDED_TYPES = {"conference-abstract", "conference-poster"}

# Heuristic keyword -> (project, tags) map used to pre-fill new entries,
# based on the vocabulary already used across content/publication/. This is
# a starting guess for the reviewer, not a substitute for review - every
# entry is still marked draft/"Needs review" regardless of what's predicted
# here. Matching is case-insensitive against "title. abstract", each
# keyword must match on a word boundary.
TAXONOMY: list[tuple[list[str], str, list[str]]] = [
    (["markerless", "theia3d", "pose estimation", "motion capture",
      "camera configuration", "leap motion"],
     "markerless", ["Markerless"]),
    (["statistical parametric mapping", "spm1d", "spm", "vector field",
      "waveform", "power analysis", "sample size"],
     "spm1d", ["SPM"]),
    (["training load", "microcycle", "match load", "accelerometry",
      "ground reaction force", "wearable sensor", "player load",
      "training and match load"],
     "training_load", ["Training Load"]),
    (["anterior cruciate ligament", "acl", "sidestepping", "side-cutting",
      "side cutting", "knee abduction", "knee flexion",
      "change of direction"],
     "knee", ["ACL", "Knee"]),
    (["alkaptonuria", "systemic sclerosis", "concussion", "mtbi",
      "rehabilitation", "clinical population"],
     "clinical", ["Clinical"]),
    (["reliability", "validity", "biomechanical model", "kinematic model",
      "inverse kinematics", "gait model"],
     "methods", ["Methods"]),
]


def predict_project_and_tags(title: str, abstract: str) -> tuple[list[str], list[str]]:
    """Heuristically guess a project and tags from title/abstract keywords.

    Picks the single best-matching project (most keyword hits), but
    collects tags from every taxonomy group that matched at all, since a
    paper can reasonably carry tags from more than one theme. Always keeps
    "Needs review" so the guess still gets checked before publishing.
    """
    text = f"{title} {abstract}".lower()
    scores: dict[str, int] = {}
    tags: list[str] = []
    for keywords, project, project_tags in TAXONOMY:
        hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text))
        if hits:
            scores[project] = scores.get(project, 0) + hits
            for tag in project_tags:
                if tag not in tags:
                    tags.append(tag)
    tags.append("Needs review")
    best_project = max(scores, key=scores.get) if scores else None
    return ([best_project] if best_project else []), tags


def normalise_title(title: str) -> str:
    """Lowercase and strip punctuation/whitespace so titles can be compared."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def normalise_doi(doi: str) -> str:
    """Strip any URL prefix so DOIs compare equal regardless of formatting."""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", text)


def load_existing_publications() -> tuple[list[str], set[str]]:
    """Return (normalised titles, normalised DOIs) already in content/publication/."""
    titles = []
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
            titles.append(normalise_title(title))
        doi = front_matter.get("doi")
        if doi:
            dois.add(normalise_doi(doi))
    return titles, dois


def load_ignore_list() -> tuple[list[str], set[str]]:
    """Return (normalised titles, normalised DOIs) explicitly declined before.

    Populated either by hand (add a `- title: "..."` / `- doi: "..."` entry
    to scripts/orcid_ignore.yml) or automatically when a "New publications
    from ORCID" pull request is closed without merging - see
    .github/workflows/orcid-sync-reject.yml.
    """
    if not IGNORE_FILE.exists():
        return [], set()
    data = yaml.safe_load(IGNORE_FILE.read_text(encoding="utf-8")) or {}
    entries = data.get("ignored") or []
    titles = [normalise_title(e["title"]) for e in entries if e.get("title")]
    dois = {normalise_doi(e["doi"]) for e in entries if e.get("doi")}
    return titles, dois


def titles_match(a: str, b: str, threshold: float = TITLE_SIMILARITY_THRESHOLD) -> bool:
    """True if two normalised titles are close enough to be the same paper.

    Two checks, either of which is sufficient:
      - overall similarity ratio (catches punctuation/wording differences)
      - containment: the shorter title is almost entirely a contiguous
        substring of the longer one (catches ORCID/Crossref dropping a
        subtitle, e.g. "...gait" vs "...gait suitable for use in real-time
        visual feedback applications" - a whole-string ratio would score
        that low despite it being the same paper).
    """
    # autojunk=False: SequenceMatcher's default autojunk heuristic treats a
    # character as "popular" (and excludes it from matches) once it makes up
    # too much of a long sequence - which silently breaks contiguous-match
    # detection on titles over ~200 characters (common characters like
    # spaces get marked junk). Titles are short enough that disabling it
    # costs nothing.
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    if matcher.ratio() >= threshold:
        return True
    shorter_len = min(len(a), len(b))
    if not shorter_len:
        return False
    longest_match = matcher.find_longest_match(0, len(a), 0, len(b))
    return (longest_match.size / shorter_len) >= threshold


def is_similar_title(title: str, others: list[str], threshold: float = TITLE_SIMILARITY_THRESHOLD) -> bool:
    """Fuzzy-match a normalised title against a list of other normalised titles."""
    return any(titles_match(title, other, threshold) for other in others)


def dedupe_works(works: list[dict]) -> list[dict]:
    """Collapse works that are the same paper appearing under multiple ORCID
    source records (common: near-identical title, or the same DOI, listed
    twice with minor formatting differences)."""
    kept: list[dict] = []
    kept_titles: list[str] = []
    kept_dois: set[str] = set()
    for work in works:
        doi = normalise_doi(work["doi"]) if work.get("doi") else None
        norm_title = normalise_title(work["title"])
        if doi and doi in kept_dois:
            continue
        if is_similar_title(norm_title, kept_titles):
            continue
        kept.append(work)
        kept_titles.append(norm_title)
        if doi:
            kept_dois.add(doi)
    return kept


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
            "type": summary.get("type"),  # e.g. "journal-article", "conference-abstract"
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

    projects, tags = predict_project_and_tags(title, abstract)

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
        "tags": tags,
        "projects": projects,
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


DEFAULT_YEARS_BACK = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orcid-id", default=DEFAULT_ORCID_ID, help="ORCID iD, e.g. 0000-0002-5627-492X")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without writing files")
    parser.add_argument(
        "--min-year", type=int, default=None,
        help=f"Only propose works published in this year or later (default: current year - {DEFAULT_YEARS_BACK})",
    )
    parser.add_argument(
        "--all-years", action="store_true",
        help="Disable the year cutoff entirely and consider the full ORCID history",
    )
    parser.add_argument(
        "--exclude-types", default=",".join(sorted(DEFAULT_EXCLUDED_TYPES)),
        help="Comma-separated ORCID work types to skip (default: %(default)s)",
    )
    parser.add_argument(
        "--include-all-types", action="store_true",
        help="Don't filter by work type at all (overrides --exclude-types)",
    )
    args = parser.parse_args()

    if args.all_years:
        min_year = None
    elif args.min_year is not None:
        min_year = args.min_year
    else:
        min_year = date.today().year - DEFAULT_YEARS_BACK

    excluded_types = set()
    if not args.include_all_types:
        excluded_types = {t.strip().lower() for t in args.exclude_types.split(",") if t.strip()}

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    print(f"Fetching ORCID works for {args.orcid_id} ...")
    try:
        works = fetch_orcid_works(args.orcid_id, session)
    except requests.RequestException as exc:
        print(f"Failed to fetch ORCID profile: {exc!r}", file=sys.stderr)
        return 1
    print(f"Found {len(works)} works on ORCID record.")

    if excluded_types:
        before = len(works)
        works = [w for w in works if (w.get("type") or "").lower() not in excluded_types]
        print(f"Excluding types {sorted(excluded_types)}: {before} -> {len(works)} works.")

    if min_year is not None:
        before = len(works)
        # A work with no resolvable year can't be confirmed recent, so it's
        # excluded along with everything older than the cutoff.
        works = [w for w in works if w.get("year") and int(w["year"]) >= min_year]
        print(f"Restricting to {min_year} onwards: {before} -> {len(works)} works.")

    works = dedupe_works(works)
    print(f"After removing same-paper duplicates within the ORCID record: {len(works)} works.")

    known_titles, known_dois = load_existing_publications()
    ignored_titles, ignored_dois = load_ignore_list()
    all_known_titles = known_titles + ignored_titles
    all_known_dois = known_dois | ignored_dois
    taken_slugs = existing_slugs()

    added = []
    skipped_similar = []
    for work in works:
        title = work["title"]
        doi = normalise_doi(work["doi"]) if work.get("doi") else None

        if doi and doi in all_known_dois:
            continue
        if is_similar_title(normalise_title(title), all_known_titles):
            skipped_similar.append(title)
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

    if skipped_similar:
        print(f"\nSkipped {len(skipped_similar)} work(s) as likely-duplicates of existing/ignored entries:")
        for title in skipped_similar:
            print(f"  - {title}")

    if not added:
        print("\nNo new publications found - repository is up to date with ORCID.")
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

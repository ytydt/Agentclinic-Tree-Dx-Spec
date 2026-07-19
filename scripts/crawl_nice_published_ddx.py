#!/usr/bin/env python3
"""Crawl NICE published guidance list and seed DDx-related chapters (no API-Key).

Source list: https://www.nice.org.uk/guidance/published?sp=on&ps=9999
Paginated with ``pa=1,2,...``.

Pipeline:
  1. Parse published table → guidance ref + title + URL
  2. Keep clinical guideline types (NG/CG/DG/SC) OR title DDx keywords
  3. Fetch each guidance landing page → **stacked-nav sidebar** chapter TOC
  4. By default keep Overview / Introduction / Using-this-guideline and
     DDx-related sidebar chapters; ``--all-sidebar`` keeps every sidebar
     chapter except research / committee / update / terms (etc.).
  5. Write ``data/cpg/open_cpg_nice_ddx_seed.json`` (+ optional download)

License: NICE UK Open Content Licence — verify attribution before redistribution.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from html import unescape
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "cpg" / "open_cpg_nice_ddx_seed.json"
CACHE_LIST = ROOT / "data" / "cpg" / "api" / "nice_published_list_latest.json"
CACHE_CHAPTERS = ROOT / "data" / "cpg" / "api" / "nice_ddx_chapters_latest.jsonl"

USER_AGENT = (
    "Mozilla/5.0 (compatible; Agentclinic-Tree-Dx-Spec/0.1; research) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PUBLISHED_BASE = "https://www.nice.org.uk/guidance/published?sp=on&ps=9999"

# Clinical CPG types in the published index (skip TA/HTG/MIB drug & device appraisals).
CLINICAL_PREFIXES = frozenset({"ng", "cg", "dg", "sc"})

TITLE_DDX_RE = re.compile(
    r"\b("
    r"differential diagnos|diagnosis|diagnosing|diagnostic|"
    r"assessment and|assessment of|initial assessment|"
    r"recognition and referral|recognising|recognizing|"
    r"suspected|referral|evaluation|presenting|"
    r"symptoms and signs|identifying|investigation|"
    r"work-?up|triage|screening|exclude|distinguish"
    r")\b",
    re.I,
)

CHAPTER_DDX_RE = re.compile(
    r"differential|diagnos|assess|evaluat|recogni|referral|suspect|"
    r"symptoms|signs|presenting|investigation|identifying|"
    r"excluding|distinguish|work-?up|triage|initial|"
    r"clinical.features|making.the.diagnos|confirming|"
    r"recommended.actions|organised.by|safety.netting|"
    r"rationale|introduction|overview|using.this",
    re.I,
)

# Sidebar / overview sections always kept when the guidance is DDx-relevant.
SIDEBAR_OVERVIEW_RE = re.compile(
    r"^(overview|introduction|using this guideline|rationale and impact|"
    r"summary|context|scope|key points)$",
    re.I,
)

CHAPTER_SKIP_RE = re.compile(
    r"recommendations for research|committee details|update information|"
    r"terms used|finding more information|finding more|"
    r"support and information|putting this guideline into practice|"
    r"who should read|evidence review|conflict of interest|"
    r"equality and diversity|prescribing|monitoring",
    re.I,
)

BODY_DDX_RE = re.compile(
    r"\b(differential diagnos|distinguish(?:ing)?|rule out|exclude|"
    r"alternative diagnos|other causes|consider(?:ing)?|"
    r"diagnos(?:is|tic)|assessment|refer(?:ral)?)\b",
    re.I,
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def fetch_text(url: str, timeout: int = 90, retries: int = 3) -> str:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-GB,en;q=0.9",
                },
            )
            ctx = ssl.create_default_context()
            with urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, IncompleteRead, OSError) as exc:
            last_exc = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def parse_published_page(html: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for url, ref, title in re.findall(
        r'<a[^>]+href="(https://www\.nice\.org\.uk/guidance/([a-z]+\d+))"[^>]*>([^<]+)</a>',
        html,
        re.I,
    ):
        ref = ref.lower()
        if ref in seen:
            continue
        seen.add(ref)
        prefix = re.match(r"([a-z]+)", ref)
        rows.append(
            {
                "ref": ref,
                "prefix": prefix.group(1) if prefix else "",
                "title": unescape(title.strip()),
                "url": url.split("?", 1)[0],
            }
        )
    return rows


def crawl_published_list(*, use_cache: bool, timeout: int, sleep: float) -> list[dict]:
    if use_cache and CACHE_LIST.exists():
        return json.loads(CACHE_LIST.read_text(encoding="utf-8"))

    all_rows: dict[str, dict] = {}
    pa = 1
    while True:
        url = PUBLISHED_BASE if pa == 1 else f"{PUBLISHED_BASE}&pa={pa}"
        print(f"fetch list pa={pa} …", flush=True)
        html = fetch_text(url, timeout=timeout)
        page_rows = parse_published_page(html)
        if not page_rows:
            break
        for row in page_rows:
            all_rows[row["ref"]] = row
        if "pa=" + str(pa + 1) not in html and f"pa={pa + 1}" not in html:
            # also check URL-encoded amp
            if f"pa={pa + 1}" not in html.replace("&amp;", "&"):
                break
        next_marker = f"pa={pa + 1}"
        if next_marker not in html.replace("&amp;", "&"):
            break
        pa += 1
        if sleep > 0:
            time.sleep(sleep)

    rows = sorted(all_rows.values(), key=lambda r: r["ref"])
    CACHE_LIST.parent.mkdir(parents=True, exist_ok=True)
    CACHE_LIST.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


def guidance_candidate(row: dict, *, clinical_only: bool) -> bool:
    prefix = row["prefix"]
    title = row["title"]
    if prefix in CLINICAL_PREFIXES:
        return True
    if clinical_only:
        return False
    return bool(TITLE_DDX_RE.search(title))


def _chapter_blob(slug: str, title: str) -> str:
    return re.sub(r"[-_]+", " ", f"{slug} {title}".lower())


def extract_sidebar_chapters(html: str, ref: str) -> list[tuple[str, str, str, str]]:
    """Parse ``stacked-nav`` sidebar → (slug, nav_title, url, kind).

    kind is ``overview`` for the guidance landing page, else ``chapter``.
    """
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    nav_re = re.compile(
        r'stacked-nav__list-item.*?href="(/guidance/[^"]+)"'
        r'.*?stacked-nav__content-wrapper">\s*([^<]+?)\s*</span>',
        re.I | re.S,
    )
    for path, nav_title in nav_re.findall(html):
        nav_title = unescape(re.sub(r"\s+", " ", nav_title.strip()))
        path = path.split("?", 1)[0]
        if path in seen:
            continue
        seen.add(path)
        url = f"https://www.nice.org.uk{path}"
        m = re.search(rf"/guidance/{re.escape(ref)}/chapter/([^/]+)$", path, re.I)
        if m:
            slug = m.group(1)
            kind = "chapter"
        elif re.search(rf"/guidance/{re.escape(ref)}$", path, re.I):
            slug = "overview"
            kind = "overview"
        else:
            continue
        out.append((slug, nav_title, url, kind))
    return out


def extract_chapters_fallback(html: str, ref: str) -> list[tuple[str, str, str, str]]:
    """Fallback when sidebar markup is absent."""
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(
        rf'href="(/guidance/{re.escape(ref)}(?:/chapter/([^"]+))?)"[^>]*>([^<]+)',
        re.I,
    )
    for path, slug, title in pattern.findall(html):
        path = path.split("?", 1)[0]
        if path in seen:
            continue
        seen.add(path)
        title = unescape(re.sub(r"\s+", " ", title.strip()))
        url = f"https://www.nice.org.uk{path}"
        if slug:
            kind = "chapter"
        else:
            slug, kind = "overview", "overview"
        out.append((slug.strip(), title, url, kind))
    return out


def should_keep_chapter(
    slug: str,
    nav_title: str,
    guidance_title: str,
    *,
    guidance_is_ddx: bool,
    all_sidebar: bool = False,
) -> bool:
    blob = _chapter_blob(slug, nav_title)
    if CHAPTER_SKIP_RE.search(blob):
        return False
    if all_sidebar:
        return True
    if SIDEBAR_OVERVIEW_RE.search(nav_title.strip()) or slug.lower() == "overview":
        return guidance_is_ddx or bool(TITLE_DDX_RE.search(guidance_title))
    if CHAPTER_DDX_RE.search(blob):
        return True
    if guidance_is_ddx and re.search(
        r"symptoms|signs|diagnosis|assessment|referral|investigation|"
        r"recogni|suspect|differential|presenting|initial|evaluat|"
        r"identifying|recommended|organised|early pregnancy|"
        r"diagnostic process|safety netting",
        blob,
        re.I,
    ):
        return True
    return False


def collect_guidance_chapters(
    html: str,
    ref: str,
    guidance_title: str,
    *,
    guidance_is_ddx: bool,
    all_sidebar: bool = False,
) -> list[tuple[str, str, str]]:
    """Return (slug, nav_title, url) to fetch."""
    sidebar = extract_sidebar_chapters(html, ref)
    if not sidebar:
        sidebar = extract_chapters_fallback(html, ref)
    # If overview page has a thin nav, try to expand from inline chapter links.
    if len(sidebar) < 4:
        merged = {u: x for x in sidebar for u in [x[2]]}
        for item in extract_chapters_fallback(html, ref):
            if item[2] not in merged:
                merged[item[2]] = item
        sidebar = list(merged.values())

    kept: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for slug, nav_title, url, _kind in sidebar:
        if url in seen:
            continue
        if not should_keep_chapter(
            slug, nav_title, guidance_title,
            guidance_is_ddx=guidance_is_ddx,
            all_sidebar=all_sidebar,
        ):
            continue
        seen.add(url)
        kept.append((slug, nav_title, url))
    return kept


def chapter_has_ddx_body(url: str, timeout: int) -> bool:
    try:
        html = fetch_text(url, timeout=timeout)
    except (HTTPError, URLError, TimeoutError):
        return True  # keep on fetch failure; chapter slug already matched
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", unescape(text))
    return bool(BODY_DDX_RE.search(text[:120_000]))


def build_seed(
    rows: list[dict],
    *,
    clinical_only: bool,
    all_sidebar: bool,
    verify_body: bool,
    timeout: int,
    sleep: float,
    limit: int,
) -> tuple[list[dict], list[dict]]:
    """Return (seed_items, audit_log)."""
    candidates = [r for r in rows if guidance_candidate(r, clinical_only=clinical_only)]
    if limit > 0:
        candidates = candidates[:limit]

    seed: list[dict] = []
    audit: list[dict] = []
    seen_urls: set[str] = set()

    for i, row in enumerate(candidates, 1):
        ref = row["ref"]
        print(f"[{i}/{len(candidates)}] {ref} {row['title'][:60]}…", flush=True)
        try:
            html = fetch_text(row["url"], timeout=timeout)
        except (HTTPError, URLError, TimeoutError) as exc:
            audit.append({**row, "status": "guidance_fetch_error", "error": str(exc)})
            continue

        guidance_is_ddx = bool(TITLE_DDX_RE.search(row["title"]))
        chapters = collect_guidance_chapters(
            html, ref, row["title"],
            guidance_is_ddx=guidance_is_ddx,
            all_sidebar=all_sidebar,
        )

        # Sidebar on overview can be incomplete — probe first chapter for full nav.
        min_nav = 2 if all_sidebar else 3
        if len(chapters) < min_nav:
            probe = re.search(
                rf'href="(/guidance/{re.escape(ref)}/chapter/[^"]+)"', html, re.I,
            )
            if probe:
                try:
                    ch_html = fetch_text(f"https://www.nice.org.uk{probe.group(1).split('?',1)[0]}", timeout=timeout)
                    extra = collect_guidance_chapters(
                        ch_html, ref, row["title"],
                        guidance_is_ddx=guidance_is_ddx,
                        all_sidebar=all_sidebar,
                    )
                    by_url = {u: (s, t, u) for s, t, u in chapters}
                    for item in extra:
                        by_url[item[2]] = item
                    chapters = list(by_url.values())
                except Exception:
                    pass

        if not chapters:
            audit.append({**row, "status": "no_ddx_chapters", "chapters": 0})
            if sleep > 0:
                time.sleep(sleep)
            continue

        kept = 0
        for slug, ch_title, ch_url in chapters:
            if verify_body and not chapter_has_ddx_body(ch_url, timeout=timeout):
                continue
            if ch_url in seen_urls:
                continue
            seen_urls.add(ch_url)
            kept += 1
            seed.append(
                {
                    "id": f"nice_ddx__{ref}__{slugify(slug)}"[:120],
                    "parent_id": f"nice_guidance_{ref}",
                    "source": "NICE",
                    "title": f"{row['title']} — {ch_title}",
                    "url": ch_url,
                    "clinical_area": ["nice", "guideline", "differential_diagnosis"],
                    "access": "public_html",
                    "license_note": "NICE UK Open Content Licence; verify attribution.",
                    "nice_ref": ref,
                    "chapter_slug": slug,
                }
            )
            if sleep > 0:
                time.sleep(sleep)

        audit.append({**row, "status": "ok", "chapters_found": len(chapters), "chapters_kept": kept})
        if sleep > 0:
            time.sleep(sleep)

    seed.sort(key=lambda x: x["id"])
    return seed, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--use-cache-list", action="store_true", help="reuse nice_published_list_latest.json")
    parser.add_argument(
        "--all-title-ddx",
        action="store_true",
        help="also include non-NG/CG/DG/SC entries whose title matches DDx keywords",
    )
    parser.add_argument(
        "--all-sidebar",
        action="store_true",
        help="keep every sidebar chapter (except research/committee/update/terms); default is DDx-filtered subset",
    )
    parser.add_argument("--verify-body", action="store_true", help="fetch chapter HTML and confirm DDx terms")
    parser.add_argument("--limit", type=int, default=0, help="max guidance items to scan (0=all)")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--download", action="store_true", help="run download_open_cpg.py after seed build")
    args = parser.parse_args()

    clinical_only = not args.all_title_ddx
    rows = crawl_published_list(
        use_cache=args.use_cache_list,
        timeout=args.timeout,
        sleep=args.sleep,
    )
    seed, audit = build_seed(
        rows,
        clinical_only=clinical_only,
        all_sidebar=args.all_sidebar,
        verify_body=args.verify_body,
        timeout=args.timeout,
        sleep=args.sleep,
        limit=args.limit,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CACHE_CHAPTERS.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_CHAPTERS.open("w", encoding="utf-8") as f:
        for row in audit:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "published_list": len(rows),
        "guidance_scanned": len(audit),
        "seed_chapters": len(seed),
        "out": str(args.out.relative_to(ROOT)),
        "audit": str(CACHE_CHAPTERS.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.download and seed:
        import subprocess

        rc = subprocess.call(
            [
                sys.executable,
                str(ROOT / "scripts" / "download_open_cpg.py"),
                "--seed",
                str(args.out),
                "--timeout",
                str(args.timeout),
                "--skip-existing",
                "--insecure",
                "--sleep",
                str(max(args.sleep, 0.35)),
            ],
            cwd=str(ROOT),
        )
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Derive explicit CPG seed entries from downloaded index pages.

Reads HTML mirrors under data/cpg/raw/, extracts official child links, merges
with a hand-curated expansion list, and writes data/cpg/open_cpg_seed.json.
Some indexes need a one-shot live fetch (RCOG green-top, ATS statements hub).
"""

from __future__ import annotations

import html
import json
import os
import re
import ssl
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "cpg" / "raw"
SEED = ROOT / "data" / "cpg" / "open_cpg_seed.json"
EXPANSION = ROOT / "data" / "cpg" / "open_cpg_seed_expansion.json"
POC_SEED = ROOT / "data" / "cpg" / "open_poc_seed.json"
API_SEED = ROOT / "data" / "cpg" / "open_cpg_api_seed.json"
NICE_SEED = ROOT / "data" / "cpg" / "open_cpg_nice_seed.json"
NICE_PUBLIC_SEED = ROOT / "data" / "cpg" / "open_cpg_nice_public_seed.json"
NICE_DDX_SEED = ROOT / "data" / "cpg" / "open_cpg_nice_ddx_seed.json"
USER_AGENT = (
    "Mozilla/5.0 (compatible; Agentclinic-Tree-Dx-Spec/0.3; "
    "+https://github.com/local/research) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DERIVED_PREFIXES = (
    "cdc_hiv_child__",
    "acr_cms__",
    "acr_ac__",
    "idsa_child__",
    "ash_child__",
    "ash_sub__",
    "endocrine_child__",
    "endocrine_pm__",
    "endocrine_oup__",
    "acr_rheum_child__",
    "eular_child__",
    "ats_child__",
    "rcog_child__",
    "msd_child__",
    "esmo_api__",
    "acog_child__",
    "aan_pm__",
    "acc_aha_pm__",
    "esc_epmc__",
    "ash_ba_epmc__",
    "ssc_epmc__",
    "ssc_pm__",
    "sccm_child__",
)
DEPRECATED_IDS = {"who_antibiotic_awareness_index"}

IDSA_SKIP_SLUGS = {
    "all-practice-guidelines",
    "practice-guidelines",
    "idsa-practice-guidelines-app",
}
ENDOCRINE_SKIP = {"mobile-app", "clinical-practice-guidelines"}
ACOG_GUIDANCE_TYPES = {
    "practice-bulletin",
    "committee-opinion",
    "clinical-practice-guideline",
    "practice-advisory",
    "clinical-consensus",
    "committee-statement",
    "obstetric-care-consensus",
}
PUBMED_EMAIL = os.environ.get("PUBMED_EMAIL", "research@local.invalid")
PUBMED_API_KEY = os.environ.get("NCBI_API_KEY")
MSD_SKIP_PREFIXES = (
    "/professional/_next/",
    "/professional/content/",
    "/professional/pages-with-widgets/",
    "/professional/resourcespages/",
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"expected list in {path}")
    return data


def ssl_context(insecure: bool = True) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ctx


def fetch_url(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout, context=ssl_context(True)) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 60) -> dict | list:
    return json.loads(fetch_url(url, timeout=timeout))


def pubmed_esearch(term: str, retmax: int) -> list[str]:
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(retmax),
        "retmode": "json",
        "email": PUBMED_EMAIL,
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode(params)
    data = fetch_json(url)
    return data.get("esearchresult", {}).get("idlist", [])


def pubmed_esummary(pmids: list[str]) -> dict[str, dict]:
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "email": PUBMED_EMAIL,
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode(params)
    data = fetch_json(url)
    result = data.get("result", {})
    return {pid: result.get(pid, {}) for pid in pmids if pid in result}


def pubmed_pmc_ids(pmids: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pmid in pmids:
        params = {
            "dbfrom": "pubmed",
            "db": "pmc",
            "id": pmid,
            "retmode": "json",
            "email": PUBMED_EMAIL,
        }
        if PUBMED_API_KEY:
            params["api_key"] = PUBMED_API_KEY
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?" + urlencode(params)
        try:
            data = fetch_json(url)
        except (URLError, OSError, TimeoutError, json.JSONDecodeError):
            continue
        for linkset in data.get("linksets", []):
            if str(linkset.get("ids", [""])[0]) != pmid:
                continue
            for ldb in linkset.get("linksetdbs", []):
                if ldb.get("linkname") == "pubmed_pmc" and ldb.get("links"):
                    mapping[pmid] = f"PMC{ldb['links'][0]}"
                    break
        time.sleep(0.12)
    return mapping


def read_raw(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def make_item(
    *,
    item_id: str,
    parent_id: str,
    source: str,
    title: str,
    url: str,
    clinical_area: list[str],
    access: str = "public_html",
) -> dict:
    return {
        "id": item_id,
        "parent_id": parent_id,
        "source": source,
        "title": title,
        "url": url,
        "clinical_area": clinical_area,
        "access": access,
    }


def existing_urls(items: list[dict]) -> set[str]:
    urls: set[str] = set()
    for item in items:
        url = item.get("url")
        if url:
            urls.add(url.rstrip("/"))
        for attachment in item.get("attachments", []):
            aurl = attachment.get("url")
            if aurl:
                urls.add(aurl.rstrip("/"))
    return urls


def extract_cdc_hiv_links() -> list[dict]:
    text = read_raw(RAW / "cdc" / "cdc-hiv-guidelines-index.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for href, title in re.findall(r'<p>\s*<a href="([^"]+)"[^>]*>([^<]{8,220})</a>', text):
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        title = re.sub(r"\s*external icon\s*$", "", title, flags=re.I).strip()
        if href.startswith("/"):
            url = "https://www.cdc.gov" + href
        elif href.startswith("http"):
            url = href.split("&amp;")[0]
        else:
            continue
        host = urlparse(url).netloc.lower()
        allowed_hosts = {
            "www.cdc.gov",
            "cdc.gov",
            "clinicalinfo.hiv.gov",
            "stacks.cdc.gov",
            "www.uspreventiveservicestaskforce.org",
            "uspreventiveservicestaskforce.org",
            "www.acpjournals.org",
            "acpjournals.org",
            "academic.oup.com",
        }
        if host not in allowed_hosts or url in seen:
            continue
        seen.add(url)
        access = "public_pdf" if url.lower().endswith(".pdf") else "public_html"
        items.append(
            make_item(
                item_id=f"cdc_hiv_child__{slugify(title)[:80]}",
                parent_id="cdc_hiv_guidelines_index",
                source="CDC",
                title=title,
                url=url,
                clinical_area=["infectious disease", "HIV"],
                access=access,
            )
        )
    return items


def extract_acr_narratives() -> list[dict]:
    text = read_raw(RAW / "acr" / "acr-appropriateness-criteria.html")
    if not text:
        return []
    titles_by_doc: dict[str, str] = {}
    for m in re.finditer(r'topicHeading">\s*([^<]+?)\s*</span>', text):
        heading = re.sub(r"\s+", " ", m.group(1)).strip()
        if not heading or heading == "\n":
            continue
        chunk = text[m.end() : m.end() + 8000]
        nm = re.search(r'href="(/docs/(\d+)/Narrative/)"', chunk)
        if nm:
            titles_by_doc[nm.group(2)] = heading

    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="(/docs/(\d+)/Narrative/)"', text):
        doc_id = m.group(2)
        if doc_id in seen:
            continue
        seen.add(doc_id)
        title = titles_by_doc.get(doc_id, f"ACR Appropriateness Criteria (document {doc_id})")
        url = urljoin("https://acsearch.acr.org", m.group(1))
        items.append(
            make_item(
                item_id=f"acr_ac__{doc_id}",
                parent_id="acr_appropriateness_criteria",
                source="ACR",
                title=f"ACR Appropriateness Criteria: {title}",
                url=url,
                clinical_area=["radiology", "diagnostic testing"],
            )
        )
    return items


def extract_idsa_az(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "idsa" / "idsa-all-guidelines-az.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for href, slug in re.findall(r'href="(/practice-guideline/([^"/]+)/)"', text):
        if slug in IDSA_SKIP_SLUGS or slug.endswith("-folder"):
            continue
        url = f"https://www.idsociety.org{href}".rstrip("/") + "/"
        if url.rstrip("/") in skip_urls or slug in seen:
            continue
        seen.add(slug)
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"idsa_child__{slug[:80]}",
                parent_id="idsa_all_guidelines_az",
                source="IDSA",
                title=f"IDSA Practice Guideline: {title}",
                url=url,
                clinical_area=["infectious disease"],
            )
        )
    return items


def extract_ash_guidelines(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "ash" / "ash-guidelines-index.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    pattern = (
        r'href="(/education/clinicians/guidelines-and-quality-care/'
        r"clinical-practice-guidelines/[a-z0-9-]+)"
    )
    for path in re.findall(pattern, text):
        url = urljoin("https://www.hematology.org", path)
        slug = path.rsplit("/", 1)[-1]
        if slug in seen or url.rstrip("/") in skip_urls:
            continue
        seen.add(slug)
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"ash_child__{slug[:80]}",
                parent_id="ash_guidelines_index",
                source="ASH",
                title=f"ASH Clinical Practice Guideline: {title}",
                url=url,
                clinical_area=["hematology", "oncology"],
            )
        )
    return items


def extract_endocrine_categories(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "endocrine-society" / "endocrine-society-guidelines-index.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for path in re.findall(r'href="(/clinical-practice-guidelines/[a-z0-9-]+)"', text):
        slug = path.rsplit("/", 1)[-1]
        if slug in ENDOCRINE_SKIP or slug in seen:
            continue
        url = urljoin("https://www.endocrine.org", path)
        if url.rstrip("/") in skip_urls:
            continue
        seen.add(slug)
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"endocrine_child__{slug[:80]}",
                parent_id="endocrine_society_guidelines_index",
                source="Endocrine Society",
                title=f"Endocrine Society Guidelines: {title}",
                url=url,
                clinical_area=["endocrinology"],
            )
        )
    return items


def extract_acr_rheum_guidelines(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "acr" / "acr-rheumatology-guidelines-index.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for path, slug in re.findall(r'href="(/([a-z0-9-]+-guideline)[^"]*)"', text):
        if slug == "clinical-practice-guideline" or slug in seen:
            continue
        url = urljoin("https://rheumatology.org", path)
        if url.rstrip("/") in skip_urls:
            continue
        seen.add(slug)
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"acr_rheum_child__{slug[:80]}",
                parent_id="acr_rheumatology_guidelines_index",
                source="ACR",
                title=f"ACR Rheumatology Guideline: {title}",
                url=url,
                clinical_area=["rheumatology"],
            )
        )
    return items


def extract_eular_recommendations(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "eular" / "eular-recommendations-index.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()

    for m in re.finditer(
        r'(?:<h[234][^>]*>([^<]{8,220})</h[234]>|<strong[^>]*>([^<]{8,220})</strong>)',
        text,
    ):
        heading = re.sub(r"\s+", " ", (m.group(1) or m.group(2) or "")).strip()
        if not heading or heading.lower().startswith("read "):
            continue
        chunk = text[m.end() : m.end() + 3000]
        rm = re.search(
            r'href="(https://ard\.bmj\.com/content/[^"]+)"[^>]*>\s*Read [Rr]ecommendation',
            chunk,
        )
        if not rm:
            continue
        url = rm.group(1).split("?")[0].replace(".full", "").rstrip("/")
        if url in skip_urls or url in seen:
            continue
        seen.add(url)
        items.append(
            make_item(
                item_id=f"eular_child__{slugify(heading)[:80]}",
                parent_id="eular_recommendations_index",
                source="EULAR",
                title=heading,
                url=url,
                clinical_area=["rheumatology"],
            )
        )

    for m in re.finditer(
        r'href="(https://ard\.bmj\.com/content/[^"]+)"[^>]*>\s*Read [Rr]ecommendation',
        text,
        re.I,
    ):
        url = m.group(1).split("?")[0].replace(".full", "").rstrip("/")
        if url in skip_urls or url in seen:
            continue
        seen.add(url)
        slug = url.rsplit("/", 1)[-1]
        items.append(
            make_item(
                item_id=f"eular_child__{slugify(slug)[:80]}",
                parent_id="eular_recommendations_index",
                source="EULAR",
                title=f"EULAR Recommendation ({slug})",
                url=url,
                clinical_area=["rheumatology"],
            )
        )
    return items


def extract_ats_statements(skip_urls: set[str]) -> list[dict]:
    urls: set[str] = set()
    try:
        html_text = fetch_url(
            "https://site.thoracic.org/clinicians-researchers/"
            "clinical-practice-guidelines-statements-reports"
        )
    except (URLError, OSError, TimeoutError):
        html_text = read_raw(RAW / "ats" / "ats-statements-index.html")
    for m in re.finditer(r'href="(https://www\.thoracic\.org/statements/[^"]+)"', html_text):
        url = m.group(1).split("#")[0]
        if "implementation-tools" in url or url.endswith(".php"):
            urls.add(url)
    items: list[dict] = []
    for url in sorted(urls):
        if url.rstrip("/") in skip_urls:
            continue
        slug = slugify(Path(urlparse(url).path).stem)
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"ats_child__{slug[:80]}",
                parent_id="ats_statements_index",
                source="ATS",
                title=f"ATS Statement / Guideline Tool: {title}",
                url=url,
                clinical_area=["pulmonary"],
            )
        )
    return items


def extract_rcog_green_top(skip_urls: set[str]) -> list[dict]:
    try:
        html_text = fetch_url(
            "https://www.rcog.org.uk/guidance/browse-all-guidance/green-top-guidelines/"
        )
    except (URLError, OSError, TimeoutError):
        html_text = read_raw(RAW / "rcog" / "rcog-guidelines-index.html")
    items: list[dict] = []
    seen: set[str] = set()
    for path in re.findall(
        r'href="(/guidance/browse-all-guidance/green-top-guidelines/[a-z0-9-]+/)"',
        html_text,
        re.I,
    ):
        url = urljoin("https://www.rcog.org.uk", path)
        if url.rstrip("/") in skip_urls or path in seen:
            continue
        seen.add(path)
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"rcog_child__{slug[:80]}",
                parent_id="rcog_guidelines_index",
                source="RCOG",
                title=f"RCOG Green-top Guideline: {title}",
                url=url,
                clinical_area=["obstetrics", "gynecology"],
            )
        )
    return items


def extract_msd_topics(skip_urls: set[str]) -> list[dict]:
    text = read_raw(RAW / "merck-msd-manual" / "msdmanual-professional-index.html")
    items: list[dict] = []
    seen: set[str] = set()

    try:
        topics_html = fetch_url("https://www.msdmanuals.com/professional/health-topics")
    except (URLError, OSError, TimeoutError):
        topics_html = text
    for path in re.findall(r'href="(/professional/[a-z0-9-]+(?:-[a-z0-9-]+)*)"(?=[^>]*>|\s)', topics_html):
        if path in {"/professional/health-topics", "/professional/resource"}:
            continue
        if any(path.startswith(prefix.rstrip("/")) for prefix in MSD_SKIP_PREFIXES):
            continue
        segments = [s for s in path.split("/") if s]
        if len(segments) != 2:
            continue
        url = urljoin("https://www.msdmanuals.com", path)
        norm = url.rstrip("/")
        if norm in skip_urls or norm in seen:
            continue
        seen.add(norm)
        title = segments[1].replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"msd_child__{slugify(segments[1])[:80]}",
                parent_id="msdmanual_professional_index",
                source="Merck/MSD Manual",
                title=f"MSD Manual: {title}",
                url=url,
                clinical_area=["point-of-care", segments[1].replace("-", " ")],
            )
        )

    if not text:
        return items
    for path in re.findall(r'href="(/professional/[^"?#]+)"', text):
        if any(path.startswith(prefix) for prefix in MSD_SKIP_PREFIXES):
            continue
        segments = [s for s in path.split("/") if s]
        if len(segments) < 3:
            continue
        if segments[1] in {"news", "resources"}:
            continue
        url = urljoin("https://www.msdmanuals.com", path.split("?")[0])
        norm = url.rstrip("/")
        if norm in skip_urls or norm in seen:
            continue
        seen.add(norm)
        title = segments[-1].replace("-", " ").title()
        specialty = segments[1].replace("-", " ")
        items.append(
            make_item(
                item_id=f"msd_child__{slugify('/'.join(segments[1:]))[:80]}",
                parent_id="msdmanual_professional_index",
                source="Merck/MSD Manual",
                title=f"MSD Manual: {title}",
                url=url,
                clinical_area=["point-of-care", specialty],
            )
        )

    nav_paths = {
        "/professional/health-topics": "MSD Manual Health Topics index",
        "/professional/resource": "MSD Manual Clinical Resources index",
        "/professional/drug-names-generic-and-brand": "MSD Manual Drug Names (Generic and Brand)",
        "/professional/resources/normal-laboratory-values/laboratory-reference-ranges": (
            "MSD Manual Laboratory Reference Ranges"
        ),
    }
    for path, title in nav_paths.items():
        url = urljoin("https://www.msdmanuals.com", path)
        if url.rstrip("/") in skip_urls or url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))
        items.append(
            make_item(
                item_id=f"msd_child__{slugify(path)[:80]}",
                parent_id="msdmanual_professional_index",
                source="Merck/MSD Manual",
                title=title,
                url=url,
                clinical_area=["point-of-care"],
            )
        )
    return items


def extract_ash_subguidelines(skip_urls: set[str]) -> list[dict]:
    """Expand ASH disease hubs into topic sub-pages (VTE, SCD, etc.)."""
    items: list[dict] = []
    seen: set[str] = set()
    hub_paths: set[str] = set()

    index_text = read_raw(RAW / "ash" / "ash-guidelines-index.html")
    if index_text:
        hub_paths.update(
            re.findall(
                r"/education/clinicians/guidelines-and-quality-care/"
                r"clinical-practice-guidelines/[a-z0-9-]+",
                index_text,
            )
        )

    for path in sorted(hub_paths):
        slug = path.rsplit("/", 1)[-1]
        raw_path = RAW / "ash" / f"ash-child-{slug}.html"
        text = read_raw(raw_path)
        if not text:
            try:
                text = fetch_url("https://www.hematology.org" + path)
            except (URLError, OSError, TimeoutError):
                continue
        parent_id = f"ash_child__{slug}"
        pattern = re.compile(rf'href="({re.escape(path)}/[a-z0-9-]+)"')
        for subpath in sorted(set(pattern.findall(text))):
            url = urljoin("https://www.hematology.org", subpath)
            if url.rstrip("/") in skip_urls or subpath in seen:
                continue
            seen.add(subpath)
            sub_slug = subpath.rsplit("/", 1)[-1]
            title = sub_slug.replace("-", " ").title()
            items.append(
                make_item(
                    item_id=f"ash_sub__{slug[:40]}__{sub_slug[:40]}",
                    parent_id=parent_id,
                    source="ASH",
                    title=f"ASH Guideline Topic: {title}",
                    url=url,
                    clinical_area=["hematology", "oncology"],
                )
            )
    return items


def extract_acog_clinical_guidance(skip_urls: set[str]) -> list[dict]:
    """Parse ACOG sitemap for public clinical guidance articles."""
    try:
        xml_text = fetch_url("https://www.acog.org/sitemap.xml", timeout=90)
    except (URLError, OSError, TimeoutError):
        return []
    items: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"<loc>(https://www\.acog\.org/clinical/clinical-guidance/"
        r"([^/]+)/articles/(\d{4})/(\d{2})/([^<]+))</loc>"
    )
    for url, guidance_type, year, month, slug in pattern.findall(xml_text):
        if guidance_type not in ACOG_GUIDANCE_TYPES:
            continue
        norm = url.rstrip("/")
        if norm in skip_urls or norm in seen:
            continue
        seen.add(norm)
        title = slug.replace("-", " ").title()
        label = guidance_type.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"acog_child__{guidance_type[:20]}__{year}_{month}_{slug[:50]}",
                parent_id="acog_clinical_guidance_index",
                source="ACOG",
                title=f"ACOG {label}: {title}",
                url=norm,
                clinical_area=["obstetrics", "gynecology"],
            )
        )
    return items


def extract_endocrine_collaborated(skip_urls: set[str]) -> list[dict]:
    """OUP/JCEM links from Endocrine Society collaborated & endorsed page."""
    try:
        text = fetch_url(
            "https://www.endocrine.org/clinical-practice-guidelines/"
            "collaborated-and-endorsed-guidelines"
        )
    except (URLError, OSError, TimeoutError):
        text = read_raw(RAW / "endocrine-society" / "endocrine-collaborated-guidelines.html")
    if not text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for url in re.findall(r'href="(https://academic\.oup\.com/[^"]+/article/[^"]+)"', text):
        url = url.split("?")[0]
        if "endocrinesociety/pages" in url or url in skip_urls or url in seen:
            continue
        seen.add(url)
        slug = slugify(url.rsplit("/", 1)[-1][:80])
        items.append(
            make_item(
                item_id=f"endocrine_oup__{slug[:80]}",
                parent_id="endocrine_collaborated_guidelines_index",
                source="Endocrine Society",
                title=f"Endocrine Society Guideline (OUP): {slug.replace('-', ' ')}",
                url=url,
                clinical_area=["endocrinology"],
            )
        )
    return items


def extract_pubmed_society_guidelines(
    *,
    query: str,
    source: str,
    prefix: str,
    parent_id: str,
    clinical_area: list[str],
    skip_urls: set[str],
    retmax: int = 300,
) -> list[dict]:
    """PubMed society guidelines; prefer PMC full-text URLs when linked."""
    try:
        pmids = pubmed_esearch(query, retmax=retmax)
    except (URLError, OSError, TimeoutError, json.JSONDecodeError):
        return []
    items: list[dict] = []
    seen: set[str] = set()
    batch_size = 100
    for start in range(0, len(pmids), batch_size):
        batch = pmids[start : start + batch_size]
        try:
            summaries = pubmed_esummary(batch)
            pmc_map = pubmed_pmc_ids(batch)
        except (URLError, OSError, TimeoutError, json.JSONDecodeError):
            continue
        for pmid in batch:
            meta = summaries.get(pmid, {})
            title = (meta.get("title") or f"PubMed {pmid}").strip()
            pmcid = pmc_map.get(pmid)
            if pmcid:
                url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                access = "public_html"
            else:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                access = "public_html_index"
            norm = url.rstrip("/")
            if norm in skip_urls or pmid in seen:
                continue
            seen.add(pmid)
            items.append(
                make_item(
                    item_id=f"{prefix}{pmid}",
                    parent_id=parent_id,
                    source=source,
                    title=title,
                    url=url,
                    clinical_area=clinical_area,
                    access=access,
                )
            )
        if start + batch_size < len(pmids):
            time.sleep(0.35)
    return items


def extract_endocrine_pubmed(skip_urls: set[str]) -> list[dict]:
    return extract_pubmed_society_guidelines(
        query=(
            '("Endocrine Society"[Corporate Author]) AND '
            '(Practice Guideline[PT] OR Guideline[PT] OR '
            '"clinical practice guideline"[Title])'
        ),
        source="Endocrine Society",
        prefix="endocrine_pm__",
        parent_id="endocrine_society_guidelines_index",
        clinical_area=["endocrinology"],
        skip_urls=skip_urls,
        retmax=200,
    )


def extract_aan_pubmed(skip_urls: set[str]) -> list[dict]:
    return extract_pubmed_society_guidelines(
        query=(
            '("American Academy of Neurology"[Corporate Author]) AND '
            '(Practice Guideline[PT] OR Guideline[PT] OR '
            '"practice guideline"[Title])'
        ),
        source="AAN",
        prefix="aan_pm__",
        parent_id="aan_guidelines_index",
        clinical_area=["neurology"],
        skip_urls=skip_urls,
        retmax=200,
    )


def extract_europepmc_seeds(
    *,
    query: str,
    source: str,
    prefix: str,
    parent_id: str,
    clinical_area: list[str],
    skip_urls: set[str],
    max_records: int = 150,
) -> list[dict]:
    """Europe PMC search; prefer PMC full-text URLs."""
    items: list[dict] = []
    seen: set[str] = set()
    cursor = "*"
    while len(items) < max_records:
        page_size = min(100, max_records - len(items))
        params = {
            "query": query,
            "format": "json",
            "pageSize": str(page_size),
            "cursorMark": cursor,
            "resultType": "core",
        }
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode(params)
        try:
            data = fetch_json(url, timeout=90)
        except (URLError, OSError, TimeoutError, json.JSONDecodeError):
            break
        hits = data.get("resultList", {}).get("result", [])
        if not hits:
            break
        for hit in hits:
            pmcid = hit.get("pmcid")
            pmid = hit.get("pmid")
            title = (hit.get("title") or "Untitled").strip()
            if pmcid:
                out_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                access = "public_html"
                key = pmcid
            elif pmid:
                out_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                access = "public_html_index"
                key = f"pmid_{pmid}"
            else:
                continue
            norm = out_url.rstrip("/")
            if norm in skip_urls or key in seen:
                continue
            seen.add(key)
            items.append(
                make_item(
                    item_id=f"{prefix}{slugify(key)[:80]}",
                    parent_id=parent_id,
                    source=source,
                    title=title,
                    url=out_url,
                    clinical_area=clinical_area,
                    access=access,
                )
            )
        next_cursor = data.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(0.25)
    return items


def extract_acc_aha_pubmed(skip_urls: set[str]) -> list[dict]:
    return extract_pubmed_society_guidelines(
        query=(
            '("American College of Cardiology"[Corporate Author] OR '
            '"American Heart Association"[Corporate Author]) AND '
            '(Practice Guideline[PT] OR Guideline[PT]) AND 2010:2026[PDAT]'
        ),
        source="ACC/AHA",
        prefix="acc_aha_pm__",
        parent_id="acc_aha_guidelines_index",
        clinical_area=["cardiology"],
        skip_urls=skip_urls,
        retmax=250,
    )


def extract_esc_europepmc(skip_urls: set[str]) -> list[dict]:
    return extract_europepmc_seeds(
        query='JOURNAL:"Eur Heart J" AND "ESC Guidelines"',
        source="ESC",
        prefix="esc_epmc__",
        parent_id="esc_guidelines_index",
        clinical_area=["cardiology"],
        skip_urls=skip_urls,
        max_records=150,
    )


def extract_ash_blood_europepmc(skip_urls: set[str]) -> list[dict]:
    return extract_europepmc_seeds(
        query=(
            'JOURNAL:"Blood Adv" AND "American Society of Hematology" '
            'AND (guideline OR guidelines)'
        ),
        source="ASH",
        prefix="ash_ba_epmc__",
        parent_id="ash_guidelines_index",
        clinical_area=["hematology", "oncology"],
        skip_urls=skip_urls,
        max_records=120,
    )


def extract_ssc_europepmc(skip_urls: set[str]) -> list[dict]:
    return extract_europepmc_seeds(
        query=(
            'JOURNAL:"Crit Care Med" AND ("Surviving Sepsis Campaign" OR SCCM) '
            'AND (guideline OR guidelines)'
        ),
        source="SSC/SCCM",
        prefix="ssc_epmc__",
        parent_id="sccm_guidelines_index",
        clinical_area=["emergency", "critical care", "sepsis"],
        skip_urls=skip_urls,
        max_records=80,
    )


def extract_ssc_pubmed(skip_urls: set[str]) -> list[dict]:
    return extract_pubmed_society_guidelines(
        query=(
            '("Surviving Sepsis Campaign"[All Fields] OR '
            '"Society of Critical Care Medicine"[Corporate Author]) AND '
            '(Practice Guideline[PT] OR Guideline[PT])'
        ),
        source="SSC/SCCM",
        prefix="ssc_pm__",
        parent_id="sccm_guidelines_index",
        clinical_area=["emergency", "critical care", "sepsis"],
        skip_urls=skip_urls,
        retmax=120,
    )


def extract_sccm_guidelines(skip_urls: set[str]) -> list[dict]:
    """Individual SCCM-hosted guideline pages from the guidelines hub."""
    try:
        html_text = fetch_url("https://sccm.org/clinical-resources/guidelines/guidelines", timeout=90)
    except (URLError, OSError, TimeoutError):
        html_text = read_raw(RAW / "ssc-sccm" / "sccm-guidelines-index.html")
    if not html_text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for path in re.findall(
        r'href="(/clinical-resources/guidelines/guidelines/[a-z0-9-]+)"',
        html_text,
    ):
        url = urljoin("https://sccm.org", path)
        norm = url.rstrip("/")
        if norm in skip_urls or norm in seen:
            continue
        seen.add(norm)
        slug = path.rsplit("/", 1)[-1]
        title = slug.replace("-", " ").title()
        items.append(
            make_item(
                item_id=f"sccm_child__{slug[:80]}",
                parent_id="sccm_guidelines_index",
                source="SSC/SCCM",
                title=f"SCCM Guideline: {title}",
                url=norm,
                clinical_area=["critical care", "emergency"],
            )
        )
    return items


def primary_items(items: list[dict]) -> list[dict]:
    return [
        item
        for item in items
        if not any(item["id"].startswith(prefix) for prefix in DERIVED_PREFIXES)
    ]


def merge_seeds(base: list[dict], extra: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {item["id"]: item for item in base}
    for item in extra:
        if item["id"] in DEPRECATED_IDS:
            continue
        merged[item["id"]] = item
    return list(merged.values())


def main() -> int:
    loaded = load_json(SEED) if SEED.exists() else []
    base = primary_items(loaded)
    expansion = load_json(EXPANSION) if EXPANSION.exists() else []
    poc = load_json(POC_SEED) if POC_SEED.exists() else []
    api = load_json(API_SEED) if API_SEED.exists() else []
    nice = load_json(NICE_SEED) if NICE_SEED.exists() else []
    nice_pub = load_json(NICE_PUBLIC_SEED) if NICE_PUBLIC_SEED.exists() else []
    nice_ddx = load_json(NICE_DDX_SEED) if NICE_DDX_SEED.exists() else []
    skip_urls = existing_urls(base + expansion + poc)

    derived: list[dict] = []
    derived_breakdown: dict[str, int] = {}
    extractors: list[tuple[str, object]] = [
        ("cdc_hiv", extract_cdc_hiv_links),
        ("acr_narratives", extract_acr_narratives),
        ("idsa_az", lambda: extract_idsa_az(skip_urls)),
        ("ash", lambda: extract_ash_guidelines(skip_urls)),
        ("ash_sub", lambda: extract_ash_subguidelines(skip_urls)),
        ("endocrine", lambda: extract_endocrine_categories(skip_urls)),
        ("endocrine_oup", lambda: extract_endocrine_collaborated(skip_urls)),
        ("endocrine_pubmed", lambda: extract_endocrine_pubmed(skip_urls)),
        ("acr_rheum", lambda: extract_acr_rheum_guidelines(skip_urls)),
        ("eular", lambda: extract_eular_recommendations(skip_urls)),
        ("ats", lambda: extract_ats_statements(skip_urls)),
        ("rcog", lambda: extract_rcog_green_top(skip_urls)),
        ("msd", lambda: extract_msd_topics(skip_urls)),
        ("acog", lambda: extract_acog_clinical_guidance(skip_urls)),
        ("aan_pubmed", lambda: extract_aan_pubmed(skip_urls)),
        ("acc_aha_pubmed", lambda: extract_acc_aha_pubmed(skip_urls)),
        ("esc_europepmc", lambda: extract_esc_europepmc(skip_urls)),
        ("ash_blood_europepmc", lambda: extract_ash_blood_europepmc(skip_urls)),
        ("ssc_europepmc", lambda: extract_ssc_europepmc(skip_urls)),
        ("ssc_pubmed", lambda: extract_ssc_pubmed(skip_urls)),
        ("sccm_guidelines", lambda: extract_sccm_guidelines(skip_urls)),
    ]
    for name, fn in extractors:
        group = fn()
        derived_breakdown[name] = len(group)
        derived.extend(group)
        skip_urls.update(existing_urls(group))

    merged = merge_seeds(base, expansion + poc + api + nice + nice_pub + nice_ddx + derived)
    merged.sort(key=lambda item: item["id"])
    SEED.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "seed_path": str(SEED),
                "primary_seed": len(base),
                "expansion": len(expansion),
                "poc_seed": len(poc),
                "api_seed": len(api),
                "nice_seed": len(nice),
                "nice_public_seed": len(nice_pub),
                "nice_ddx_seed": len(nice_ddx),
                "derived_from_index": len(derived),
                "derived_breakdown": derived_breakdown,
                "total": len(merged),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

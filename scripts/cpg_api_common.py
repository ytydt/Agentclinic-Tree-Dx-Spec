"""Shared helpers for public CPG / guideline API fetch scripts."""

from __future__ import annotations

import json
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Agentclinic-Tree-Dx-Spec cpg-api/0.1 (research; mailto:local@research.invalid)"


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
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


def fetch_bytes(url: str, timeout: int = 60, headers: dict[str, str] | None = None) -> bytes:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    with urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        return resp.read()


def fetch_text(url: str, timeout: int = 60, headers: dict[str, str] | None = None) -> str:
    return fetch_bytes(url, timeout=timeout, headers=headers).decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 60, headers: dict[str, str] | None = None) -> Any:
    return json.loads(fetch_text(url, timeout=timeout, headers=headers))


def post_json(url: str, payload: dict, timeout: int = 60, headers: dict[str, str] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8")
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = Request(url, data=body, headers=hdrs, method="POST")
    with urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def merge_jsonl_latest(rows: list[dict], out_dir: Path, stem: str) -> tuple[Path, Path]:
    from datetime import datetime, timezone

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = out_dir / f"{stem}_{run_id}.jsonl"
    latest = out_dir / f"{stem}_latest.jsonl"
    write_jsonl(manifest, rows)
    latest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    return manifest, latest


def pubmed_esearch(term: str, retstart: int, retmax: int, email: str, api_key: str | None) -> dict:
    params = {
        "db": "pubmed",
        "term": term,
        "retstart": str(retstart),
        "retmax": str(retmax),
        "retmode": "json",
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode(params)
    return fetch_json(url)


def pubmed_esummary(pmids: list[str], email: str, api_key: str | None) -> dict:
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode(params)
    return fetch_json(url)


def polite_sleep(seconds: float, last_http_error: HTTPError | None = None) -> None:
    if last_http_error and last_http_error.code == 429:
        time.sleep(max(seconds, 3.0))
    else:
        time.sleep(seconds)

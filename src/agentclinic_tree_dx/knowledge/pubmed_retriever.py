"""PubMed E-utilities retrieval module for real-time literature search.

Provides a fallback pathway when both the structured LR cache and the local
RAG index fail to provide LR data for a finding-disease pair.

Uses NCBI E-utilities (free, rate-limited to 3 req/s without API key,
10 req/s with key) to search PubMed for relevant abstracts, then
attempts to extract quantitative LR/sensitivity/specificity data.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedRetriever:
    """Search PubMed for clinical evidence and extract LR data."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        max_results: int = 5,
        min_delay: float = 0.35,
        llm_extractor_fn=None,
    ) -> None:
        self._api_key = api_key
        self._max_results = max_results
        self._min_delay = min_delay
        self._last_request_time = 0.0
        self._llm_extractor_fn = llm_extractor_fn

    def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: dict) -> Optional[str]:
        try:
            import requests
        except ImportError:
            import urllib.request
            import urllib.parse
            if self._api_key:
                params["api_key"] = self._api_key
            qs = urllib.parse.urlencode(params)
            full_url = f"{url}?{qs}"
            self._rate_limit()
            try:
                with urllib.request.urlopen(full_url, timeout=15) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:
                logger.warning("PubMed request failed: %s", e)
                return None
        else:
            if self._api_key:
                params["api_key"] = self._api_key
            self._rate_limit()
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.warning("PubMed request failed: %s", e)
                return None

    def search_abstracts(
        self,
        finding: str,
        disease: str,
        *,
        max_results: Optional[int] = None,
    ) -> list[dict]:
        """Search PubMed for abstracts about a finding-disease association.

        Uses a two-tier strategy:
        1. Strict query requiring LR/sensitivity keywords
        2. Broad query for clinical association (if strict yields nothing)

        Returns list of dicts with keys: pmid, title, abstract.
        """
        k = max_results or self._max_results

        strict_query = (
            f'("{finding}"[Title/Abstract]) AND ("{disease}"[Title/Abstract]) '
            f'AND (sensitivity[Title/Abstract] OR specificity[Title/Abstract] '
            f'OR "likelihood ratio"[Title/Abstract])'
        )
        results = self._fetch_abstracts(strict_query, k)
        if results:
            return results

        broad_query = (
            f'("{finding}"[Title/Abstract]) AND ("{disease}"[Title/Abstract]) '
            f'AND (diagnosis[MeSH] OR "clinical significance"[Title/Abstract])'
        )
        return self._fetch_abstracts(broad_query, k)

    def _fetch_abstracts(self, query: str, k: int) -> list[dict]:
        """Run the E-utilities search+fetch for a given query string."""
        xml = self._get(ESEARCH_URL, {
            "db": "pubmed",
            "term": query,
            "retmax": str(k),
            "retmode": "xml",
        })
        if not xml:
            return []

        pmids = re.findall(r"<Id>(\d+)</Id>", xml)
        if not pmids:
            return []

        fetch_xml = self._get(EFETCH_URL, {
            "db": "pubmed",
            "id": ",".join(pmids[:k]),
            "rettype": "abstract",
            "retmode": "xml",
        })
        if not fetch_xml:
            return []

        results = []
        for article_match in re.finditer(
            r"<PubmedArticle>(.*?)</PubmedArticle>", fetch_xml, re.S
        ):
            block = article_match.group(1)
            pmid_m = re.search(r"<PMID[^>]*>(\d+)</PMID>", block)
            title_m = re.search(r"<ArticleTitle>(.*?)</ArticleTitle>", block, re.S)
            abstract_parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", block, re.S)

            pmid = pmid_m.group(1) if pmid_m else ""
            title = re.sub(r"<[^>]+>", "", title_m.group(1)) if title_m else ""
            abstract = " ".join(re.sub(r"<[^>]+>", "", p) for p in abstract_parts)

            if abstract:
                results.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                })

        return results

    def extract_lr_from_abstracts(
        self,
        finding: str,
        disease: str,
        abstracts: list[dict],
    ) -> Optional[dict]:
        """Extract LR data from PubMed abstracts using regex + optional LLM."""
        for ab in abstracts:
            text = ab.get("abstract", "")
            entry = self._regex_extract(finding, disease, text, ab.get("pmid", ""))
            if entry:
                return entry

        if self._llm_extractor_fn and abstracts:
            combined = "\n---\n".join(
                f"[PMID:{a['pmid']}] {a['title']}\n{a['abstract']}"
                for a in abstracts[:3]
            )
            return self._llm_extract(finding, disease, combined)

        return None

    def _regex_extract(
        self, finding: str, disease: str, text: str, pmid: str
    ) -> Optional[dict]:
        lr_match = re.search(
            r"(?:likelihood ratio|LR)\s*(?:\+|positive)?\s*(?:of|was|=|:)\s*([\d.]+)",
            text, re.I,
        )
        sn_match = re.search(
            r"sensitivity\s*(?:of|was|=|:)\s*([\d.]+)\s*%?",
            text, re.I,
        )
        sp_match = re.search(
            r"specificity\s*(?:of|was|=|:)\s*([\d.]+)\s*%?",
            text, re.I,
        )

        if not (lr_match or (sn_match and sp_match)):
            return None

        lr_val = float(lr_match.group(1)) if lr_match else None
        sn_val = float(sn_match.group(1)) if sn_match else None
        sp_val = float(sp_match.group(1)) if sp_match else None

        if sn_val and sn_val > 1:
            sn_val /= 100
        if sp_val and sp_val > 1:
            sp_val /= 100
        if lr_val is None and sn_val and sp_val and sp_val < 1:
            lr_val = sn_val / (1 - sp_val)

        lr_neg = None
        if sn_val is not None and sp_val and sp_val > 0:
            lr_neg = round((1 - sn_val) / sp_val, 4)

        return {
            "finding": finding,
            "disease": disease,
            "sensitivity": sn_val,
            "specificity": sp_val,
            "lr_positive": round(lr_val, 4) if lr_val else None,
            "lr_negative": lr_neg,
            "source": f"PubMed:PMID{pmid}",
            "confidence": "low",
        }

    def _llm_extract(
        self, finding: str, disease: str, combined_text: str
    ) -> Optional[dict]:
        """Use LLM to extract LR data from abstracts."""
        if not self._llm_extractor_fn:
            return None
        try:
            payload = {
                "task": "extract_lr",
                "finding": finding,
                "disease": disease,
                "abstracts_text": combined_text[:3000],
            }
            result = self._llm_extractor_fn(payload)
            if result and result.get("lr_positive"):
                result["source"] = "PubMed:LLM-extracted"
                result["confidence"] = "low"
                return result
        except Exception as e:
            logger.warning("LLM LR extraction failed: %s", e)
        return None

    def lookup_lr(self, finding: str, disease: str) -> Optional[dict]:
        """Full pipeline: search PubMed → fetch abstracts → extract LR."""
        abstracts = self.search_abstracts(finding, disease)
        if not abstracts:
            return None
        return self.extract_lr_from_abstracts(finding, disease, abstracts)

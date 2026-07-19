#!/usr/bin/env python3
"""Build HPO phenotype term embeddings for semantic matching.

Encodes all HPO term names + synonyms + LR cache finding names using
sentence-transformers/all-MiniLM-L6-v2 for fast cosine similarity lookup.
"""

import json
import re
import logging
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_raw"


def load_hpo_terms(obo_path: Path) -> list[dict]:
    """Parse hp.obo for all HPO terms and synonyms."""
    terms = []
    current_id = None
    current_name = None
    current_syns = []
    
    with open(obo_path) as f:
        for line in f:
            line = line.strip()
            if line == "[Term]":
                if current_id and current_name:
                    terms.append({"text": current_name, "hpo_id": current_id, "is_synonym": False, "source": "hpo_name"})
                    for syn in current_syns:
                        terms.append({"text": syn, "hpo_id": current_id, "is_synonym": True, "source": "hpo_synonym"})
                current_id = current_name = None
                current_syns = []
            elif line.startswith("id: HP:"):
                current_id = line[4:]
            elif line.startswith("name: "):
                current_name = line[6:]
            elif line.startswith("synonym: "):
                m = re.match(r'synonym:\s+"(.+?)"\s+', line)
                if m:
                    current_syns.append(m.group(1))
    
    if current_id and current_name:
        terms.append({"text": current_name, "hpo_id": current_id, "is_synonym": False, "source": "hpo_name"})
        for syn in current_syns:
            terms.append({"text": syn, "hpo_id": current_id, "is_synonym": True, "source": "hpo_synonym"})
    
    return terms


def load_lr_cache_findings(cache_path: Path) -> list[dict]:
    """Extract unique finding names from unified LR cache."""
    if not cache_path.exists():
        return []
    with open(cache_path, encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data.get("entries", data)
    seen = set()
    findings = []
    for entry in entries.values():
        name = entry.get("finding", "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            findings.append({
                "text": name,
                "hpo_id": entry.get("hpo_id", ""),
                "is_synonym": False,
                "source": "lr_cache",
            })
    return findings


def main():
    # Load terms
    hpo_terms = load_hpo_terms(DATA_DIR / "hp.obo")
    logger.info("HPO terms loaded: %d (names + synonyms)", len(hpo_terms))
    
    lr_findings = load_lr_cache_findings(DATA_DIR / "unified_symptom_disease_cache.json")
    logger.info("LR cache unique findings: %d", len(lr_findings))
    
    # Deduplicate by text (case-insensitive)
    seen = set()
    all_terms = []
    for t in hpo_terms + lr_findings:
        key = t["text"].lower()
        if key not in seen:
            seen.add(key)
            all_terms.append(t)
    
    logger.info("Total unique terms to encode: %d", len(all_terms))
    
    # Encode
    logger.info("Loading sentence-transformers model...")
    local_model = Path("/data2/wanghongyi/models/all-MiniLM-L6-v2")
    model_name = str(local_model) if local_model.exists() else "sentence-transformers/all-MiniLM-L6-v2"
    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
            if free_mb >= 512:
                device = "cuda"
            else:
                logger.info("GPU free memory %.0f MB < 512 MB, using CPU", free_mb)
    except Exception:
        pass
    model = SentenceTransformer(model_name, device=device)
    logger.info("Encoding device: %s", device)
    
    texts = [t["text"] for t in all_terms]
    logger.info("Encoding %d terms...", len(texts))
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=512, normalize_embeddings=True)
    
    # Save
    emb_path = DATA_DIR / "hpo_embeddings.npy"
    meta_path = DATA_DIR / "hpo_embedding_metadata.json"
    
    np.save(emb_path, embeddings)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(all_terms, f, ensure_ascii=False)
    
    logger.info("Saved embeddings: %s (shape=%s, %.1f MB)", 
                emb_path, embeddings.shape, emb_path.stat().st_size / 1024 / 1024)
    logger.info("Saved metadata: %s (%d entries)", meta_path, len(all_terms))


if __name__ == "__main__":
    main()

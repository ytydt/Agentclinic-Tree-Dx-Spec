"""Knowledge layer modules for external knowledge integration.

Layer 0: DiagnosticMarkerIndex (pathognomonic signs + diagnostic criteria + gene-disease links)
Layer 0b: DxS DiagRL-Corpus discriminator index (flat phenotype set differences)
Layer 1: PrimeKG knowledge graph (HPO-based disease-phenotype + disease-disease + phenotype-phenotype + gene-disease)
Layer 2: LR Cache (unified multi-source: GetTheDiagnosis + HPO + Orphadata + HealthKG + BODHI-S + docLogica)
Layer 3: RAG fallback
  3a. StatPearls/Textbooks FAISS vector search (RAGRetriever)
  3b. PubMed E-utilities live search (PubMedRetriever)
  3c. LLM ChainDiscoverer (indirect reasoning chain generation)
Bridge: DiseaseNameResolver (UMLS CUI + fuzzy matching across heterogeneous source keys)
Pre-process: FindingNormalizer (numeric lab values → HPO phenotype terms)
"""

from .disease_name_resolver import DiseaseNameResolver
from .diagnostic_marker_index import DiagnosticMarkerIndex
from .finding_normalizer import FindingNormalizer
from .hpo_index import HPOIndex
from .dx_discriminator_index import DxDiscriminatorIndex
from .embedding_index import EmbeddingIndex
from .evidence_matcher import EvidenceMatcher
from .lr_retriever import LRRetriever
from .primekg_index import PrimeKGIndex
from .dx_feature_retriever import DxFeatureRetriever
from .rag_retriever import RAGRetriever
from .pubmed_retriever import PubMedRetriever

__all__ = [
    "DiseaseNameResolver",
    "DiagnosticMarkerIndex",
    "DxDiscriminatorIndex",
    "EmbeddingIndex",
    "EvidenceMatcher",
    "LRRetriever",
    "PrimeKGIndex",
    "DxFeatureRetriever",
    "RAGRetriever",
    "PubMedRetriever",
    "FindingNormalizer",
    "HPOIndex",
]

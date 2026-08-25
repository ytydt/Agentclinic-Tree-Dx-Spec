"""MedEinst / ECR-Agent implementation (arxiv 2601.06636)."""

from src.evaluate import bias_trap_rate, robust_accuracy, baseline_accuracy
from src.loss import evidence_score
from src.model import ECRAgent, ModelConfig

__all__ = [
    "ECRAgent",
    "ModelConfig",
    "evidence_score",
    "baseline_accuracy",
    "robust_accuracy",
    "bias_trap_rate",
]

"""Conservative keyword sets used for relevance filtering (never for filling facts)."""

from __future__ import annotations

import re

from .text import normalize_name

AI_KEYWORDS: tuple[str, ...] = (
    "ai",
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "genai",
    "llm",
    "large language model",
    "foundation model",
    "gpt",
    "chatgpt",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "transformer",
    "neural network",
    "computer vision",
    "nlp",
    "natural language processing",
    "speech recognition",
    "text to speech",
    "diffusion model",
    "stable diffusion",
    "reinforcement learning",
    "rag",
    "retrieval augmented",
    "embeddings",
    "vector database",
    "mlops",
    "inference",
    "fine tuning",
    "fine-tuning",
    "agentic",
    "ai agent",
)

JOB_AI_KEYWORDS: tuple[str, ...] = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "genai",
    "llm",
    "large language model",
    "gpt",
    "openai",
    "nlp",
    "computer vision",
    "pytorch",
    "tensorflow",
    "mlops",
    "data scientist",
    "data science",
    "data engineer",
    "ai engineer",
    "ai developer",
    "ai researcher",
    "research scientist",
    "applied scientist",
    "prompt engineer",
    "ai",
    "ml",
)

ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Research", re.compile(r"\b(research|scientist|phd|postdoc)\b", re.I)),
    ("Data", re.compile(r"\b(data|analytics|analyst|bi)\b", re.I)),
    ("Product", re.compile(r"\b(product|program)\b", re.I)),
    ("Design", re.compile(r"\b(design|ux|ui)\b", re.I)),
    ("Sales", re.compile(r"\b(sales|account executive|business development)\b", re.I)),
    ("Marketing", re.compile(r"\b(marketing|growth|content|seo)\b", re.I)),
    ("Operations", re.compile(r"\b(operations|ops|support|people|hr)\b", re.I)),
    ("Engineering", re.compile(r"\b(engineer|developer|architect|sre|devops|full.?stack|backend|frontend)\b", re.I)),
)


def is_ai_related(text: str | None, keywords: tuple[str, ...] = AI_KEYWORDS) -> bool:
    if not text:
        return False
    haystack = f" {normalize_name(text)} "
    for keyword in keywords:
        needle = normalize_name(keyword)
        if needle and f" {needle} " in haystack:
            return True
    return False


def classify_role(title: str | None) -> str:
    if not title:
        return "Other"
    for family, pattern in ROLE_PATTERNS:
        if pattern.search(title):
            return family
    return "Other"

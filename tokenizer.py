#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: tokenizer.py (P2.1 Tokenizer Heuristic Calibration & BPE Alignment)
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chompress

Description:
Modular tokenizer interface for exact and heuristic LLM token measurement:
- TiktokenBackend: native OpenAI cl100k_base, o200k_base, p50k_base.
- HuggingFaceBackend: LLaMA, Mistral, Qwen via transformers/tokenizers.
- HeuristicBackend: high-fidelity BPE pre-tokenization alignment supporting:
  * Case-sensitive subword splitting (CamelCase, snake_case, leading spaces).
  * Atomic 1-token CJK ideograph mapping ([\u4e00-\u9fff]).
  * Natural alphabetic word retention up to 12 characters.
  * Indentation preservation and newline whitespace run grouping.
  * Sub-3-digit numeric grouping and long alphanumeric/hash chunking.
- Tokenizer calibration suite computing:
  error_pct = (abs(heuristic_tokens - real_tokens) * 100.0) / (real_tokens)
  mean_error_pct = (sum(i=1 to n, error_pct_i)) / (n)
  bar_D = (sum(i=1 to n, D_i)) / (n)
  s_D = sqrt((sum(i=1 to n, (D_i - bar_D) * (D_i - bar_D))) / (n - 1))
  CI_95%(bar_D) = [bar_D - ((1.96 * s_D) / (sqrt(n))), bar_D + ((1.96 * s_D) / (sqrt(n)))]

Mathematical token model (pure ASCII notation):
ratio = (heuristic_tokens) / (real_tokens)
error_pct = (abs(heuristic_tokens - real_tokens) * 100.0) / (real_tokens)
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

# High-fidelity BPE pre-tokenization regex aligned with cl100k_base and o200k_base rules.
# Matches:
# 1. Contractions: 's, 't, 're, 've, 'm, 'll, 'd (case-insensitive)
# 2. CJK Unified Ideographs: [\u4e00-\u9fff] (strictly 1 token each in cl100k, o200k, LLaMA)
# 3. Newlines with optional indentation: \r?\n[ \t]*
# 4. Words with optional leading space: CamelCase, lowercase runs, uppercase acronyms
# 5. Numbers up to 3 digits with optional leading space: ?[0-9]{1,3}
# 6. Runs of spaces up to 4: [ ]{1,4}
# 7. Underscores and punctuation with optional leading space: _+, ?[^\s\w]+
# 8. Remaining whitespace sequences: \s+
HEURISTIC_BPE_PATTERN = re.compile(
    r"""'(?i:[sStTmMdD]|ll|LL|ve|VE|re|RE)|"""
    r"""[\u4e00-\u9fff]|"""
    r"""\r?\n[ \t]*|"""
    r""" ?[A-Z]+(?![a-z0-9_])|"""
    r""" ?[A-Z][a-z]+|"""
    r""" ?[a-z]+|"""
    r""" ?[0-9]{1,3}|"""
    r"""[ ]{1,4}|"""
    r"""\t+|"""
    r"""_+|"""
    r""" ?[^\s\w]+|"""
    r"""\s+"""
)


class BaseTokenizer:
    """Abstract interface for token counters."""

    name: str = "base"

    def count(self, text: str) -> int:
        raise NotImplementedError

    def count_batch(self, texts: List[str]) -> List[int]:
        return [self.count(t) for t in texts]


class TiktokenBackend(BaseTokenizer):
    """Native tiktoken backend supporting cl100k_base, o200k_base, p50k_base."""

    def __init__(self, encoding_name: str = "cl100k_base"):
        import tiktoken

        self.name = f"tiktoken:{encoding_name}"
        self.encoding_name = encoding_name
        self.enc = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self.enc.encode(text, disallowed_special=()))


class HuggingFaceBackend(BaseTokenizer):
    """
    HuggingFace AutoTokenizer backend for open models (e.g. meta-llama/Llama-3, Qwen).
    Requires transformers package.
    """

    def __init__(self, pretrained_model_name_or_path: str):
        from transformers import AutoTokenizer

        self.name = f"hf:{pretrained_model_name_or_path}"
        self.tokenizer = AutoTokenizer.from_pretrained(
            pretrained_model_name_or_path, trust_remote_code=True
        )

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self.tokenizer.encode(text, add_special_tokens=False))


class HeuristicBackend(BaseTokenizer):
    """
    Zero-dependency standard library tokenizer aligned with BPE pre-tokenization rules.
    Splits on subwords, leading space boundaries, indentation, and atomic CJK ideographs.
    Differentiates natural alphabetic vocabulary from alphanumeric hashes and base64 payloads.
    Provides high-speed approximation within ~5% of real BPE tokenizers.
    """

    def __init__(self, name: str = "heuristic"):
        self.name = name
        self._re = HEURISTIC_BPE_PATTERN

    def count(self, text: str) -> int:
        if not text:
            return 0
        token_count = 0
        for match in self._re.finditer(text):
            tok = match.group(0)
            clean_tok = tok.lstrip(" ")
            length = len(clean_tok)

            # Atomic CJK characters ([\u4e00-\u9fff]) are strictly 1 token each
            if length == 1 and ord(clean_tok[0]) >= 0x4E00:
                token_count += 1
            # Pure alphabetic English words up to 12 chars are single BPE tokens
            elif clean_tok.isalpha():
                if length > 12:
                    token_count += (length + 5) // 6
                else:
                    token_count += 1
            # Alphanumeric tokens containing digits (hashes, base64, identifiers)
            elif clean_tok.isalnum():
                if length > 4:
                    token_count += (length + 3) // 4
                else:
                    token_count += 1
            # Punctuation, symbols, whitespace runs
            else:
                token_count += 1

        return max(1, token_count) if text else 0


def get_tokenizer(target: Optional[str] = None) -> BaseTokenizer:
    """
    Factory function returning the appropriate tokenizer backend.
    - 'cl100k_base', 'o200k_base': TiktokenBackend (if tiktoken is installed)
    - 'hf:<model_id>': HuggingFaceBackend (if transformers is installed)
    - 'heuristic' or None: HeuristicBackend fallback
    """
    target_str = (target or "auto").strip()

    if target_str in ("auto", "cl100k_base", "o200k_base"):
        try:
            import tiktoken

            enc = "cl100k_base" if target_str == "auto" else target_str
            return TiktokenBackend(enc)
        except ImportError:
            if target_str != "auto":
                raise ImportError(
                    f"Requested tokenizer '{target_str}' requires 'pip install tiktoken'"
                )

    if target_str.startswith("hf:"):
        model_name = target_str[3:]
        try:
            return HuggingFaceBackend(model_name)
        except ImportError:
            raise ImportError(
                "Requested HuggingFace tokenizer requires 'pip install transformers'"
            )

    return HeuristicBackend("heuristic")


def benchmark_tokenizer_ratio(
    real_tokenizer: BaseTokenizer,
    heuristic_tokenizer: BaseTokenizer,
    sample_text: str,
) -> Tuple[int, int, float]:
    """
    Measures empirical ratio = (heuristic_tokens) / (real_tokens) on representative text.
    Returns (real_tokens, heuristic_tokens, ratio).
    """
    real_count = real_tokenizer.count(sample_text)
    heuristic_count = heuristic_tokenizer.count(sample_text)
    ratio = ((heuristic_count) / (real_count)) if real_count > 0 else 1.0
    return real_count, heuristic_count, round(ratio, 4)


def calibrate_tokenizer_suite(
    real_tokenizer: BaseTokenizer,
    heuristic_tokenizer: BaseTokenizer,
    corpus_samples: List[str],
) -> Dict[str, Any]:
    """
    Evaluates heuristic alignment against a real BPE tokenizer across corpus samples.
    Computes:
      error_pct_i = (abs(tok_heur_i - tok_real_i) * 100.0) / (tok_real_i)
      mean_error_pct = (sum(i=1 to n, error_pct_i)) / (n)
      bar_D = (sum(i=1 to n, D_i)) / (n)
      s_D = sqrt((sum(i=1 to n, (D_i - bar_D) * (D_i - bar_D))) / (n - 1))
      CI_95%(bar_D) = [bar_D - ((1.96 * s_D) / (sqrt(n))), bar_D + ((1.96 * s_D) / (sqrt(n)))]
    """
    n = len(corpus_samples)
    if n == 0:
        return {
            "samples": 0,
            "mean_error_pct": 0.0,
            "mean_ratio": 1.0,
            "ci_95_diff": [0.0, 0.0],
        }

    real_counts: List[int] = []
    heur_counts: List[int] = []
    errors_pct: List[float] = []
    diffs: List[int] = []
    ratios: List[float] = []

    for text in corpus_samples:
        r_c = real_tokenizer.count(text)
        h_c = heuristic_tokenizer.count(text)
        real_counts.append(r_c)
        heur_counts.append(h_c)

        diff = h_c - r_c
        diffs.append(diff)

        err = ((abs(diff)) * 100.0) / (r_c) if r_c > 0 else 0.0
        errors_pct.append(err)

        rat = ((h_c) / (r_c)) if r_c > 0 else 1.0
        ratios.append(rat)

    mean_err = (sum(errors_pct)) / (n)
    mean_rat = (sum(ratios)) / (n)
    bar_D = (sum(diffs)) / (float(n))

    if n > 1:
        variance_D = (sum((d - bar_D) * (d - bar_D) for d in diffs)) / (float(n - 1))
        s_D = math.sqrt(variance_D)
        margin = (1.96 * s_D) / (math.sqrt(n))
        ci_95 = [round(bar_D - margin, 3), round(bar_D + margin, 3)]
    else:
        ci_95 = [round(bar_D, 3), round(bar_D, 3)]

    total_real = sum(real_counts)
    total_heur = sum(heur_counts)
    aggregate_error_pct = (
        ((abs(total_heur - total_real)) * 100.0) / (total_real)
        if total_real > 0
        else 0.0
    )

    return {
        "samples": n,
        "total_real_tokens": total_real,
        "total_heuristic_tokens": total_heur,
        "aggregate_error_pct": round(aggregate_error_pct, 2),
        "mean_sample_error_pct": round(mean_err, 2),
        "mean_ratio": round(mean_rat, 4),
        "mean_diff_tokens": round(bar_D, 2),
        "ci_95_diff": ci_95,
    }

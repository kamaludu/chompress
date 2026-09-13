#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: placeholders.py (P2.3 Alphabet Optimizer & Multi-Range Generator)
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Tokenizer-aware placeholder alphabet optimizer and generator:
- Discovers and calibrates candidate alphabets targeting strictly 1 token per reference.
- Dynamic corpus filtering: excludes any symbol present in the original input files.
- Huffman-like frequency weighting: assigns cheapest symbols (1 token) to highest-frequency patterns.
- Two-tier alphabet scaling:
  Tier 1: Atomic 1-token symbols (over 2,500 collision-free CJK ideographs and symbols).
  Tier 2: Asymmetric prefix symbols (^1, ^2, ...) at 2 tokens if replacements exceed Tier 1.
- P2.3 Multi-Range & Hybrid Protocol Metadata:
  * Contiguous range detection: allows protocol headers in ~8 tokens.
  * Multi-range detection for corpus gaps: cjk_ranges="19968-20050,20060-20500".
  * Hybrid CJK + Prefix spillover: single header coordinating Tier 1 and Tier 2.
- Finalization: reconciles alphabet on the exact subset of replacements actually selected.

Mathematical token model (pure ASCII notation):
cost_total = sum(i=1 to M, freq_i * tokens(symbol_i))
avg_tokens = (sum(i=1 to K, tokens(ph_i))) / (K)
net_token_gain_i = freq_i * (tokens_original_i - tokens_placeholder_i) - marginal_mapping_cost_i
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import tokenizer

# Base range of CJK Unified Ideographs (each character is strictly 1 token in cl100k, o200k, LLaMA 3)
CJK_BASE_CODEPOINT = 0x4E00  # Character '一' (19968)
CJK_POOL_SIZE = 2500        # Expanded pool for Tier 1 atomic single-token placeholders


class PlaceholderEngine:
    """
    Manages placeholder generation, alphabet discovery, dynamic corpus filtering,
    frequency-weighted symbol allocation, and BPE cost calibration.
    """

    STYLES: Dict[str, Dict[str, str]] = {
        "single_token": {
            "sub": "{:s}",
            "blk": "{:s}",
            "wrd": "{:s}",
            "regex": r"[\u4e00-\u9fff]",
            "desc": "Atomic 1-token symbols (CJK Unified Ideographs, zero bracket overhead)",
        },
        "prefix_compact": {
            "sub": "^{:d}",
            "blk": "^{:d}",
            "wrd": "^w{:d}",
            "regex": r"\^w?\d+",
            "desc": "Compact asymmetric prefix (^1, ^2) at strictly 2 tokens",
        },
        "guillemet": {
            "sub": "«{:d}»",
            "blk": "«{:d}»",
            "wrd": "«w{:d}»",
            "regex": r"«w?\d+»",
            "desc": "Compact French quotes («1», «2») at 3 tokens",
        },
        "classic": {
            "sub": "__s{:d}__",
            "blk": "__b{:d}__",
            "wrd": "__w{:d}__",
            "regex": r"__[sbw]\d+__",
            "desc": "Baseline verbose delimiters (__s1__, __b1__) at 4 tokens",
        },
        "section": {
            "sub": "§{:d}§",
            "blk": "§{:d}§",
            "wrd": "§w{:d}§",
            "regex": r"§w?\d+§",
            "desc": "Section delimiters (§1§, §2§) at 3 tokens",
        },
        "bracket": {
            "sub": "⟦{:d}⟧",
            "blk": "⟦{:d}⟧",
            "wrd": "⟦w{:d}⟧",
            "regex": r"⟦w?\d+⟧",
            "desc": "Mathematical bracket delimiters (⟦1⟧, ⟦2⟧) at 3 tokens",
        },
        "ascii_compact": {
            "sub": "~{:d}~",
            "blk": "~{:d}~",
            "wrd": "~w{:d}~",
            "regex": r"~w?\d+~",
            "desc": "Compact symmetric ASCII (~1~, ~2~) at 3 tokens",
        },
    }

    def __init__(
        self,
        style_name: str = "auto",
        tok: Optional[tokenizer.BaseTokenizer] = None,
    ):
        self.tok: tokenizer.BaseTokenizer = tok or tokenizer.get_tokenizer("heuristic")
        self.requested_style: str = (style_name or "auto").strip().lower()
        self.style_name: str = "single_token"
        self.cfg: Dict[str, str] = self.STYLES["single_token"]

        # Dynamic allocated alphabet state
        self.active_alphabet: List[str] = []
        self.used_corpus_chars: Set[str] = set()
        self.is_contiguous_cjk: bool = False
        self.is_multi_range_cjk: bool = False
        self.is_hybrid: bool = False
        self.cjk_ranges: List[Tuple[int, int]] = []
        self.cjk_start_cp: int = CJK_BASE_CODEPOINT
        self.prefix_char: str = "^"

        if self.requested_style != "auto" and self.requested_style in self.STYLES:
            self.style_name = self.requested_style
            self.cfg = self.STYLES[self.requested_style]

    @classmethod
    def list_styles(cls) -> List[Tuple[str, str]]:
        """Returns list of (style_name, description)."""
        return [(k, v["desc"]) for k, v in cls.STYLES.items()]

    def _extract_ranges(self, cps: List[int]) -> List[Tuple[int, int]]:
        """Groups a sorted list of codepoints into contiguous [start, end] ranges."""
        if not cps:
            return []
        ranges: List[Tuple[int, int]] = []
        cur_start = cps[0]
        cur_end = cps[0]
        for cp in cps[1:]:
            if cp == cur_end + 1:
                cur_end = cp
            else:
                ranges.append((cur_start, cur_end))
                cur_start = cp
                cur_end = cp
        ranges.append((cur_start, cur_end))
        return ranges

    def auto_calibrate(self, raw_corpus: str = "", sample_size: int = 30) -> str:
        """
        Evaluates candidate styles against the active tokenizer and corpus.
        Prioritizes single-token atomic symbols if corpus has no conflicting characters.
        Falls back to prefix_compact (^1) or guillemet if single_token is unsuitable.
        """
        self.used_corpus_chars = set(raw_corpus)
        self.prefix_char = "^" if "^" not in self.used_corpus_chars else "~"

        if self.requested_style != "auto" and self.requested_style in self.STYLES:
            self.style_name = self.requested_style
            self.cfg = self.STYLES[self.requested_style]
            if self.style_name == "prefix_compact":
                self.cfg["sub"] = f"{self.prefix_char}{{:d}}"
                self.cfg["blk"] = f"{self.prefix_char}{{:d}}"
                self.cfg["wrd"] = f"{self.prefix_char}w{{:d}}"
            return self.style_name

        # Test single-token viability: verify first 100 candidate symbols are absent from corpus
        cjk_available = sum(
            1 for cp in range(CJK_BASE_CODEPOINT, CJK_BASE_CODEPOINT + 100)
            if chr(cp) not in self.used_corpus_chars
        )

        if cjk_available >= 90:
            self.style_name = "single_token"
            self.cfg = self.STYLES["single_token"]
            return self.style_name

        # If single-token CJK collided with corpus, evaluate remaining styles
        candidates_ranked: List[Tuple[float, str]] = []
        for name in ["prefix_compact", "guillemet", "ascii_compact", "classic"]:
            cfg = self.STYLES[name]
            sample_prefix = self.prefix_char if name == "prefix_compact" else None
            sample_sub_fmt = f"{sample_prefix}{{:d}}" if sample_prefix else cfg["sub"]
            sample_sub_1 = sample_sub_fmt.format(1)
            if sample_sub_1 in raw_corpus:
                continue

            total_tokens = sum(
                self.tok.count(sample_sub_fmt.format(i)) for i in range(1, sample_size + 1)
            )
            avg_tokens = (total_tokens) / (float(sample_size))
            candidates_ranked.append((avg_tokens, name))

        if candidates_ranked:
            candidates_ranked.sort(key=lambda x: (x[0], x[1]))
            best_style = candidates_ranked[0][1]
        else:
            best_style = "prefix_compact"

        self.style_name = best_style
        self.cfg = dict(self.STYLES[best_style])
        if best_style == "prefix_compact":
            self.cfg["sub"] = f"{self.prefix_char}{{:d}}"
            self.cfg["blk"] = f"{self.prefix_char}{{:d}}"
            self.cfg["wrd"] = f"{self.prefix_char}w{{:d}}"

        return self.style_name

    def build_alphabet(
        self,
        raw_corpus: str,
        required_count: int,
        candidate_frequencies: Optional[List[int]] = None,
    ) -> List[str]:
        """
        Constructs the initial placeholder sequence for required_count replacements.
        - Filters out all characters already present in raw_corpus.
        - Fills Tier 1 (1-token atomic CJK symbols) first.
        - Spills over into Tier 2 (asymmetric prefix ^1, ^2, ...) if required_count > Tier 1 capacity.
        - Detects contiguous and multi-range slices for compact header serialization.
        """
        self.used_corpus_chars = set(raw_corpus)
        self.prefix_char = "^" if "^" not in self.used_corpus_chars else "~"
        alphabet: List[str] = []

        if self.style_name == "single_token":
            tier1_symbols: List[str] = []
            cp = CJK_BASE_CODEPOINT
            max_cp = CJK_BASE_CODEPOINT + CJK_POOL_SIZE

            while cp < max_cp and len(tier1_symbols) < required_count:
                char = chr(cp)
                if char not in self.used_corpus_chars:
                    tier1_symbols.append(char)
                cp += 1

            cps = [ord(ch) for ch in tier1_symbols]
            ranges = self._extract_ranges(cps)
            self.cjk_ranges = ranges

            if len(ranges) == 1:
                self.is_contiguous_cjk = True
                self.is_multi_range_cjk = False
                self.cjk_start_cp = ranges[0][0]
            elif len(ranges) > 1:
                self.is_contiguous_cjk = False
                self.is_multi_range_cjk = True
            else:
                self.is_contiguous_cjk = False
                self.is_multi_range_cjk = False

            alphabet.extend(tier1_symbols)

            # Tier 2 spillover if replacements exceed Tier 1 pool
            if len(alphabet) < required_count:
                spillover_needed = required_count - len(alphabet)
                for i in range(1, spillover_needed + 1):
                    alphabet.append(f"{self.prefix_char}{i}")
                self.is_hybrid = True
            else:
                self.is_hybrid = False

        elif self.style_name == "prefix_compact":
            alphabet = [f"{self.prefix_char}{i}" for i in range(1, required_count + 1)]
            self.is_contiguous_cjk = False
            self.is_multi_range_cjk = False
            self.is_hybrid = False

        else:
            fmt = self.cfg["sub"]
            alphabet = [fmt.format(i) for i in range(1, required_count + 1)]
            self.is_contiguous_cjk = False
            self.is_multi_range_cjk = False
            self.is_hybrid = False

        self.active_alphabet = alphabet
        return alphabet

    def finalize_used_alphabet(self, used_placeholders: List[str]) -> None:
        """
        Trims active alphabet to the exact list of placeholders selected for actual replacement.
        Recomputes contiguous, multi-range, and hybrid states for protocol header serialization.
        """
        if not used_placeholders:
            self.active_alphabet = []
            self.is_contiguous_cjk = False
            self.is_multi_range_cjk = False
            self.is_hybrid = False
            self.cjk_ranges = []
            return

        self.active_alphabet = list(used_placeholders)

        cjk_tokens = [s for s in self.active_alphabet if len(s) == 1 and ord(s) >= 0x4E00]
        pref_tokens = [
            s
            for s in self.active_alphabet
            if len(s) > 1 and s[0] in ("^", "~") and s[1:].isdigit()
        ]

        if cjk_tokens and pref_tokens and (len(cjk_tokens) + len(pref_tokens)) == len(self.active_alphabet):
            self.is_hybrid = True
            self.is_contiguous_cjk = False
            self.cjk_ranges = self._extract_ranges([ord(s) for s in cjk_tokens])
            self.is_multi_range_cjk = len(self.cjk_ranges) > 1
        elif len(cjk_tokens) == len(self.active_alphabet):
            self.is_hybrid = False
            self.cjk_ranges = self._extract_ranges([ord(s) for s in cjk_tokens])
            if len(self.cjk_ranges) == 1:
                self.is_contiguous_cjk = True
                self.is_multi_range_cjk = False
                self.cjk_start_cp = self.cjk_ranges[0][0]
            else:
                self.is_contiguous_cjk = False
                self.is_multi_range_cjk = True
        else:
            self.is_hybrid = False
            self.is_contiguous_cjk = False
            self.is_multi_range_cjk = False
            self.cjk_ranges = []

    def format_placeholder(self, c_type: str, index: int) -> str:
        """
        Returns placeholder for 1-based index.
        Uses allocated active_alphabet if available; otherwise falls back to algorithmic formatting.
        """
        if self.active_alphabet and 1 <= index <= len(self.active_alphabet):
            return self.active_alphabet[index - 1]

        if self.style_name == "single_token":
            return chr(CJK_BASE_CODEPOINT + (index - 1))
        elif self.style_name == "prefix_compact":
            return f"{self.prefix_char}{index}"
        else:
            fmt = self.cfg.get("sub", "«{:d}»")
            return fmt.format(index)

    def get_protocol_meta(self) -> Dict[str, Any]:
        """
        Returns metadata describing the active alphabet for positional mapping headers.
        Supports contiguous CJK, multi-range CJK, hybrid CJK+prefix, prefix, and template sequences.
        """
        if not self.active_alphabet:
            return {"type": "default", "style": self.style_name}

        if self.is_contiguous_cjk:
            return {
                "type": "cjk_contiguous",
                "start_cp": self.cjk_start_cp,
                "start_char": chr(self.cjk_start_cp),
                "count": len(self.active_alphabet),
            }

        if self.is_multi_range_cjk and not self.is_hybrid:
            return {
                "type": "cjk_multi_range",
                "ranges": self.cjk_ranges,
                "count": len(self.active_alphabet),
            }

        if self.is_hybrid:
            cjk_tokens = [s for s in self.active_alphabet if len(s) == 1 and ord(s) >= 0x4E00]
            pref_tokens = [
                s
                for s in self.active_alphabet
                if len(s) > 1 and s[0] in ("^", "~") and s[1:].isdigit()
            ]
            p_start = int(pref_tokens[0][1:]) if pref_tokens else 1
            return {
                "type": "hybrid_cjk_prefix",
                "cjk_ranges": self.cjk_ranges,
                "cjk_count": len(cjk_tokens),
                "prefix": self.prefix_char,
                "p_start": p_start,
                "p_count": len(pref_tokens),
                "count": len(self.active_alphabet),
            }

        if self.style_name == "prefix_compact" or (
            self.active_alphabet and self.active_alphabet[0].startswith(self.prefix_char)
        ):
            return {
                "type": "prefix_sequence",
                "prefix": self.prefix_char,
                "start": 1,
                "count": len(self.active_alphabet),
            }

        fmt = self.cfg.get("sub", "")
        if "{:d}" in fmt:
            return {
                "type": "template_sequence",
                "template": fmt,
                "start": 1,
                "count": len(self.active_alphabet),
            }

        # Explicit alphabet string fallback
        return {
            "type": "explicit_alphabet",
            "alphabet": "".join(self.active_alphabet),
            "count": len(self.active_alphabet),
        }

    def get_regex(self) -> re.Pattern:
        """
        Returns compiled regex pattern matching all allocated active placeholders
        or any placeholder matching the active style definition.
        """
        patterns: List[str] = []
        if self.active_alphabet:
            escaped = [re.escape(s) for s in sorted(self.active_alphabet, key=len, reverse=True)]
            patterns.append("|".join(escaped))

        patterns.append(self.cfg["regex"])
        # Universal fallback regex covering full CJK ideographs range
        patterns.append(r"__[sbw]\d+__|«w?\d+»|\^w?\d+|~w?\d+~|§w?\d+§|⟦w?\d+⟧|[\u4e00-\u9fff]")
        return re.compile("|".join(patterns))

    def get_token_cost(self, c_type: str, index: int) -> int:
        """Computes exact token cost of the placeholder using active tokenizer."""
        ph = self.format_placeholder(c_type, index)
        return self.tok.count(ph)

    def measure_style_economy(
        self, style_name: str, count: int = 50
    ) -> Dict[str, Any]:
        """
        Empirical measurement utility comparing a specific style's token usage.
        Calculates:
            total_tokens = sum(i=1 to count, tok.count(ph_i))
            avg_tokens = (total_tokens) / (count)
        """
        if style_name not in self.STYLES:
            raise ValueError(f"Unknown placeholder style: {style_name}")

        cfg = self.STYLES[style_name]
        tokens_list = []
        for i in range(1, count + 1):
            if style_name == "single_token":
                ph = chr(CJK_BASE_CODEPOINT + (i - 1))
            else:
                ph = cfg["sub"].format(i)
            tokens_list.append(self.tok.count(ph))

        total = sum(tokens_list)
        return {
            "style": style_name,
            "count": count,
            "total_tokens": total,
            "avg_tokens": round((total) / (float(count)), 3),
            "min_tokens": min(tokens_list),
            "max_tokens": max(tokens_list),
        }

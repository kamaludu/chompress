#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: mapping.py (P2.3 Protocol Header Multi-Range Support & 1-Token Compact Sentinel)
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chompress

Description:
High-efficiency, tokenizer-aware mapping serialization engines.
Supports:
1. Positional: Zero-key indexed array with ultra-compact protocol headers (~8 to ~28 tokens):
   - Ultra-compact 1-token sentinel delimiter ("§", "¶", "‡") saving ~3-4 tokens per replacement entry.
   - Contiguous CJK range headers: [MAP:INDEXED cjk_start=19968 count=N]
   - P2.3 Multi-Range CJK headers: [MAP:INDEXED cjk_ranges="19968-20050,20060-20500" count=N]
   - P2.3 Hybrid CJK + Prefix spillover: [MAP:INDEXED cjk_ranges="..." prefix='^' p_start=1 p_count=M]
   - Prefix sequence headers: [MAP:INDEXED prefix='^' start=1 count=N]
   - Template sequence headers: [MAP:INDEXED seq='«{:d}»' start=1 count=N]
   - Automatic local sequence detection strictly scoped to the keys being serialized.
2. Delimited: Sentinel-separated raw blocks preserving literal newlines and quotes.
3. Key-Value: Compact single-line records with newline marker.
4. JSON: Baseline standard JSON with escaping and key redundancy.

Mathematical token model (pure ASCII notation):
net_tokens_saved = original_tokens - (compressed_tokens + mapping_tokens + protocol_tokens)
net_ratio = (net_tokens_saved) / (original_tokens)
marginal_entry_cost = tokens(entry_representation) + tokens(delimiter)
"""

import ast
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import tokenizer


def natural_sort_key(s: str) -> List[Any]:
    """
    Sorts strings containing numbers in natural numeric order (1, 2, ..., 10),
    or by Unicode codepoint order for single-character symbols.
    """
    parts = re.split(r"(\d+)", s)
    return [int(text) if text.isdigit() else text for text in parts]


def positional_sort_key(k: str) -> Tuple[int, Any, int]:
    """
    Multi-tier sort key for positional mapping:
    - Tier 0: Single CJK characters (ord >= 0x4E00), sorted by codepoint.
    - Tier 1: Compact prefix tokens (e.g. ^1, ^2 or ~1, ~2), sorted numerically.
    - Tier 2: Other single-character symbols, sorted by codepoint.
    - Tier 3: General strings / templates, sorted by natural numeric order.
    """
    if len(k) == 1 and ord(k) >= 0x4E00:
        return (0, "", ord(k))
    m_pref = re.match(r"^([^0-9]+)(\d+)$", k)
    if m_pref:
        pref, num_str = m_pref.groups()
        return (1, pref, int(num_str))
    if len(k) == 1:
        return (2, "", ord(k))
    return (3, natural_sort_key(k), 0)


class BaseMappingSerializer:
    """Abstract base class for dictionary serializers."""

    name: str = "base"

    def serialize(
        self,
        mapping: Dict[str, str],
        raw_corpus: str = "",
        ph_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Serializes mapping into (payload_text, protocol_header).
        Returns raw text ready for LLM consumption and exact reconstruction.
        """
        raise NotImplementedError

    def deserialize(self, payload: str, protocol_meta: str = "") -> Dict[str, str]:
        """
        Reconstructs exact dictionary mapping {placeholder: content}
        guaranteeing: deserialize(serialize(M)) == M.
        """
        raise NotImplementedError

    def estimate_entry_tokens(
        self, placeholder: str, content: str, tok: tokenizer.BaseTokenizer
    ) -> int:
        """
        Computes marginal token cost of adding one replacement entry to this format.
        """
        raise NotImplementedError


class JSONMappingSerializer(BaseMappingSerializer):
    """
    Standard JSON mapping serializer (baseline reference).
    Incurs escaping penalties on newlines and quotes.
    """

    name: str = "json"

    def serialize(
        self,
        mapping: Dict[str, str],
        raw_corpus: str = "",
        ph_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        if not mapping:
            return "{}", "[MAP:JSON]"
        payload = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
        header = "[MAP:JSON]"
        return payload, header

    def deserialize(self, payload: str, protocol_meta: str = "") -> Dict[str, str]:
        text = payload.strip()
        if not text or text == "{}":
            return {}
        return json.loads(text)

    def estimate_entry_tokens(
        self, placeholder: str, content: str, tok: tokenizer.BaseTokenizer
    ) -> int:
        sample = f'"{placeholder}":{json.dumps(content)},'
        return tok.count(sample)


class DelimitedMappingSerializer(BaseMappingSerializer):
    """
    Delimited mapping: entries are separated by a collision-free sentinel string.
    Zero JSON escaping: preserves raw newlines and quotes intact.
    """

    name: str = "delimited"
    DEFAULT_SENTINEL: str = "\n---§---\n"

    def _get_safe_sentinel(self, raw_corpus: str, values: List[str]) -> str:
        sentinel = self.DEFAULT_SENTINEL
        all_text = raw_corpus + "".join(values)
        while sentinel.strip() in all_text:
            suffix = hashlib.sha256(sentinel.encode("utf-8")).hexdigest()[:4]
            sentinel = "\n---§" + suffix + "---\n"
        return sentinel

    def serialize(
        self,
        mapping: Dict[str, str],
        raw_corpus: str = "",
        ph_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        if not mapping:
            return "", "[MAP:DELIMITED]"
        sentinel = self._get_safe_sentinel(raw_corpus, list(mapping.values()))
        parts: List[str] = []
        sorted_keys = sorted(mapping.keys(), key=natural_sort_key)
        for ph in sorted_keys:
            parts.append(f"{ph}\n{mapping[ph]}")
        payload = sentinel.join(parts)
        header = f"[MAP:DELIMITED sentinel={repr(sentinel)}]"
        return payload, header

    def deserialize(self, payload: str, protocol_meta: str = "") -> Dict[str, str]:
        if not payload:
            return {}
        sentinel = self.DEFAULT_SENTINEL
        if "sentinel=" in protocol_meta:
            m = re.search(r"sentinel=(['\"])(.*?)\1", protocol_meta, re.DOTALL)
            if m:
                try:
                    sentinel = ast.literal_eval(m.group(0).split("=", 1)[1])
                except Exception:
                    sentinel = m.group(2)

        blocks = payload.split(sentinel)
        result: Dict[str, str] = {}
        for b in blocks:
            if not b:
                continue
            lines = b.split("\n", 1)
            ph = lines[0].strip()
            content = lines[1] if len(lines) > 1 else ""
            if ph:
                result[ph] = content
        return result

    def estimate_entry_tokens(
        self, placeholder: str, content: str, tok: tokenizer.BaseTokenizer
    ) -> int:
        return (
            tok.count(placeholder)
            + 1
            + tok.count(content)
            + tok.count(self.DEFAULT_SENTINEL)
        )


class PositionalMappingSerializer(BaseMappingSerializer):
    """
    Positional mapping: stores ONLY replacement values in indexed order.
    Zero tokens spent on placeholder keys in the body.
    Employs an ultra-compact 1-token sentinel delimiter to minimize dictionary overhead.
    Supports ultra-compact headers (~8 to ~28 tokens) for:
    - Contiguous CJK ideographs (cjk_start=19968 count=N)
    - P2.3 Multi-Range CJK (cjk_ranges="19968-20050,20060-20500" count=N)
    - P2.3 Hybrid CJK + Prefix (cjk_ranges="..." prefix='^' p_start=1 p_count=M)
    - Prefix sequences (prefix='^' start=1 count=N)
    - Template sequences (seq='«{:d}»' start=1 count=N)
    """

    name: str = "positional"
    DEFAULT_SENTINEL: str = "§"
    SENTINEL_CANDIDATES: Tuple[str, ...] = ("§", "¶", "‡", "†", "␞", "␟")

    def _get_safe_sentinel(self, raw_corpus: str, values: List[str]) -> str:
        """
        Selects a collision-free 1-token sentinel delimiter.
        Iterates through candidate symbols strictly absent from raw corpus and values.
        """
        all_text = raw_corpus + "".join(values)
        for cand in self.SENTINEL_CANDIDATES:
            if cand not in all_text:
                return cand

        # Fallback if all 1-character candidates collide (extremely rare)
        sentinel = "\n---§---\n"
        while sentinel in all_text:
            suffix = hashlib.sha256(sentinel.encode("utf-8")).hexdigest()[:4]
            sentinel = f"\n---§{suffix}---\n"
        return sentinel

    def _extract_cjk_ranges(self, cps: List[int]) -> List[Tuple[int, int]]:
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

    def _detect_sequence(self, keys: List[str]) -> Optional[Dict[str, Any]]:
        """
        Auto-detects continuous, multi-range, hybrid, or template sequences directly from keys:
        1. Contiguous or Multi-Range single CJK characters.
        2. Hybrid CJK + Prefix spillover sequences (Tier 1 CJK + Tier 2 ^1..^M).
        3. Arithmetic numeric prefix sequences (^1..^N or ~1..~N).
        4. Template sequences («1»..«N», ~1~..~N~, __s1__..__sN__).
        5. Explicit single-character alphabet string.
        """
        if not keys:
            return None

        # Check 1: All single characters (CJK Unified Ideographs or single symbols)
        if all(len(k) == 1 for k in keys):
            cps = [ord(k) for k in keys]
            ranges = self._extract_cjk_ranges(cps)
            if len(ranges) == 1:
                return {
                    "type": "cjk_contiguous",
                    "start_cp": ranges[0][0],
                    "count": ranges[0][1] - ranges[0][0] + 1,
                }
            elif len(ranges) > 1 and len(ranges) <= 25:
                return {
                    "type": "cjk_multi_range",
                    "ranges": ranges,
                    "count": len(cps),
                }

        # Check 2: Hybrid CJK + Prefix spillover sequence
        cjk_keys = [k for k in keys if len(k) == 1 and ord(k) >= 0x4E00]
        pref_keys = [
            k
            for k in keys
            if len(k) > 1 and k[0] in ("^", "~") and k[1:].isdigit()
        ]
        if (
            len(cjk_keys) > 0
            and len(pref_keys) > 0
            and (len(cjk_keys) + len(pref_keys)) == len(keys)
        ):
            cjk_cps = [ord(k) for k in cjk_keys]
            cjk_ranges = self._extract_cjk_ranges(cjk_cps)

            pref_char = pref_keys[0][0]
            start_num = int(pref_keys[0][1:])
            is_pref_arithmetic = True
            for offset, k in enumerate(pref_keys):
                if k != f"{pref_char}{start_num + offset}":
                    is_pref_arithmetic = False
                    break

            if is_pref_arithmetic:
                return {
                    "type": "hybrid_cjk_prefix",
                    "cjk_ranges": cjk_ranges,
                    "cjk_count": len(cjk_keys),
                    "prefix": pref_char,
                    "p_start": start_num,
                    "p_count": len(pref_keys),
                    "total_count": len(keys),
                }

        # Check 3: Arithmetic numeric prefix or template sequence (e.g. ^1..^N or «1»..«N»)
        m_first = re.match(r"^([^0-9]*)(\d+)([^0-9]*)$", keys[0])
        if m_first:
            prefix, start_str, suffix = m_first.groups()
            start_id = int(start_str)
            is_arithmetic = True
            for offset, k in enumerate(keys):
                expected = f"{prefix}{start_id + offset}{suffix}"
                if k != expected:
                    is_arithmetic = False
                    break

            if is_arithmetic:
                if suffix == "":
                    return {
                        "type": "prefix_sequence",
                        "prefix": prefix,
                        "start": start_id,
                        "count": len(keys),
                    }
                else:
                    return {
                        "type": "template_sequence",
                        "template": prefix + "{:d}" + suffix,
                        "start": start_id,
                        "count": len(keys),
                    }

        # Check 4: Non-contiguous single characters fallback
        if all(len(k) == 1 for k in keys):
            return {
                "type": "explicit_alphabet",
                "alphabet": "".join(keys),
                "count": len(keys),
            }

        return None

    def serialize(
        self,
        mapping: Dict[str, str],
        raw_corpus: str = "",
        ph_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        if not mapping:
            return "", "[MAP:INDEXED]"
        sentinel = self._get_safe_sentinel(raw_corpus, list(mapping.values()))
        sorted_keys = sorted(mapping.keys(), key=positional_sort_key)
        values = [mapping[k] for k in sorted_keys]
        payload = sentinel.join(values)

        # Detect sequence from the exact subset of keys being serialized
        detected = self._detect_sequence(sorted_keys)
        if detected:
            seq_info = detected
        elif ph_meta and ph_meta.get("type") and ph_meta.get("count") == len(sorted_keys):
            seq_info = ph_meta
        else:
            seq_info = None

        if seq_info and seq_info.get("type") == "cjk_contiguous":
            header = (
                f"[MAP:INDEXED sentinel={repr(sentinel)} "
                f"cjk_start={seq_info['start_cp']} count={seq_info['count']}]"
            )
        elif seq_info and seq_info.get("type") == "cjk_multi_range":
            ranges_str = ",".join(f"{s}-{e}" for s, e in seq_info["ranges"])
            header = (
                f"[MAP:INDEXED sentinel={repr(sentinel)} "
                f"cjk_ranges={repr(ranges_str)} count={seq_info['count']}]"
            )
        elif seq_info and seq_info.get("type") == "hybrid_cjk_prefix":
            ranges = seq_info["cjk_ranges"]
            if len(ranges) == 1:
                header = (
                    f"[MAP:INDEXED sentinel={repr(sentinel)} "
                    f"cjk_start={ranges[0][0]} cjk_count={seq_info['cjk_count']} "
                    f"prefix={repr(seq_info['prefix'])} p_start={seq_info['p_start']} "
                    f"p_count={seq_info['p_count']}]"
                )
            else:
                ranges_str = ",".join(f"{s}-{e}" for s, e in ranges)
                header = (
                    f"[MAP:INDEXED sentinel={repr(sentinel)} "
                    f"cjk_ranges={repr(ranges_str)} "
                    f"prefix={repr(seq_info['prefix'])} p_start={seq_info['p_start']} "
                    f"p_count={seq_info['p_count']}]"
                )
        elif seq_info and seq_info.get("type") == "prefix_sequence":
            header = (
                f"[MAP:INDEXED sentinel={repr(sentinel)} "
                f"prefix={repr(seq_info['prefix'])} start={seq_info['start']} count={seq_info['count']}]"
            )
        elif seq_info and seq_info.get("type") == "template_sequence":
            header = (
                f"[MAP:INDEXED sentinel={repr(sentinel)} "
                f"seq={repr(seq_info['template'])} start={seq_info['start']} count={seq_info['count']}]"
            )
        elif seq_info and seq_info.get("type") == "explicit_alphabet":
            header = (
                f"[MAP:INDEXED sentinel={repr(sentinel)} "
                f"alphabet={repr(seq_info['alphabet'])}]"
            )
        else:
            keys_csv = ",".join(sorted_keys)
            header = f"[MAP:INDEXED sentinel={repr(sentinel)} keys={keys_csv}]"

        return payload, header

    def deserialize(self, payload: str, protocol_meta: str = "") -> Dict[str, str]:
        if not payload:
            return {}
        sentinel = self.DEFAULT_SENTINEL
        if "sentinel=" in protocol_meta:
            m_sentinel = re.search(
                r"sentinel=(['\"])(.*?)\1", protocol_meta, re.DOTALL
            )
            if m_sentinel:
                try:
                    sentinel = ast.literal_eval(
                        m_sentinel.group(0).split("=", 1)[1]
                    )
                except Exception:
                    sentinel = m_sentinel.group(2)

        entries = payload.split(sentinel)
        keys: List[str] = []

        # 1. P2.3 Multi-Range CJK (cjk_ranges="start1-end1,start2-end2")
        m_ranges = re.search(r'(?<!\w)cjk_ranges=(["\'])(.*?)\1', protocol_meta)
        if m_ranges:
            ranges_str = m_ranges.group(2)
            for part in ranges_str.split(","):
                part = part.strip()
                if "-" in part:
                    s_str, e_str = part.split("-", 1)
                    keys.extend(chr(cp) for cp in range(int(s_str), int(e_str) + 1))
                elif part:
                    keys.append(chr(int(part)))

        # 2. Contiguous single CJK range (cjk_start=... count=... or cjk_count=...)
        elif "cjk_start=" in protocol_meta:
            m_cjk_s = re.search(r"(?<!\w)cjk_start=(\d+)", protocol_meta)
            m_cjk_c = re.search(r"(?<!\w)(?:cjk_count|count)=(\d+)", protocol_meta)
            if m_cjk_s and m_cjk_c:
                start_cp = int(m_cjk_s.group(1))
                count = int(m_cjk_c.group(1))
                keys.extend(chr(start_cp + i) for i in range(count))

        # 3. Hybrid or Standalone Prefix sequence (prefix=... p_start/start=... p_count/count=...)
        if "prefix=" in protocol_meta:
            m_pref = re.search(r"(?<!\w)prefix=(['\"])(.*?)\1", protocol_meta)
            if m_pref:
                try:
                    p = ast.literal_eval(m_pref.group(1) + m_pref.group(2) + m_pref.group(1))
                except Exception:
                    p = m_pref.group(2)

                m_p_s = re.search(r"(?<!\w)p_start=(\d+)", protocol_meta) or re.search(
                    r"(?<!\w)start=(\d+)", protocol_meta
                )
                m_p_c = re.search(r"(?<!\w)p_count=(\d+)", protocol_meta) or re.search(
                    r"(?<!\w)count=(\d+)", protocol_meta
                )
                if m_p_s and m_p_c:
                    start_id = int(m_p_s.group(1))
                    count = int(m_p_c.group(1))
                    keys.extend(f"{p}{start_id + i}" for i in range(count))

        # 4. Template sequence (seq='«{:d}»')
        elif not keys and "seq=" in protocol_meta:
            m_seq = re.search(
                r"(?<!\w)seq=(['\"])(.*?)\1\s+start=(\d+)\s+count=(\d+)", protocol_meta
            )
            if m_seq:
                try:
                    fmt = ast.literal_eval(m_seq.group(1) + m_seq.group(2) + m_seq.group(1))
                except Exception:
                    fmt = m_seq.group(2)
                start_id = int(m_seq.group(3))
                count = int(m_seq.group(4))
                keys = [fmt.format(start_id + i) for i in range(count)]

        # 5. Explicit alphabet string
        elif not keys and "alphabet=" in protocol_meta:
            m_alpha = re.search(r"(?<!\w)alphabet=(['\"])(.*?)\1", protocol_meta)
            if m_alpha:
                try:
                    alpha_str = ast.literal_eval(m_alpha.group(1) + m_alpha.group(2) + m_alpha.group(1))
                except Exception:
                    alpha_str = m_alpha.group(2)
                keys = list(alpha_str)

        # 6. Fallback CSV keys
        elif not keys:
            m_keys = re.search(r"(?<!\w)keys=([^\s\]]+)", protocol_meta)
            if m_keys:
                keys = [k.strip() for k in m_keys.group(1).split(",") if k.strip()]

        result: Dict[str, str] = {}
        for idx, item in enumerate(entries):
            ph = keys[idx] if idx < len(keys) else f"«{idx + 1}»"
            result[ph] = item
        return result

    def estimate_entry_tokens(
        self, placeholder: str, content: str, tok: tokenizer.BaseTokenizer
    ) -> int:
        return tok.count(content) + tok.count(self.DEFAULT_SENTINEL)


class KVMappingSerializer(BaseMappingSerializer):
    """
    Key-Value mapping: raw 'KEY=CONTENT' lines with compact newline marker.
    Optimized for short single-line phrases and tokens.
    """

    name: str = "kv"
    NEWLINE_MARKER: str = "␤"

    def serialize(
        self,
        mapping: Dict[str, str],
        raw_corpus: str = "",
        ph_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        if not mapping:
            return "", "[MAP:KV]"
        lines: List[str] = []
        sorted_keys = sorted(mapping.keys(), key=natural_sort_key)
        for k in sorted_keys:
            v = mapping[k]
            v_compact = v.replace("\r\n", "\n").replace("\n", self.NEWLINE_MARKER)
            lines.append(f"{k}={v_compact}")
        payload = "\n".join(lines)
        header = f"[MAP:KV nl={repr(self.NEWLINE_MARKER)}]"
        return payload, header

    def deserialize(self, payload: str, protocol_meta: str = "") -> Dict[str, str]:
        if not payload.strip():
            return {}
        nl_marker = self.NEWLINE_MARKER
        m_nl = re.search(r"(?<!\w)nl=(['\"])(.*?)\1", protocol_meta)
        if m_nl:
            nl_marker = m_nl.group(2)

        result: Dict[str, str] = {}
        for line in payload.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.replace(nl_marker, "\n")
        return result

    def estimate_entry_tokens(
        self, placeholder: str, content: str, tok: tokenizer.BaseTokenizer
    ) -> int:
        compact_content = content.replace("\n", self.NEWLINE_MARKER)
        return tok.count(placeholder) + 1 + tok.count(compact_content) + 1


def get_mapping_serializer(name: str = "auto") -> BaseMappingSerializer:
    """Factory returning configured mapping serializer backend."""
    key = (name or "auto").strip().lower()
    if key in ("positional", "auto"):
        return PositionalMappingSerializer()
    if key == "delimited":
        return DelimitedMappingSerializer()
    if key == "kv":
        return KVMappingSerializer()
    if key == "json":
        return JSONMappingSerializer()
    return PositionalMappingSerializer()


def benchmark_mapping_formats(
    mapping: Dict[str, str],
    tok: tokenizer.BaseTokenizer,
    raw_corpus: str = "",
    ph_meta: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluates all available mapping serializers on the same dictionary.
    Computes exact token counts for payload and protocol header:
        total_tokens = payload_tokens + protocol_tokens
    """
    formats = ["json", "delimited", "positional", "kv"]
    results: List[Dict[str, Any]] = []

    for fmt_name in formats:
        serializer = get_mapping_serializer(fmt_name)
        payload, header = serializer.serialize(
            mapping, raw_corpus=raw_corpus, ph_meta=ph_meta
        )
        reconstructed = serializer.deserialize(payload, header)

        is_exact = reconstructed == mapping
        payload_tokens = tok.count(payload) if payload else 0
        protocol_tokens = tok.count(header) if header else 0
        total_tokens = payload_tokens + protocol_tokens

        results.append(
            {
                "format": fmt_name,
                "payload_chars": len(payload),
                "payload_tokens": payload_tokens,
                "protocol_tokens": protocol_tokens,
                "total_tokens": total_tokens,
                "exact_match": is_exact,
            }
        )

    results.sort(key=lambda x: x["total_tokens"])
    return results

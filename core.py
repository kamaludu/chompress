#!/usr/bin/env python3
"""
Local LLM-ready Compressor (P0, P1, P2, P3 & P4 Token-Aware Core Pipeline)
File: core.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chompress

Description:
Core compression pipeline optimized for LLM context token economy:
- Single-File First architecture: zero directory overhead for single file inputs.
- Hardened scanner: automatic exclusion of output directories, hidden folders (.git),
  virtual environments (.venv), and build/cache artifacts (__pycache__, node_modules).
- Domain-Specific Pre-deduplication (P1, P2, P3 & P4):
  * Python: docstring/type stripping, local renaming, P3.2 error/log string compaction,
    P4.1 unused import pruning, P4.2 assertion pruning.
  * Bash: ANSI escape code and full-line comment stripping.
  * Markdown: shields.io badges removal and visual table compaction.
  * P3.1: License and copyright boilerplate header annihilation.
  * P3.4: Polyglot whitespace and comment stripping for JSON and YAML.
- Global repository dictionary (P1.3): unified cross-file deduplication amortizing
  dictionary overhead over all repository occurrences.
- Multi-tier candidate detection:
  * Words and identifier tokens down to 4 characters with BPE yield validation.
  * Rabin-Karp 64-bit rolling hash substring repetition detector.
  * P2.2: Dynamic Sliding Block Discovery via 60-bit line-level polynomial rolling hash.
- Frequency-weighted replacement selection integrating Alphabet Optimizer.
- Asymmetric prefix safety: digit boundary guards and negative lookahead reconstruction.
- Universal collision-free substitution and exact lossless roundtrip verification.
- Boundary-aware atomic chunking preserving token boundaries.

Mathematical token model (pure ASCII notation):
net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
candidate_net_gain = N * (tokens(content) - tokens(ph)) - tokens(mapping_entry) - delta_protocol
"""

import bisect
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import io_utils
import mapping as mapping_module
import minifiers
import placeholders as placeholders_module
import tokenizer

# Universal fallback regex matching all supported placeholder families across the full CJK range
UNIVERSAL_FALLBACK_REGEX = re.compile(
    r"__[sbw]\d+__|«w?\d+»|\^w?\d+|~w?\d+~|§w?\d+§|⟦w?\d+⟧|[\u4e00-\u9fff]"
)


# -----------------------------------------------------------------------------
# 1. File Scanning and Loading (Single-File First & Hardened Directory Traversal)
# -----------------------------------------------------------------------------
def scan_files(
    input_path: str,
    exclude_pointless: bool = True,
    output_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scans input file, directory, or text manifest file.
    Single-File First: returns single-element metadata list for standalone files.
    Hardened Traversal:
    - Recursively ignores hidden directories (.git, .cache, .venv, .pytest_cache).
    - Ignores build and cache directories (__pycache__, node_modules, build, dist).
    - Automatically excludes the target output_dir if located inside input_path,
      preventing recursive self-ingestion loops.
    """
    default_exclude_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".ttf", ".woff", ".woff2",
        ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".bin", ".class", ".o", ".a", ".jar",
        ".mp3", ".mp4", ".mov", ".avi", ".webm", ".ogg", ".wav", ".7z", ".rar", ".iso",
        ".db", ".sqlite", ".bak", ".swp", ".tmp", ".lock", ".pyc", ".pyo",
    }
    default_exclude_dirs = {
        ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
        ".pytest_cache", ".mypy_cache", ".tox", ".eggs", "build", "dist",
    }

    p = Path(input_path)
    files: List[Path] = []
    out_resolved = Path(output_dir).resolve() if output_dir else None

    if p.is_dir():
        p_resolved = p.resolve()
        for f in sorted(p.rglob("*")):
            if f.is_dir():
                continue

            # 1. Automatic exclusion of the output directory
            if out_resolved:
                try:
                    f_resolved = f.resolve()
                    if f_resolved == out_resolved or out_resolved in f_resolved.parents:
                        continue
                except Exception:
                    pass

            # 2. Check relative path parts for hidden or excluded directories
            try:
                rel_parts = f.relative_to(p).parts
            except Exception:
                try:
                    rel_parts = f.resolve().relative_to(p_resolved).parts
                except Exception:
                    rel_parts = f.parts

            is_excluded = False
            for part in rel_parts[:-1]:
                if part.startswith(".") or part in default_exclude_dirs:
                    is_excluded = True
                    break
            if is_excluded:
                continue

            # 3. Check filename itself
            if rel_parts[-1].startswith(".") or rel_parts[-1] in default_exclude_dirs:
                continue

            if f.is_file():
                files.append(f)
    elif p.is_file():
        files.append(p)
    else:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                fp = Path(line)
                if fp.is_file():
                    files.append(fp)

    metas: List[Dict[str, Any]] = []
    for f in files:
        try:
            if exclude_pointless and f.suffix.lower() in default_exclude_exts:
                continue
            sha = io_utils.sha256_file(f)
        except Exception:
            continue
        metas.append(
            {
                "path": str(f.resolve()),
                "size": f.stat().st_size,
                "sha256": sha,
                "is_single_file": p.is_file(),
            }
        )
    if not metas:
        raise RuntimeError(f"No valid text files found in input: {input_path}")
    return metas


def load_contents(file_metas: List[Dict[str, Any]]) -> Dict[str, str]:
    """Reads all identified text files into memory mapped by resolved path."""
    contents: Dict[str, str] = {}
    for meta in file_metas:
        path = meta["path"]
        try:
            text = io_utils.read_text(path)
        except Exception:
            continue
        contents[path] = text
    return contents


def strip_empty_lines_by_extension(
    contents: Dict[str, str],
    preserve_exts: Optional[Set[str]] = None,
    normalize_indent: bool = False,
) -> Dict[str, str]:
    """
    Strips redundant empty lines in code while preserving Markdown and text formatting.
    Optionally normalizes 4 spaces of leading indentation to single tabs.
    """
    if preserve_exts is None:
        preserve_exts = {".md", ".txt", ".rst", ".html", ".tex", ".adoc", ".org"}

    new_contents: Dict[str, str] = {}
    for path, text in contents.items():
        ext = Path(path).suffix.lower()
        if ext in preserve_exts:
            new_contents[path] = text
            continue

        lines = text.splitlines(keepends=True)
        kept: List[str] = []
        for ln in lines:
            line_content = ln.rstrip("\r\n")
            cleaned = line_content.rstrip(" \t")
            if cleaned == "":
                continue

            if normalize_indent:
                leading_spaces = len(cleaned) - len(cleaned.lstrip(" "))
                if leading_spaces >= 4:
                    num_tabs = leading_spaces // 4
                    remainder = leading_spaces % 4
                    cleaned = ("\t" * num_tabs) + (" " * remainder) + cleaned.lstrip(" ")

            line_ending = "\n" if ln.endswith(("\r", "\n")) else ""
            kept.append(cleaned + line_ending)

        new_contents[path] = "".join(kept)
    return new_contents


def canonicalize_contents(
    contents: Dict[str, str],
    enable_comments_removal: bool = True,
    enable_table_compaction: bool = True,
    enable_python_renaming: bool = True,
    enable_docstring_removal: bool = True,
    enable_type_annotations_removal: bool = True,
    enable_ansi_stripping: bool = True,
    enable_badge_removal: bool = True,
    enable_license_stripping: bool = True,
    enable_error_string_compaction: bool = True,
    enable_import_pruning: bool = True,
    enable_assert_pruning: bool = True,
    **kwargs: Any,
) -> Dict[str, str]:
    """
    Pre-deduplication canonicalizer delegating to safe language-aware minifiers (P1, P2, P3 & P4).
    Applies AST transformations for Python (docstrings, types, renaming, error strings,
    unused imports pruning, assert pruning), ANSI/comment stripping for Bash,
    badge/table compaction for Markdown, license header annihilation, and config minification.
    """
    sig = inspect.signature(minifiers.canonicalize_content)
    params = sig.parameters

    forward_kwargs: Dict[str, Any] = {
        "enable_comments_removal": enable_comments_removal,
        "enable_table_compaction": enable_table_compaction,
        "enable_python_renaming": enable_python_renaming,
        "enable_docstring_removal": enable_docstring_removal,
        "enable_type_annotations_removal": enable_type_annotations_removal,
        "enable_ansi_stripping": enable_ansi_stripping,
        "enable_badge_removal": enable_badge_removal,
    }

    if "enable_license_stripping" in params:
        forward_kwargs["enable_license_stripping"] = enable_license_stripping
    if "enable_error_string_compaction" in params:
        forward_kwargs["enable_error_string_compaction"] = enable_error_string_compaction
    if "enable_import_pruning" in params:
        forward_kwargs["enable_import_pruning"] = enable_import_pruning
    if "enable_assert_pruning" in params:
        forward_kwargs["enable_assert_pruning"] = enable_assert_pruning

    for k, v in kwargs.items():
        if k in params:
            forward_kwargs[k] = v

    canonical: Dict[str, str] = {}
    for path, text in contents.items():
        canonical[path] = minifiers.canonicalize_content(
            file_path=path,
            content=text,
            **forward_kwargs,
        )
    return canonical


# -----------------------------------------------------------------------------
# 2. Multi-Granularity Repetition Detection
# -----------------------------------------------------------------------------
def find_repetitions(
    contents: Dict[str, str],
    L_min: int = 14,
    N_min: int = 2,
    B_min_lines: int = 2,
    B_max_lines: int = 10,
    L_max: int = 2000,
) -> List[Dict[str, Any]]:
    """
    Detects repeated candidates across words, rolling-hash substrings, and line blocks.
    De-duplicates candidate hashes to ensure a unified candidate pool across all files.
    """
    word_candidates = _find_word_candidates(contents, min_len=4, min_freq=max(3, N_min))
    substring_candidates = _find_substring_candidates(contents, L_min, N_min, L_max)
    block_candidates = _find_block_candidates(contents, B_min_lines, B_max_lines)

    seen: Set[str] = set()
    all_candidates: List[Dict[str, Any]] = []

    for c in word_candidates + substring_candidates + block_candidates:
        h = c["id_hash"]
        if h not in seen:
            seen.add(h)
            all_candidates.append(c)

    return all_candidates


def _find_word_candidates(
    contents: Dict[str, str], min_len: int = 4, min_freq: int = 3
) -> List[Dict[str, Any]]:
    """
    Identifies recurring identifier tokens and words across files.
    Scans tokens down to 4 characters to capture high-frequency identifiers.
    """
    word_re = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{%d,}\b" % (min_len - 1))
    word_occs: Dict[str, List[Tuple[str, int, int]]] = {}

    for path, text in contents.items():
        for m in word_re.finditer(text):
            w = m.group(0)
            word_occs.setdefault(w, []).append((path, m.start(), m.end()))

    candidates: List[Dict[str, Any]] = []
    for w, occs in word_occs.items():
        if len(occs) >= min_freq:
            h = hashlib.sha256(w.encode("utf-8")).hexdigest()
            candidates.append(
                {
                    "id_hash": h,
                    "type": "word",
                    "content": w,
                    "occurrences": [{"path": p, "start": s, "end": e} for p, s, e in occs],
                }
            )
    return candidates


def _find_substring_candidates(
    contents: Dict[str, str], L_min: int, N_min: int, L_max: int
) -> List[Dict[str, Any]]:
    """
    Rabin-Karp rolling hash substring repetition detector.
    Uses 64-bit packed file and offset coordinates and bi-directional expansion.
    """
    base = 257
    mod = 2**61 - 1

    def roll_hash_init(s: str) -> Tuple[int, int]:
        h = 0
        power = 1
        for ch in s:
            h = (h * base + ord(ch)) % mod
            power = (power * base) % mod
        return h, power

    def roll_hash_next(h: int, power: int, left: str, right: str) -> int:
        return (h * base - ord(left) * power + ord(right)) % mod

    file_paths = list(contents.keys())
    index: Dict[int, Any] = {}

    def _record_packed(h_val: int, packed_val: int) -> None:
        curr = index.get(h_val)
        if curr is None:
            index[h_val] = packed_val
        elif isinstance(curr, list):
            curr.append(packed_val)
        else:
            index[h_val] = [curr, packed_val]

    for file_id, path in enumerate(file_paths):
        text = contents[path]
        n = len(text)
        if n < L_min:
            continue
        window = text[0:L_min]
        h, power = roll_hash_init(window)
        _record_packed(h, (file_id << 32) | 0)
        for i in range(1, n - L_min + 1):
            h = roll_hash_next(h, power, text[i - 1], text[i + L_min - 1])
            _record_packed(h, (file_id << 32) | i)

    candidates: Dict[str, Dict[str, Any]] = {}

    for h, val in index.items():
        if not isinstance(val, list) or len(val) < N_min:
            continue
        packed_occs = val

        exact_groups: Dict[str, List[Tuple[str, int]]] = {}
        for packed in packed_occs:
            file_id = packed >> 32
            start = packed & 0xFFFFFFFF
            path = file_paths[file_id]
            window_str = contents[path][start : start + L_min]
            exact_groups.setdefault(window_str, []).append((path, start))

        for window_str, group_occs in exact_groups.items():
            if len(group_occs) < N_min:
                continue

            seed_path, seed_start = group_occs[0]
            seed_text = contents[seed_path]

            per_occ_expansion: List[Tuple[str, int, int, int]] = []
            for path, start in group_occs:
                t = contents[path]

                k_left = 0
                while (
                    start - 1 - k_left >= 0
                    and seed_start - 1 - k_left >= 0
                    and t[start - 1 - k_left] == seed_text[seed_start - 1 - k_left]
                ):
                    k_left += 1
                    if L_min + k_left >= L_max:
                        break

                k_right = 0
                while (
                    start + L_min + k_right < len(t)
                    and seed_start + L_min + k_right < len(seed_text)
                    and t[start + L_min + k_right] == seed_text[seed_start + L_min + k_right]
                ):
                    k_right += 1
                    if L_min + k_right >= L_max:
                        break

                per_occ_expansion.append((path, start, k_left, k_right))

            common_left = min(item[2] for item in per_occ_expansion)
            common_right = min(item[3] for item in per_occ_expansion)

            if L_min + common_left + common_right > L_max:
                common_right = max(0, L_max - L_min - common_left)

            content_start = seed_start - common_left
            content_end = seed_start + L_min + common_right
            content = seed_text[content_start:content_end]

            if len(content) < L_min:
                continue

            id_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            cand = candidates.setdefault(
                id_hash,
                {
                    "id_hash": id_hash,
                    "type": "substring",
                    "content": content,
                    "occurrences": [],
                    "_seen_occs": set(),
                },
            )

            for path, start, _, _ in per_occ_expansion:
                occ_s = start - common_left
                occ_e = start + L_min + common_right
                occ_key = (path, occ_s, occ_e)
                if occ_key not in cand["_seen_occs"]:
                    cand["_seen_occs"].add(occ_key)
                    cand["occurrences"].append({"path": path, "start": occ_s, "end": occ_e})

    result: List[Dict[str, Any]] = []
    for c in candidates.values():
        c.pop("_seen_occs", None)
        if len(c["occurrences"]) >= N_min:
            result.append(c)
    return result


def _find_block_candidates(
    contents: Dict[str, str], B_min_lines: int, B_max_lines: int
) -> List[Dict[str, Any]]:
    """
    P2.2: Dynamic Sliding Block Repetition Discovery.
    Uses a 60-bit line-level polynomial rolling hash state machine across parametric
    window sizes [B_min_lines, B_max_lines]. Precomputes line offsets and hashes
    to achieve O(1) block rolling evaluation, eliminating redundant SHA-256 allocations.
    """
    if B_min_lines > B_max_lines or B_min_lines <= 0:
        return []

    file_paths = list(contents.keys())
    file_lines: List[List[str]] = []
    file_offsets: List[List[int]] = []
    file_line_hashes: List[List[int]] = []

    # 60-bit prime base and modulus for line polynomial rolling hash
    base = 1000003
    mod = 2**61 - 1

    for path in file_paths:
        lines = contents[path].splitlines(keepends=True)
        offsets = [0]
        curr = 0
        hashes: List[int] = []
        for ln in lines:
            curr += len(ln)
            offsets.append(curr)
            # 60-bit integer hash per line
            h_val = int(hashlib.md5(ln.encode("utf-8")).hexdigest()[:15], 16)
            hashes.append(h_val)

        file_lines.append(lines)
        file_offsets.append(offsets)
        file_line_hashes.append(hashes)

    candidates: List[Dict[str, Any]] = []
    seen_blocks: Set[str] = set()

    sizes = list(range(B_max_lines, B_min_lines - 1, -1))

    for size in sizes:
        power = pow(base, size - 1, mod)
        block_index: Dict[int, List[Tuple[int, int]]] = {}

        for file_id, hashes in enumerate(file_line_hashes):
            n_lines = len(hashes)
            if n_lines < size:
                continue

            # Initialize rolling hash for first window of 'size' lines
            h = 0
            for j in range(size):
                h = (h * base + hashes[j]) % mod
            block_index.setdefault(h, []).append((file_id, 0))

            # Slide window across remaining lines in O(1)
            for i in range(1, n_lines - size + 1):
                h = ((h - hashes[i - 1] * power) * base + hashes[i + size - 1]) % mod
                block_index.setdefault(h, []).append((file_id, i))

        # Group matches and verify exact string contents
        for h, occs in block_index.items():
            if len(occs) < 2:
                continue

            exact_groups: Dict[str, List[Tuple[int, int]]] = {}
            for file_id, li in occs:
                start_char = file_offsets[file_id][li]
                end_char = file_offsets[file_id][li + size]
                block_str = contents[file_paths[file_id]][start_char:end_char]
                exact_groups.setdefault(block_str, []).append((file_id, li))

            for block_content, matched_occs in exact_groups.items():
                if len(matched_occs) < 2:
                    continue

                block_sha = hashlib.sha256(block_content.encode("utf-8")).hexdigest()
                if block_sha in seen_blocks:
                    continue
                seen_blocks.add(block_sha)

                cand_occurrences: List[Dict[str, Any]] = []
                for f_id, line_idx in matched_occs:
                    s_c = file_offsets[f_id][line_idx]
                    e_c = file_offsets[f_id][line_idx + size]
                    cand_occurrences.append(
                        {"path": file_paths[f_id], "start": s_c, "end": e_c}
                    )

                candidates.append(
                    {
                        "id_hash": block_sha,
                        "type": "block",
                        "content": block_content,
                        "occurrences": cand_occurrences,
                    }
                )

    return candidates


# -----------------------------------------------------------------------------
# 3. Frequency-Weighted Replacement Selection (Global Repository Amortization)
# -----------------------------------------------------------------------------
def _has_interval_overlap(intervals: List[Tuple[int, int]], s: int, e: int) -> bool:
    """Checks whether interval [s, e) intersects any interval in sorted list."""
    if not intervals:
        return False
    idx = bisect.bisect_right(intervals, s, key=lambda x: x[1])
    if idx < len(intervals) and intervals[idx][0] < e:
        return True
    return False


def select_replacements(
    candidates: List[Dict[str, Any]],
    all_raw_text: str = "",
    placeholder_fmt_sub: str = "__s{:d}__",
    placeholder_fmt_blk: str = "__b{:d}__",
    min_total_saving: int = 1,
    tok: Optional[tokenizer.BaseTokenizer] = None,
    ph_engine: Optional[placeholders_module.PlaceholderEngine] = None,
    map_serializer: Optional[mapping_module.BaseMappingSerializer] = None,
) -> List[Dict[str, Any]]:
    """
    P0, P1, P2, P3 & P4 Token-Aware Replacement Selection with Global Dictionary Amortization:
    1. Pre-scores candidates across all files: marginal dictionary cost is paid once in global map.
    2. Filters out candidates yielding zero per-occurrence token reduction (tok_content <= tok_ph).
    3. Sorts candidates descending by net gain and overall repository frequency.
    4. Builds the optimized placeholder alphabet (assigning 1-token symbols to top frequency patterns).
    5. Applies collision-free greedy selection with interval overlap resolution per file.
    6. Finalizes and trims active alphabet strictly to the selected replacements.
    """
    if tok is None:
        tok = tokenizer.get_tokenizer("heuristic")

    if ph_engine is None:
        if placeholder_fmt_sub != "__s{:d}__":
            ph_engine = placeholders_module.PlaceholderEngine("classic", tok=tok)
            ph_engine.cfg["sub"] = placeholder_fmt_sub
            ph_engine.cfg["blk"] = placeholder_fmt_blk
        else:
            ph_engine = placeholders_module.PlaceholderEngine("auto", tok=tok)
            ph_engine.auto_calibrate(all_raw_text)

    if map_serializer is None:
        map_serializer = mapping_module.get_mapping_serializer("positional")

    scored: List[Tuple[int, int, Dict[str, Any]]] = []

    for c in candidates:
        content = c["content"]
        occs = c["occurrences"]
        N = len(occs)
        if N < 2:
            continue

        c_type = c.get("type", "substring")
        sample_ph = ph_engine.format_placeholder(c_type, 1)

        tok_content = tok.count(content)
        tok_ph = tok.count(sample_ph)

        # Early token efficiency guard: skip if original content is not strictly larger than placeholder
        if tok_content <= tok_ph:
            continue

        tok_map = map_serializer.estimate_entry_tokens(sample_ph, content, tok)

        # Global repository dictionary amortization: tok_map is deducted once for all N occurrences
        net_gain = N * (tok_content - tok_ph) - tok_map
        if net_gain >= min_total_saving:
            scored.append((net_gain, N, c))

    # Sort descending by net gain, then frequency, then content length
    scored.sort(key=lambda x: (-x[0], -x[1], -len(x[2]["content"]), x[2]["id_hash"]))

    # Alphabet Optimization: build initial alphabet pool
    candidate_frequencies = [x[1] for x in scored]
    ph_engine.build_alphabet(
        raw_corpus=all_raw_text,
        required_count=len(scored),
        candidate_frequencies=candidate_frequencies,
    )

    occupied: Dict[str, List[Tuple[int, int]]] = {}
    replacements: List[Dict[str, Any]] = []
    replacement_idx = 1

    for initial_saving, freq, c in scored:
        content = c["content"]
        c_type = c.get("type", "substring")

        placeholder = ph_engine.format_placeholder(c_type, replacement_idx)

        # Collision verification against corpus
        while placeholder in all_raw_text:
            replacement_idx += 1
            placeholder = ph_engine.format_placeholder(c_type, replacement_idx)

        valid_occs: List[Dict[str, Any]] = []
        candidate_occupied_per_file: Dict[str, List[Tuple[int, int]]] = {}

        for o in c["occurrences"]:
            path = o["path"]
            s = o["start"]
            e = o["end"]

            if _has_interval_overlap(occupied.get(path, []), s, e):
                continue
            if _has_interval_overlap(candidate_occupied_per_file.get(path, []), s, e):
                continue

            valid_occs.append(o)
            bisect.insort(candidate_occupied_per_file.setdefault(path, []), (s, e), key=lambda x: x[1])

        N_valid = len(valid_occs)
        if N_valid < 2:
            continue

        tok_content = tok.count(content)
        tok_ph = tok.count(placeholder)
        tok_map = map_serializer.estimate_entry_tokens(placeholder, content, tok)

        recomputed_gain = N_valid * (tok_content - tok_ph) - tok_map
        if recomputed_gain < min_total_saving:
            continue

        rep = {
            "id": f"{c_type[0].upper()}:{replacement_idx:d}",
            "type": c_type,
            "placeholder": placeholder,
            "content": content,
            "occurrences": valid_occs,
        }
        replacements.append(rep)
        replacement_idx += 1

        for o in valid_occs:
            bisect.insort(occupied.setdefault(o["path"], []), (o["start"], o["end"]), key=lambda x: x[1])

    used_placeholders = [r["placeholder"] for r in replacements]
    ph_engine.finalize_used_alphabet(used_placeholders)

    return replacements


# -----------------------------------------------------------------------------
# 4. Placeholder Application & Reverse Map Construction
# -----------------------------------------------------------------------------
def apply_placeholders(
    contents: Dict[str, str],
    replacements: List[Dict[str, Any]],
    ph_engine: Optional[placeholders_module.PlaceholderEngine] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Substitutes replacement occurrences into text.
    Applies digit boundary protection for open prefix placeholders.
    Builds structured reverse_map dictionary containing metadata, occurrences,
    and alphabet protocol metadata strictly synchronized with inserted tokens.
    """
    per_file: Dict[str, List[Dict[str, Any]]] = {}
    for r in replacements:
        for o in r["occurrences"]:
            per_file.setdefault(o["path"], []).append(
                {
                    "start": o["start"],
                    "end": o["end"],
                    "id": r.get("id"),
                    "placeholder": r["placeholder"],
                    "content": r.get("content", ""),
                    "type": r["type"],
                }
            )

    llm_ready: Dict[str, str] = {}
    reverse_map: Dict[str, Any] = {
        "placeholders": {},
        "ph_meta": {},
        "metadata": {"tool": "chompress", "version": "3.5.0"},
    }

    placeholders_dict = reverse_map["placeholders"]

    for path, text in contents.items():
        repls = per_file.get(path, [])
        if not repls:
            llm_ready[path] = text
            continue

        repls.sort(key=lambda x: x["start"])
        out_parts: List[str] = []
        last = 0

        for r in repls:
            s = r["start"]
            e = r["end"]
            if s < last or s < 0 or e > len(text) or e <= s:
                continue
            actual = text[s:e]
            expected = r.get("content", "")
            if actual != expected:
                continue

            token = r["placeholder"]

            # Boundary guard: prevent merging open prefix ending in digit with next digit (e.g. ^1 + 5 -> ^15)
            if token[-1].isdigit() and not any(token.endswith(suf) for suf in (">", "»", "]", "}", "§", "⟧", "~", "_")):
                if e < len(text) and text[e].isdigit():
                    continue

            out_parts.append(text[last:s])
            out_parts.append(token)
            last = e

            actual_content = actual

            if token not in placeholders_dict:
                placeholders_dict[token] = {
                    "type": r["type"],
                    "content": actual_content,
                    "sha256": hashlib.sha256(actual_content.encode("utf-8")).hexdigest(),
                    "length": len(actual_content),
                    "occurrences": [],
                    "token": token,
                    "id": r.get("id"),
                }

            placeholders_dict[token]["occurrences"].append({"path": path, "start": s, "end": e})

        out_parts.append(text[last:])
        llm_ready[path] = "".join(out_parts)

    actual_used_tokens = list(placeholders_dict.keys())
    if ph_engine:
        ph_engine.finalize_used_alphabet(actual_used_tokens)
        reverse_map["ph_meta"] = ph_engine.get_protocol_meta()

    return llm_ready, reverse_map


def _build_token_map_from_reverse_map(reverse_map: Dict[str, Any]) -> Dict[str, str]:
    """Extracts flat {placeholder: content} mapping from reverse_map."""
    token_map: Dict[str, str] = {}
    placeholders = reverse_map.get("placeholders", {})
    if not isinstance(placeholders, dict):
        return token_map

    for key, info in placeholders.items():
        if not isinstance(info, dict):
            continue
        tok = info.get("token") or key
        if not isinstance(tok, str):
            continue
        content = info.get("content", "")
        if not isinstance(content, str):
            continue
        token_map[tok] = content
    return token_map


def _reconstruct_using_tokens(transformed: str, token_map: Dict[str, str]) -> str:
    r"""
    Substitutes placeholders with original content in longest-first order.
    Applies negative lookahead (?!\d) for open digit-ending prefixes to prevent prefix collisions.
    """
    if not token_map:
        return transformed

    tokens_sorted = sorted(token_map.keys(), key=len, reverse=True)
    pattern_parts: List[str] = []
    for t in tokens_sorted:
        esc = re.escape(t)
        if t[-1].isdigit() and not any(t.endswith(suf) for suf in (">", "»", "]", "}", "§", "⟧", "~", "_")):
            pattern_parts.append(esc + r"(?!\d)")
        else:
            pattern_parts.append(esc)

    pattern = re.compile("|".join(pattern_parts))
    return pattern.sub(lambda m: token_map[m.group(0)], transformed)


def extract_global_mapping(reverse_map: Dict[str, Any]) -> Dict[str, str]:
    """
    P1.3: Extracts unified global repository dictionary containing all active placeholders
    used across any file in the entire repository.
    """
    if not isinstance(reverse_map, dict):
        return {}
    placeholders = reverse_map.get("placeholders", {})
    out: Dict[str, str] = {}
    for token, info in placeholders.items():
        if isinstance(info, dict) and info.get("content"):
            out[token] = info["content"]
    return out


def extract_mapping_for_files(reverse_map: dict, paths: list) -> Dict[str, str]:
    """
    Extracts minimal mapping subset strictly required for the specified target paths.
    Single-File First: if only 1 file path is passed or '.', returns full scope cleanly.
    """
    if not isinstance(reverse_map, dict):
        return {}

    norm_targets = [Path(p.strip()).as_posix() for p in (paths or []) if p and str(p).strip()]
    placeholders = reverse_map.get("placeholders", {})
    out: Dict[str, str] = {}

    if len(norm_targets) == 1 and norm_targets[0] in (".", ""):
        return extract_global_mapping(reverse_map)

    target_set = set(norm_targets)

    for token, info in placeholders.items():
        if not isinstance(info, dict):
            continue
        occs = info.get("occurrences", [])
        if not occs:
            content = info.get("content", "")
            if content:
                out[token] = content
            continue

        matched = False
        for occ in occs:
            occ_path = occ.get("path")
            if not occ_path:
                continue

            occ_posix = Path(occ_path).as_posix()
            if occ_posix in target_set or Path(occ_posix).name in target_set:
                matched = True
                break

            for t in norm_targets:
                if occ_posix.endswith("/" + t) or occ_posix == t:
                    matched = True
                    break
            if matched:
                break

        if not matched:
            continue

        content = info.get("content", "")
        if content:
            out[token] = content

    return out


# -----------------------------------------------------------------------------
# 5. Exact Roundtrip Integrity Verification
# -----------------------------------------------------------------------------
def roundtrip_check(
    target_contents: Dict[str, str],
    llm_ready: Dict[str, str],
    reverse_map: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Verifies that decompress(llm_ready) == target_contents identically.
    Detects undeclared placeholders, residual artifacts, and mismatches.
    Works universally across single-token symbols, numeric sequences, and legacy formats.
    """
    details: List[str] = []
    ok_all = True

    declared: Set[str] = set()
    if not isinstance(reverse_map, dict):
        details.append("ERROR: reverse_map is not a valid dict.")
        return False, details

    phs = reverse_map.get("placeholders", {})
    if isinstance(phs, dict):
        declared.update(phs.keys())
    else:
        details.append("ERROR: reverse_map['placeholders'] is not a valid dict.")
        return False, details

    declared_sorted = sorted(declared, key=len, reverse=True)
    declared_escaped: List[str] = []
    for t in declared_sorted:
        if not t:
            continue
        esc = re.escape(t)
        if t[-1].isdigit() and not any(t.endswith(suf) for suf in (">", "»", "]", "}", "§", "⟧", "~", "_")):
            declared_escaped.append(esc + r"(?!\d)")
        else:
            declared_escaped.append(esc)

    if declared_escaped:
        dyn_pattern = "|".join(declared_escaped) + "|" + UNIVERSAL_FALLBACK_REGEX.pattern
    else:
        dyn_pattern = UNIVERSAL_FALLBACK_REGEX.pattern
    placeholder_re = re.compile(dyn_pattern)

    token_map = _build_token_map_from_reverse_map(reverse_map) or {}

    introduced_tokens: Set[str] = set()
    all_comp_tokens: Set[str] = set()

    for path, text in llm_ready.items():
        if isinstance(text, str):
            comp_tokens = set(placeholder_re.findall(text))
            all_comp_tokens.update(comp_tokens)
            target_text = target_contents.get(path, "")
            orig_tokens = (
                set(placeholder_re.findall(target_text))
                if isinstance(target_text, str)
                else set()
            )
            introduced_tokens.update(comp_tokens - orig_tokens)

    missing_defs = sorted(introduced_tokens - declared)
    if missing_defs:
        ok_all = False
        details.append(
            f"ERROR: {len(missing_defs)} placeholder(s) used but not defined in reverse_map:"
        )
        for ph in missing_defs[:20]:
            details.append(f"  - missing: {ph}")

    orphans = sorted(declared - all_comp_tokens)
    if orphans:
        details.append(
            f"Warning: {len(orphans)} placeholder(s) declared but never used in files:"
        )
        for ph in orphans[:10]:
            details.append(f"  - orphan: {ph}")

    for path, target in target_contents.items():
        if path not in llm_ready:
            ok_all = False
            details.append(f"ERROR: Missing path in compressed output: {path}")
            continue

        transformed = llm_ready[path]
        if not isinstance(transformed, str):
            ok_all = False
            details.append(f"ERROR: Transformed content for {path} is not a string.")
            continue

        try:
            recon = _reconstruct_using_tokens(transformed, token_map)
        except Exception as e:
            ok_all = False
            details.append(f"ERROR: Reconstruction exception for {path}: {e}")
            continue

        if recon != target:
            ok_all = False
            residuals_recon = set(placeholder_re.findall(recon))
            residuals_target = set(placeholder_re.findall(target))
            unresolved = residuals_recon - residuals_target
            if unresolved:
                details.append(
                    f"ERROR: {len(unresolved)} unresolved placeholder(s) remain in {path} after reconstruction:"
                )
                for res_ph in sorted(unresolved)[:10]:
                    details.append(f"  - residual: {res_ph}")

            len_target = len(target)
            len_recon = len(recon)
            mismatch_idx = -1
            min_len = min(len_target, len_recon)
            for i in range(min_len):
                if target[i] != recon[i]:
                    mismatch_idx = i
                    break
            if mismatch_idx == -1 and len_target != len_recon:
                mismatch_idx = min_len

            ctx_start = max(0, mismatch_idx - 25)
            ctx_end_target = min(len_target, mismatch_idx + 25)
            ctx_end_recon = min(len_recon, mismatch_idx + 25)

            details.append(
                f"ERROR: Content mismatch in {path} at char {mismatch_idx} "
                f"(len_target={len_target}, len_recon={len_recon}):"
            )
            details.append(f"  Expected: {repr(target[ctx_start:ctx_end_target])}")
            details.append(f"  Recon   : {repr(recon[ctx_start:ctx_end_recon])}")
        else:
            details.append(f"OK: Verified 100% match for {path} ({len(target)} chars)")

    if ok_all:
        details.insert(0, f"EXACT ROUNDTRIP SUCCESS: {len(target_contents)} file(s) verified.")
    else:
        details.insert(0, "EXACT ROUNDTRIP FAILED: Discrepancies detected.")

    return ok_all, details


# -----------------------------------------------------------------------------
# 6. Manifest and Reverse Map Serialization
# -----------------------------------------------------------------------------
def build_manifest(
    file_metas: List[Dict[str, Any]], reverse_map: Dict[str, Any], input_root: str
) -> Dict[str, Any]:
    """Generates compact manifest JSON indexing paths, hashes, and placeholder usage."""
    root = Path(input_root).resolve()
    metas_sorted = sorted(file_metas, key=lambda m: m["path"])
    paths: List[str] = []
    files: List[Dict[str, Any]] = []
    path_to_idx: Dict[str, int] = {}

    for idx, m in enumerate(metas_sorted):
        abs_p = Path(m["path"]).resolve()
        try:
            rel = abs_p.relative_to(root)
            p = str(rel).replace("\\", "/")
        except Exception:
            p = Path(abs_p).name
        paths.append(p)
        path_to_idx[str(abs_p)] = idx
        path_to_idx[abs_p.as_posix()] = idx
        files.append({"i": idx, "sha": m.get("sha256", ""), "ph": []})

    file_placeholders: List[Set[str]] = [set() for _ in range(len(files))]
    ph_index: Dict[str, Dict[str, Any]] = {}
    placeholders = reverse_map.get("placeholders", {})

    for pid, info in placeholders.items():
        ph_index[pid] = {"sha": info.get("sha256", ""), "len": info.get("length", 0)}

        for occ in info.get("occurrences", []):
            occ_path = occ.get("path")
            if not occ_path:
                continue

            resolved_occ = Path(occ_path).resolve()
            idx = path_to_idx.get(str(resolved_occ))
            if idx is None:
                idx = path_to_idx.get(resolved_occ.as_posix())

            if idx is not None:
                file_placeholders[idx].add(pid)

    for idx, ph_set in enumerate(file_placeholders):
        files[idx]["ph"] = sorted(ph_set)

    return {"paths": paths, "files": files, "ph": ph_index, "v": 1}


def write_reverse_map(reverse_map: dict, out_path: Any) -> None:
    """Writes full reverse_map.json to disk atomically."""
    p = Path(out_path)
    io_utils.ensure_dir(p.parent)
    io_utils.write_json_atomic(p, reverse_map, ensure_ascii=False, indent=2)


def write_mapping_subset(
    reverse_map: dict,
    paths: list,
    out_path: Any,
    compact: bool = True,
    serializer: Optional[mapping_module.BaseMappingSerializer] = None,
    ph_meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Writes mapping subset or global repository dictionary for target paths.
    Supports Positional, Delimited, KV, or JSON formatting.
    """
    p = Path(out_path)
    subset = extract_mapping_for_files(reverse_map, paths or [])
    io_utils.ensure_dir(p.parent)

    resolved_ph_meta = ph_meta or reverse_map.get("ph_meta", {})

    if serializer is not None and serializer.name != "json":
        payload, header = serializer.serialize(subset, ph_meta=resolved_ph_meta)
        meta_path = p.with_suffix(".proto")
        io_utils.write_atomic(p, payload)
        io_utils.write_atomic(meta_path, header)
    else:
        if compact:
            io_utils.write_json_atomic(
                p, subset, ensure_ascii=False, separators=(",", ":"), indent=None
            )
        else:
            io_utils.write_json_atomic(p, subset, ensure_ascii=False, indent=2)


# -----------------------------------------------------------------------------
# 7. Boundary-Aware Chunker
# -----------------------------------------------------------------------------
def chunk_outputs(
    llm_ready: Dict[str, str],
    output_dir: Path,
    chunk_size: int,
    input_root: Optional[Path] = None,
    reverse_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Partitions compressed files into chunks without splitting placeholder tokens.
    Backtracks to line boundaries where feasible.
    """
    out_manifest: Dict[str, Any] = {"files": {}, "chunks_dir": "chunks", "v": 1}
    chunks_root = Path(output_dir) / out_manifest["chunks_dir"]
    io_utils.ensure_dir(chunks_root)

    active_tokens: Set[str] = set()
    if reverse_map and isinstance(reverse_map, dict):
        phs = reverse_map.get("placeholders", {})
        if isinstance(phs, dict):
            for k, info in phs.items():
                if isinstance(info, dict) and isinstance(info.get("token"), str):
                    active_tokens.add(info["token"])
                elif isinstance(k, str):
                    active_tokens.add(k)

    if active_tokens:
        sorted_tokens = sorted(active_tokens, key=len, reverse=True)
        token_pattern = re.compile("|".join(re.escape(t) for t in sorted_tokens))
    else:
        token_pattern = UNIVERSAL_FALLBACK_REGEX

    resolved_root = Path(input_root).resolve() if input_root else None

    for abs_path, text in llm_ready.items():
        abs_p = Path(abs_path).resolve()
        if resolved_root:
            try:
                rel = abs_p.relative_to(resolved_root)
                rel_path = rel.as_posix()
            except Exception:
                rel_path = abs_p.name
        else:
            rel_path = abs_p.name

        chunk_dir = chunks_root / Path(rel_path)
        io_utils.ensure_dir(chunk_dir)

        total_len = len(text)
        sha_full = io_utils.sha256_text(text)
        chunks_list: List[str] = []

        if total_len == 0:
            chunk_name = f"{1:04d}.txt"
            chunk_path = chunk_dir / chunk_name
            io_utils.write_atomic(chunk_path, "")
            chunks_list.append(str(Path(rel_path) / chunk_name).replace("\\", "/"))
        else:
            protected_spans: List[Tuple[int, int]] = []
            for m in token_pattern.finditer(text):
                protected_spans.append((m.start(), m.end()))

            curr = 0
            idx = 1
            while curr < total_len:
                if curr + chunk_size >= total_len:
                    cut = total_len
                else:
                    target_cut = curr + chunk_size
                    cut = target_cut

                    for s_start, s_end in protected_spans:
                        if s_start < target_cut < s_end:
                            cut = s_start
                            break
                        if s_start >= target_cut:
                            break

                    nl_pos = text.rfind("\n", curr, cut)
                    if nl_pos != -1 and (nl_pos + 1) > curr:
                        inside_token = False
                        for s_start, s_end in protected_spans:
                            if s_start <= nl_pos < s_end:
                                inside_token = True
                                break
                            if s_start > nl_pos:
                                break
                        if not inside_token:
                            cut = nl_pos + 1

                    if cut <= curr:
                        forced = target_cut
                        for s_start, s_end in protected_spans:
                            if s_start <= curr < s_end:
                                forced = s_end
                                break
                        cut = max(curr + 1, min(forced, total_len))

                part = text[curr:cut]
                chunk_name = f"{idx:04d}.txt"
                chunk_path = chunk_dir / chunk_name
                io_utils.write_atomic(chunk_path, part)
                chunks_list.append(str(Path(rel_path) / chunk_name).replace("\\", "/"))

                idx += 1
                curr = cut

        out_manifest["files"][rel_path] = {
            "chunks": chunks_list,
            "sha256_full": sha_full,
            "chunk_size": chunk_size,
            "total_len": total_len,
        }

    return out_manifest


# -----------------------------------------------------------------------------
# 8. Token Savings Estimation
# -----------------------------------------------------------------------------
def estimate_savings(
    original_contents: Dict[str, str],
    llm_ready: Dict[str, str],
    mapping_size: int = 0,
    tok: Optional[tokenizer.BaseTokenizer] = None,
    chars_per_token: Optional[float] = None,
    protocol_tokens: int = 0,
) -> Dict[str, Any]:
    """
    Computes token and character savings metrics in pure ASCII notation:
        net_tokens_saved = original_tokens - (compressed_tokens + mapping_tokens + protocol_tokens)
        net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
    """
    orig_total_chars = sum(len(v) for v in original_contents.values())
    new_total_chars = sum(len(v) for v in llm_ready.values())

    gross_saved_chars = orig_total_chars - new_total_chars
    gross_saved_pct = (
        ((gross_saved_chars) * 100.0) / (orig_total_chars) if orig_total_chars > 0 else 0.0
    )

    net_saved_chars = orig_total_chars - (new_total_chars + mapping_size)
    net_saved_pct = (
        ((net_saved_chars) * 100.0) / (orig_total_chars) if orig_total_chars > 0 else 0.0
    )

    if tok is not None:
        orig_tokens_est = sum(tok.count(v) for v in original_contents.values())
        new_tokens_est = sum(tok.count(v) for v in llm_ready.values())
        mapping_tokens_est = (mapping_size + 3) // 4 if mapping_size > 0 else 0
    elif chars_per_token is not None and chars_per_token > 0:
        orig_tokens_est = (
            int(round(orig_total_chars / chars_per_token)) if orig_total_chars > 0 else 0
        )
        new_tokens_est = (
            int(round(new_total_chars / chars_per_token)) if new_total_chars > 0 else 0
        )
        mapping_tokens_est = (
            int(round(mapping_size / chars_per_token)) if mapping_size > 0 else 0
        )
    else:
        default_tok = tokenizer.get_tokenizer("heuristic")
        orig_tokens_est = sum(default_tok.count(v) for v in original_contents.values())
        new_tokens_est = sum(default_tok.count(v) for v in llm_ready.values())
        mapping_tokens_est = (mapping_size + 3) // 4 if mapping_size > 0 else 0

    net_saved_tokens = orig_tokens_est - (
        new_tokens_est + mapping_tokens_est + protocol_tokens
    )

    return {
        "orig_total": orig_total_chars,
        "new_total": new_total_chars,
        "mapping_size": mapping_size,
        "saved_chars": gross_saved_chars,
        "saved_pct": round(gross_saved_pct, 2),
        "net_saved_chars": net_saved_chars,
        "net_saved_pct": round(net_saved_pct, 2),
        "orig_tokens_est": orig_tokens_est,
        "new_tokens_est": new_tokens_est,
        "mapping_tokens_est": mapping_tokens_est,
        "protocol_tokens": protocol_tokens,
        "net_saved_tokens": net_saved_tokens,
    }

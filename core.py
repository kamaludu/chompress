#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: core.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Core pipeline and utilities optimized for large files and strict net token economy:
- scan_files: Scan directory or file-list with optional exclusion of binary files.
- load_contents: Load text files into memory.
- strip_empty_lines_by_extension: Optional lossy preprocessing stripping empty lines.
- find_repetitions: Memory-efficient substring and block repetition detector (P2.6, P2.7).
- select_replacements: Greedy selection with true net saving formula preventing negative compression.
- apply_placeholders: In-place text substitution and reverse_map creation without redundant hashing.
- extract_mapping_for_files: Minimal flat dictionary export (token -> content) without metadata bloat.
- roundtrip_check: Exact verification ensuring recon == target for all files (P0.1).
- build_manifest: Generate compact file and placeholder manifest via O(1) lookups.
- write_reverse_map: Atomic write of the full substitution registry.
- write_mapping_subset: Atomic write of the reduced flat subset dictionary.
- chunk_outputs: Boundary-aware atomic chunker preventing split tokens and breaking on newlines (P0.2).
- estimate_savings: Character, net mapping payload, and LLM token savings calculation (P3.8).
"""

import bisect
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import io_utils

# -------------------------
# Documentative Type Hints
# -------------------------
# FileMeta: {"path": str, "size": int, "sha256": str}
# Candidate: {"id_hash": str, "type": "substring"|"block", "content": str,
#             "occurrences": [{"path": str, "start": int, "end": int}]}
# Replacement: {"id": str, "type": str, "placeholder": str, "content": str,
#               "occurrences": [{"path": str, "start": int, "end": int}]}


# -------------------------
# File Scanning and Loading
# -------------------------
def scan_files(input_path: str, exclude_pointless: bool = True) -> List[Dict[str, Any]]:
    """
    Scan files under input_path and return file metadata records.
    Excludes common binary and unnecessary extensions by default (exclude_pointless=True).
    Pass exclude_pointless=False to include all files.
    """
    default_exclude_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".ttf", ".woff", ".woff2",
        ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".bin", ".class", ".o", ".a", ".jar",
        ".mp3", ".mp4", ".mov", ".avi", ".webm", ".ogg", ".wav", ".7z", ".rar", ".iso",
        ".db", ".sqlite", ".bak", ".swp", ".tmp", ".lock"
    }

    p = Path(input_path)
    files: List[Path] = []
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            # Skip hidden files and directories (names starting with a dot)
            if f.name.startswith("."):
                continue
            if f.is_file():
                files.append(f)
    elif p.is_file():
        files.append(p)
    else:
        # File list format: each line represents a file path
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
            # Skip files that cannot be read or hashed
            continue
        metas.append(
            {
                "path": str(f.resolve()),
                "size": f.stat().st_size,
                "sha256": sha,
            }
        )
    if not metas:
        raise RuntimeError("No valid files found in input")
    return metas


def load_contents(file_metas: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Load text contents of scanned files into a dictionary mapping path -> text.
    """
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
    contents: Dict[str, str], preserve_exts: Optional[Set[str]] = None
) -> Dict[str, str]:
    """
    Remove lines containing only whitespace/tabs from contents,
    preserving empty lines for specified documentation extensions.

    Args:
        contents: Dict mapping file paths to text contents.
        preserve_exts: Set of lowercase file extensions (with dot) to preserve.

    Returns:
        New dict with empty lines stripped where applicable.
    """
    if preserve_exts is None:
        preserve_exts = {".md", ".txt", ".rst", ".html", ".tex", ".adoc", ".org"}

    new: Dict[str, str] = {}
    for path, text in contents.items():
        ext = Path(path).suffix.lower()
        if ext in preserve_exts:
            new[path] = text
            continue

        lines = text.splitlines(keepends=True)
        kept = [ln for ln in lines if ln.strip() != ""]
        new[path] = "".join(kept)
    return new


# -------------------------
# Repetition Analysis (P1.4, P2.6, P2.7)
# -------------------------
def find_repetitions(
    contents: Dict[str, str],
    L_min: int,
    N_min: int,
    B_min_lines: int,
    B_max_lines: int,
    L_max: int = 2000,
) -> List[Dict[str, Any]]:
    """
    Find repeated substrings and multi-line blocks across all loaded file contents.
    Optimized for scalability on large files.
    """
    substring_candidates = _find_substring_candidates(contents, L_min, N_min, L_max)
    block_candidates = _find_block_candidates(contents, B_min_lines, B_max_lines)
    candidates: List[Dict[str, Any]] = []
    candidates.extend(substring_candidates)
    candidates.extend(block_candidates)
    return candidates


def _find_substring_candidates(
    contents: Dict[str, str], L_min: int, N_min: int, L_max: int
) -> List[Dict[str, Any]]:
    """
    Find repeated substrings using rolling hash with verified left and right expansion (P1.4).
    Uses packed 64-bit integer index (file_id << 32 | offset) to minimize memory overhead (P2.7).
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
        h = (h * base - ord(left) * power + ord(right)) % mod
        return h

    file_paths = list(contents.keys())

    # 1) Build compact rolling hash index over windows of length L_min
    # Hash -> list of packed 64-bit ints ((file_id << 32) | offset)
    index: Dict[int, List[int]] = {}
    for file_id, path in enumerate(file_paths):
        text = contents[path]
        n = len(text)
        if n < L_min:
            continue
        window = text[0:L_min]
        h, power = roll_hash_init(window)
        index.setdefault(h, []).append((file_id << 32) | 0)
        for i in range(1, n - L_min + 1):
            h = roll_hash_next(h, power, text[i - 1], text[i + L_min - 1])
            index.setdefault(h, []).append((file_id << 32) | i)

    candidates: Dict[str, Dict[str, Any]] = {}

    # 2) Process hash groups with preliminary equality check and formal expansion
    for h, packed_occs in index.items():
        if len(packed_occs) < N_min:
            continue

        # Preliminary verification: group occurrences by exact window text to avoid hash collisions
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

            # Select the first occurrence as canonical seed
            seed_path, seed_start = group_occs[0]
            seed_text = contents[seed_path]

            # Measure maximal left and right expansion for each occurrence against the seed
            per_occ_expansion: List[Tuple[str, int, int, int]] = []
            for path, start in group_occs:
                t = contents[path]

                # Left expansion invariant:
                # t[start - 1 - k] == seed_text[seed_start - 1 - k]
                k_left = 0
                while (
                    start - 1 - k_left >= 0
                    and seed_start - 1 - k_left >= 0
                    and t[start - 1 - k_left] == seed_text[seed_start - 1 - k_left]
                ):
                    k_left += 1
                    if L_min + k_left >= L_max:
                        break

                # Right expansion invariant:
                # t[start + L_min + k_right] == seed_text[seed_start + L_min + k_right]
                k_right = 0
                while (
                    start + L_min + k_right < len(t)
                    and seed_start + L_min + k_right < len(seed_text)
                    and t[start + L_min + k_right] == seed_text[seed_start + L_min + k_right]
                ):
                    k_right += 1
                    if L_min + k_left + k_right >= L_max:
                        break

                per_occ_expansion.append((path, start, k_left, k_right))

            # Determine the common expansion valid for all occurrences in this group
            common_left = min(item[2] for item in per_occ_expansion)
            common_right = min(item[3] for item in per_occ_expansion)

            if L_min + common_left + common_right > L_max:
                common_right = max(0, L_max - L_min - common_left)

            # Extract the canonical extended content
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

            # Register exact non-redundant occurrences
            for path, start, _, _ in per_occ_expansion:
                occ_s = start - common_left
                occ_e = start + L_min + common_right
                occ_key = (path, occ_s, occ_e)
                if occ_key not in cand["_seen_occs"]:
                    cand["_seen_occs"].add(occ_key)
                    cand["occurrences"].append({"path": path, "start": occ_s, "end": occ_e})

    # Cleanup internal temporary sets and filter by minimum occurrences
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
    Find repeated multi-line blocks with O(1) line offset memoization (P2.6).
    Performs line splitting once per file and avoids storing duplicate block strings.
    """
    sizes: List[int] = []
    if B_min_lines <= B_max_lines:
        sizes = [B_min_lines]
        mid = (B_min_lines + B_max_lines) // 2
        if mid != B_min_lines and mid <= B_max_lines:
            sizes.append(mid)
        if B_max_lines not in sizes:
            sizes.append(B_max_lines)
    sizes = sorted(set(sizes))

    file_paths = list(contents.keys())

    # Precompute line partitions and cumulative character offsets once per file: O(lines) total time
    file_lines: List[List[str]] = []
    file_offsets: List[List[int]] = []

    for path in file_paths:
        lines = contents[path].splitlines(keepends=True)
        offsets = [0]
        curr = 0
        for ln in lines:
            curr += len(ln)
            offsets.append(curr)
        file_lines.append(lines)
        file_offsets.append(offsets)

    # Index: hash -> list of occurrences (file_id, line_index, line_count)
    index: Dict[str, List[Tuple[int, int, int]]] = {}

    for file_id, lines in enumerate(file_lines):
        total_lines = len(lines)
        for size in sizes:
            if size <= 0 or size > total_lines:
                continue
            for i in range(0, total_lines - size + 1):
                block = "".join(lines[i : i + size])
                h = hashlib.sha256(block.encode("utf-8")).hexdigest()
                index.setdefault(h, []).append((file_id, i, size))

    candidates: List[Dict[str, Any]] = []
    for h, occs in index.items():
        if len(occs) < 2:
            continue

        # Canonical block content derived from first occurrence via O(1) offsets
        seed_file_id, seed_li, seed_sz = occs[0]
        seed_start = file_offsets[seed_file_id][seed_li]
        seed_end = file_offsets[seed_file_id][seed_li + seed_sz]
        content = contents[file_paths[seed_file_id]][seed_start:seed_end]

        cand = {
            "id_hash": h,
            "type": "block",
            "content": content,
            "occurrences": [],
        }

        for file_id, li, sz in occs:
            path = file_paths[file_id]
            start = file_offsets[file_id][li]
            end = file_offsets[file_id][li + sz]
            cand["occurrences"].append({"path": path, "start": start, "end": end})

        candidates.append(cand)

    return candidates


# -------------------------
# Replacement Selection (True Net Saving Formula)
# -------------------------
def _has_interval_overlap(intervals: List[Tuple[int, int]], s: int, e: int) -> bool:
    """
    Check in O(log K) whether [s, e) overlaps with any disjoint interval in intervals.
    Assumes intervals is sorted by end (and start).
    """
    if not intervals:
        return False
    idx = bisect.bisect_right(intervals, s, key=lambda x: x[1])
    if idx < len(intervals) and intervals[idx][0] < e:
        return True
    return False


def select_replacements(
    candidates: List[Dict[str, Any]],
    placeholder_fmt_sub: str = "§§s{:03d}§§",
    placeholder_fmt_blk: str = "§§b{:03d}§§",
    min_total_saving: int = 100,
) -> List[Dict[str, Any]]:
    """
    Greedy replacement selection using true net saving:
      net_saving = N * (len(content) - ph_len) - (len(content) + ph_len + 10)
    Accounts for the exact cost of defining the placeholder in mapping_subset.json,
    guaranteeing that replacements causing negative net token compression are rejected.
    """
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for c in candidates:
        content = c["content"]
        occs = c["occurrences"]
        if len(occs) < 2:
            continue
        if c["type"] == "substring":
            ph_len = len(placeholder_fmt_sub.format(1))
        else:
            ph_len = len(placeholder_fmt_blk.format(1))

        L = len(content)
        N = len(occs)
        # True net saving = text reduction - mapping definition overhead
        net_saving = N * (L - ph_len) - (L + ph_len + 10)
        if net_saving >= min_total_saving:
            scored.append((net_saving, c))

    # Sort by initial net saving descending, then content length descending, then id_hash
    scored.sort(key=lambda x: (-x[0], -len(x[1]["content"]), x[1]["id_hash"]))

    # Occupied intervals per file path: path -> sorted List of (start, end)
    occupied: Dict[str, List[Tuple[int, int]]] = {}
    replacements: List[Dict[str, Any]] = []
    sid = 1
    bid = 1

    for initial_saving, c in scored:
        content = c["content"]
        is_sub = (c["type"] == "substring")
        ph_len = len(placeholder_fmt_sub.format(sid) if is_sub else placeholder_fmt_blk.format(bid))
        L = len(content)

        # Filter occurrences individually against occupied spans and self-overlaps
        valid_occs: List[Dict[str, Any]] = []
        candidate_occupied_per_file: Dict[str, List[Tuple[int, int]]] = {}

        for o in c["occurrences"]:
            path = o["path"]
            s = o["start"]
            e = o["end"]

            # Check overlap with previously committed replacements
            if _has_interval_overlap(occupied.get(path, []), s, e):
                continue

            # Check overlap with already accepted occurrences of the same candidate
            if _has_interval_overlap(candidate_occupied_per_file.get(path, []), s, e):
                continue

            valid_occs.append(o)
            bisect.insort(candidate_occupied_per_file.setdefault(path, []), (s, e), key=lambda x: x[1])

        # Recalculate true net savings after collision filtering
        N_valid = len(valid_occs)
        if N_valid < 2:
            continue

        recomputed_net_saving = N_valid * (L - ph_len) - (L + ph_len + 10)
        if recomputed_net_saving < min_total_saving:
            continue

        # Candidate accepted: assign placeholder and commit intervals
        if is_sub:
            pid = f"S:{sid:03d}"
            placeholder = placeholder_fmt_sub.format(sid)
            sid += 1
        else:
            pid = f"B:{bid:03d}"
            placeholder = placeholder_fmt_blk.format(bid)
            bid += 1

        rep = {
            "id": pid,
            "type": c["type"],
            "placeholder": placeholder,
            "content": content,
            "occurrences": valid_occs,
        }
        replacements.append(rep)

        for o in valid_occs:
            path = o["path"]
            bisect.insort(occupied.setdefault(path, []), (o["start"], o["end"]), key=lambda x: x[1])

    return replacements


# -------------------------
# Placeholder Application
# -------------------------
def apply_placeholders(
    contents: Dict[str, str], replacements: List[Dict[str, Any]]
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Apply replacement placeholders to the provided contents.
    Keys in reverse_map["placeholders"] are the exact textual tokens inserted into files.
    Computes SHA256 and allocates metadata dictionaries only once per unique placeholder.
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
        "metadata": {"tool": "chunk_compress"},
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
            # Validity sanity check
            if s < last or s < 0 or e > len(text) or e <= s:
                continue
            # Content match verification
            actual = text[s:e]
            expected = r.get("content", "")
            if actual != expected:
                continue

            out_parts.append(text[last:s])
            out_parts.append(r["placeholder"])
            last = e

            token = r["placeholder"]
            actual_content = actual

            # Avoid redundant SHA256 hashing and dict creation on repeated occurrences
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

    return llm_ready, reverse_map


def _build_token_map_from_reverse_map(reverse_map: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract a dictionary mapping placeholder token -> original content from reverse_map.
    """
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
    """
    Reconstruct original text by replacing tokens ordered by length descending
    to avoid substring collision issues.
    """
    if not token_map:
        return transformed
    tokens_sorted = sorted(token_map.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in tokens_sorted))
    return pattern.sub(lambda m: token_map[m.group(0)], transformed)


def extract_mapping_for_files(reverse_map: dict, paths: list) -> Dict[str, str]:
    """
    Extract a minimal flat mapping dictionary (token -> content) containing only
    placeholders that occur in the specified paths.
    Eliminates sha256 and length metadata bloat for prompt payload optimization.
    """
    if not isinstance(reverse_map, dict):
        return {}

    norm = [p.strip() for p in (paths or []) if p and p.strip()]
    if not norm:
        return {}

    norm_set = set(norm)
    norm_names = {Path(p).name for p in norm_set}

    placeholders = reverse_map.get("placeholders", {})
    out: Dict[str, str] = {}

    for token, info in placeholders.items():
        if not isinstance(info, dict):
            continue
        occs = info.get("occurrences", [])
        if not occs:
            continue
        matched = False
        for occ in occs:
            occ_path = occ.get("path")
            if not occ_path:
                continue

            # Fast O(1) match checks before suffix iteration
            if occ_path in norm_set:
                matched = True
                break

            occ_name = Path(occ_path).name
            if occ_name in norm_names:
                matched = True
                break

            for p in norm:
                if occ_path.endswith(p):
                    matched = True
                    break
            if matched:
                break

        if not matched:
            continue

        content = info.get("content", "")
        if content is None or content == "":
            continue

        out[token] = content

    return out


# -------------------------
# Exact Roundtrip Check (P0.1)
# -------------------------
def roundtrip_check(
    target_contents: Dict[str, str],
    llm_ready: Dict[str, str],
    reverse_map: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Perform exact string roundtrip check: recon == target_contents[path].

    Validation checks:
      1. Every placeholder used in llm_ready must be declared in reverse_map.
      2. Placeholders declared but unused are logged as warnings.
      3. No unresolved placeholders may remain after reconstruction.
      4. Exact character equality: recon == target_contents[path].
         If mismatch occurs, isolates the first divergent offset and displays context.

    Returns:
        Tuple of (all_passed: bool, details_log: List[str])
    """
    details: List[str] = []
    ok_all = True
    default_placeholder_re = re.compile(r"§§[^§]{1,200}§§")

    # Validate reverse_map structure
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

    # Build token map
    token_map: Dict[str, str] = {}
    token_map_error = None
    try:
        token_map = _build_token_map_from_reverse_map(reverse_map) or {}
        if not isinstance(token_map, dict):
            details.append("Warning: built token_map is not a dict; fallback will be used.")
            token_map = {}
    except Exception as e:
        token_map_error = e
        details.append(f"Warning: error building token_map: {e}; fallback will be used.")

    # Build dynamic token regex from known tokens for accurate scanning
    token_regex = None
    if token_map:
        try:
            token_keys = sorted(
                (k for k in token_map.keys() if isinstance(k, str) and k),
                key=len,
                reverse=True,
            )
            if token_keys:
                token_regex = re.compile("|".join(re.escape(k) for k in token_keys))
        except Exception as e:
            details.append(f"Warning: could not compile token regex: {e}")
            token_regex = None

    def find_placeholders(text: str) -> Set[str]:
        if not isinstance(text, str) or not text:
            return set()
        found: Set[str] = set()
        if token_regex:
            for m in token_regex.finditer(text):
                found.add(m.group(0))
            return found
        return set(default_placeholder_re.findall(text))

    # Identify all placeholders used across compressed texts
    used: Set[str] = set()
    for text in llm_ready.values():
        used.update(find_placeholders(text))

    # Detect placeholders used but not defined
    missing_defs = sorted(used - declared)
    if missing_defs:
        ok_all = False
        details.append(f"ERROR: {len(missing_defs)} placeholder(s) used but not defined in reverse_map:")
        max_list = 20
        for ph in missing_defs[:max_list]:
            details.append(f"  - missing: {ph}")
        if len(missing_defs) > max_list:
            details.append(f"  ... (+ {len(missing_defs) - max_list} more)")

    # Detect declared placeholders never used
    orphans = sorted(declared - used)
    if orphans:
        details.append(f"Warning: {len(orphans)} placeholder(s) declared but never used in files:")
        sample = 10
        for ph in orphans[:sample]:
            details.append(f"  - orphan: {ph}")
        if len(orphans) > sample:
            details.append(f"  ... (+ {len(orphans) - sample} more)")

    # Exact string verification per file
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

        # Check for unresolved residual placeholders
        residuals = find_placeholders(recon)
        if residuals:
            ok_all = False
            details.append(
                f"ERROR: {len(residuals)} unresolved placeholder(s) remain in {path} after reconstruction:"
            )
            for res_ph in sorted(residuals)[:10]:
                details.append(f"  - residual: {res_ph}")

        # Exact equality check
        if recon != target:
            ok_all = False
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

            target_ctx = repr(target[ctx_start:ctx_end_target])
            recon_ctx = repr(recon[ctx_start:ctx_end_recon])

            details.append(
                f"ERROR: Exact content mismatch in {path} at character offset {mismatch_idx} "
                f"(len_target={len_target}, len_recon={len_recon}):"
            )
            details.append(f"  Expected: {target_ctx}")
            details.append(f"  Recon   : {recon_ctx}")
        else:
            details.append(f"OK: Verified 100% exact match for {path} ({len(target)} chars)")

    if token_map_error:
        details.append(f"Note: token_map construction reported an error: {token_map_error}")

    if ok_all:
        details.insert(0, f"EXACT ROUNDTRIP SUCCESS: {len(target_contents)} file(s) verified.")
    else:
        details.insert(0, "EXACT ROUNDTRIP FAILED: Discrepancies detected.")

    return ok_all, details


# -------------------------
# Manifest Generation
# -------------------------
def build_manifest(
    file_metas: List[Dict[str, Any]], reverse_map: Dict[str, Any], input_root: str
) -> Dict[str, Any]:
    """
    Build a compact manifest structure via O(1) lookups:
    {
      "paths": [...],
      "files": [{"i": idx, "sha": sha, "ph": [...]}, ...],
      "ph": {"S:001": {"sha": "...", "len": 120}, ...},
      "v": 1
    }
    """
    root = Path(input_root).resolve()
    metas_sorted = sorted(file_metas, key=lambda m: m["path"])
    paths: List[str] = []
    files: List[Dict[str, Any]] = []
    path_to_idx: Dict[str, int] = {}
    name_to_idx: Dict[str, int] = {}

    for idx, m in enumerate(metas_sorted):
        abs_p = Path(m["path"]).resolve()
        try:
            rel = abs_p.relative_to(root)
            p = str(rel).replace("\\", "/")
        except Exception:
            p = Path(abs_p).name
        paths.append(p)
        path_to_idx[str(abs_p)] = idx
        name_to_idx[abs_p.name] = idx
        files.append({"i": idx, "sha": m.get("sha256", ""), "ph": []})

    # Track placeholders per file via set for O(1) deduplicated insertions
    file_placeholders: List[Set[str]] = [set() for _ in range(len(files))]

    ph_index: Dict[str, Dict[str, Any]] = {}
    placeholders = reverse_map.get("placeholders", {})
    for pid, info in placeholders.items():
        ph_index[pid] = {"sha": info.get("sha256", ""), "len": info.get("length", 0)}

        for occ in info.get("occurrences", []):
            occ_path = occ.get("path")
            if not occ_path:
                continue

            resolved_occ = str(Path(occ_path).resolve())
            idx = path_to_idx.get(resolved_occ)
            if idx is None:
                idx = name_to_idx.get(Path(occ_path).name)

            if idx is not None:
                file_placeholders[idx].add(pid)

    # Assign sorted placeholder list to file entries
    for idx, ph_set in enumerate(file_placeholders):
        files[idx]["ph"] = sorted(ph_set)

    manifest = {"paths": paths, "files": files, "ph": ph_index, "v": 1}
    return manifest


def write_reverse_map(reverse_map: dict, out_path: Any) -> None:
    """
    Write full reverse_map to disk atomically.
    """
    p = Path(out_path)
    io_utils.ensure_dir(p.parent)
    io_utils.write_json_atomic(p, reverse_map, ensure_ascii=False, indent=2)


def write_mapping_subset(reverse_map: dict, paths: list, out_path: Any) -> None:
    """
    Extract minimal flat mapping subset for given paths and write to disk atomically.
    """
    p = Path(out_path)
    subset = extract_mapping_for_files(reverse_map, paths or [])
    io_utils.ensure_dir(p.parent)
    io_utils.write_json_atomic(p, subset, ensure_ascii=False, indent=2)


# -------------------------
# Boundary-Aware Chunker (P0.2)
# -------------------------
def chunk_outputs(
    llm_ready: Dict[str, str],
    output_dir: Path,
    chunk_size: int,
    input_root: Optional[Path] = None,
    reverse_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Split transformed texts into boundary-aware chunks:
    1. Prohibits cutting strictly inside placeholder boundaries [ph_start, ph_end).
    2. Backtracks to the nearest newline preceding chunk_size whenever possible.
    3. Handles tokens or single lines larger than chunk_size safely without stalling.

    Returns:
        Structured chunk manifest with file metadata and chunk relative paths.
    """
    out_manifest: Dict[str, Any] = {"files": {}, "chunks_dir": "chunks", "v": 1}
    chunks_root = Path(output_dir) / out_manifest["chunks_dir"]
    io_utils.ensure_dir(chunks_root)

    # Collect active placeholder tokens from reverse_map
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
        token_pattern = re.compile(r"§§[^§]{1,200}§§")

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
            # Map of protected token intervals [start, end)
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

                    # Prohibit cutting inside any protected placeholder span
                    for s_start, s_end in protected_spans:
                        if s_start < target_cut < s_end:
                            cut = s_start
                            break
                        if s_start >= target_cut:
                            break

                    # Backtrack to the last newline within (curr, cut]
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

                    # Anti-stall guard: ensure progression even with huge lines/tokens
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


# -------------------------
# Savings and LLM Token Estimation (P3.8)
# -------------------------
def estimate_savings(
    original_contents: Dict[str, str],
    llm_ready: Dict[str, str],
    mapping_size: int = 0,
    chars_per_token: float = 4.0,
) -> Dict[str, Any]:
    """
    Calculate character compression savings, net savings factoring mapping overhead,
    and LLM token estimates (P3.8).

    Formulas:
      gross_saved_chars = orig_total - new_total
      net_saved_chars = orig_total - (new_total + mapping_size)
      net_saved_pct = (net_saved_chars / orig_total) * 100.0
      token_estimate = round(chars / chars_per_token)
    """
    orig_total = sum(len(v) for v in original_contents.values())
    new_total = sum(len(v) for v in llm_ready.values())

    gross_saved_chars = orig_total - new_total
    gross_saved_pct = (gross_saved_chars / orig_total * 100.0) if orig_total > 0 else 0.0

    net_saved_chars = orig_total - (new_total + mapping_size)
    net_saved_pct = (net_saved_chars / orig_total * 100.0) if orig_total > 0 else 0.0

    # Token estimation (conventional average: 4.0 characters per token)
    orig_tokens_est = int(round(orig_total / chars_per_token)) if orig_total > 0 else 0
    new_tokens_est = int(round(new_total / chars_per_token)) if new_total > 0 else 0
    mapping_tokens_est = int(round(mapping_size / chars_per_token)) if mapping_size > 0 else 0
    net_saved_tokens = orig_tokens_est - (new_tokens_est + mapping_tokens_est)

    return {
        "orig_total": orig_total,
        "new_total": new_total,
        "mapping_size": mapping_size,
        "saved_chars": gross_saved_chars,
        "saved_pct": round(gross_saved_pct, 2),
        "net_saved_chars": net_saved_chars,
        "net_saved_pct": round(net_saved_pct, 2),
        "orig_tokens_est": orig_tokens_est,
        "new_tokens_est": new_tokens_est,
        "mapping_tokens_est": mapping_tokens_est,
        "net_saved_tokens": net_saved_tokens,
    }

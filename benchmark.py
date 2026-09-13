#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: benchmark.py (P0 & Alphabet Optimizer Evaluation Harness)
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
A/B ablation benchmark harness measuring real LLM token economy for P0:
- Compares 4-token baseline (__s1__), 3-token brackets («1»), 2-token prefix (^1),
  and 1-token atomic CJK ideographs (一, 丁).
- Measures JSON vs Delimited vs Positional zero-key mapping.
- Isolates body tokens, mapping tokens, protocol tokens, net saved tokens,
  and net compression ratio.
- Verifies exact lossless roundtrip for each configuration.
- Outputs a clean ASCII report table and optional JSON export.

Mathematical token model (pure ASCII notation):
net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
"""

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import core
import io_utils
import mapping as mapping_module
import placeholders as ph_module
import tokenizer


def run_single_p0_benchmark(
    config_name: str,
    raw_contents: Dict[str, str],
    tok: tokenizer.BaseTokenizer,
    ph_style: str,
    map_format: str,
    preset_params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes a single compression pass under a specific P0 configuration,
    measuring exact token counts for body, dictionary payload, and protocol header.
    """
    start_time = time.perf_counter()

    # 1. Measure raw input tokens
    orig_tokens = sum(tok.count(text) for text in raw_contents.values())
    all_raw_text = "".join(raw_contents.values())

    # 2. Configure P0 engines
    ph_engine = ph_module.PlaceholderEngine(ph_style, tok=tok)
    ph_engine.auto_calibrate(all_raw_text)

    map_serializer = mapping_module.get_mapping_serializer(map_format)

    # 3. Candidate repetition detection
    candidates = core.find_repetitions(
        raw_contents,
        L_min=preset_params.get("L_min", 14),
        N_min=preset_params.get("N_min", 2),
        B_min_lines=preset_params.get("B_min_lines", 2),
        B_max_lines=preset_params.get("B_max_lines", 10),
        L_max=preset_params.get("L_max", 2000),
    )

    # 4. Frequency-weighted replacement selection using target serializer
    replacements = core.select_replacements(
        candidates,
        all_raw_text=all_raw_text,
        min_total_saving=preset_params.get("min_total_saving", 2),
        tok=tok,
        ph_engine=ph_engine,
        map_serializer=map_serializer,
    )

    # 5. Apply placeholders and record alphabet metadata
    llm_ready, reverse_map = core.apply_placeholders(
        raw_contents, replacements, ph_engine=ph_engine
    )

    # 6. Extract flat mapping subset and serialize (Single-File First)
    is_single = len(raw_contents) == 1
    file_paths = ["."] if is_single else [Path(p).name for p in raw_contents.keys()]
    subset_dict = core.extract_mapping_for_files(reverse_map, file_paths)

    ph_meta = reverse_map.get("ph_meta", {})
    mapping_payload, protocol_header = map_serializer.serialize(
        subset_dict, raw_corpus=all_raw_text, ph_meta=ph_meta
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # 7. Exact token measurements
    comp_tokens = sum(tok.count(t) for t in llm_ready.values())
    map_tokens = tok.count(mapping_payload) if subset_dict else 0
    proto_tokens = tok.count(protocol_header) if subset_dict else 0

    net_tokens = orig_tokens - (comp_tokens + map_tokens + proto_tokens)
    net_pct = (
        ((net_tokens) * 100.0) / (orig_tokens) if orig_tokens > 0 else 0.0
    )

    # 8. Exact integrity roundtrip verification
    ok_roundtrip, _ = core.roundtrip_check(raw_contents, llm_ready, reverse_map)

    return {
        "config": config_name,
        "ph_style": ph_engine.style_name,
        "map_format": map_serializer.name,
        "orig_tokens": orig_tokens,
        "comp_tokens": comp_tokens,
        "map_tokens": map_tokens,
        "proto_tokens": proto_tokens,
        "net_tokens": net_tokens,
        "net_pct": round(net_pct, 2),
        "time_ms": round(elapsed_ms, 1),
        "replacements": len(replacements),
        "roundtrip_ok": ok_roundtrip,
    }


def get_p0_ablation_matrix() -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """
    Returns the P0 ablation matrix evaluating the token economics ladder:
    (name, placeholder_style, mapping_format, preset_params)
    """
    default_params = {
        "L_min": 14,
        "N_min": 2,
        "B_min_lines": 2,
        "B_max_lines": 10,
        "min_total_saving": 2,
    }
    return [
        (
            "1. Baseline (__s1__ + JSON)",
            "classic",
            "json",
            default_params,
        ),
        (
            "2. Delimited Map (__s1__ + Delim)",
            "classic",
            "delimited",
            default_params,
        ),
        (
            "3. Guillemet JSON («1» + JSON)",
            "guillemet",
            "json",
            default_params,
        ),
        (
            "4. Guillemet Pos («1» + Pos)",
            "guillemet",
            "positional",
            default_params,
        ),
        (
            "5. Compact Prefix (^1 + Pos)",
            "prefix_compact",
            "positional",
            default_params,
        ),
        (
            "6. 1-Token Atomic (CJK + Pos)",
            "single_token",
            "positional",
            default_params,
        ),
        (
            "7. Full Auto-Optimized (Auto + Auto)",
            "auto",
            "auto",
            default_params,
        ),
    ]


def print_p0_ascii_table(
    results: List[Dict[str, Any]], tokenizer_name: str
) -> None:
    """Renders benchmark results in a clean, human-readable ASCII table."""
    sep_len = 118
    header_title = f"P0 TOKEN ECONOMY COMPARATIVE REPORT (Tokenizer: {tokenizer_name})"
    print("\n" + "=" * sep_len)
    print(header_title)
    print("=" * sep_len)

    header = (
        f"{'Configuration':<35} | "
        f"{'Input':>7} | "
        f"{'Body':>7} | "
        f"{'Map':>6} | "
        f"{'Proto':>5} | "
        f"{'Net Saved':>9} | "
        f"{'Net %':>7} | "
        f"{'Time(ms)':>8} | "
        f"{'Status':>6}"
    )
    print(header)
    print("-" * sep_len)

    for r in results:
        status = "PASS" if r["roundtrip_ok"] else "FAIL"
        line = (
            f"{r['config']:<35} | "
            f"{r['orig_tokens']:>7d} | "
            f"{r['comp_tokens']:>7d} | "
            f"{r['map_tokens']:>6d} | "
            f"{r['proto_tokens']:>5d} | "
            f"{r['net_tokens']:>9d} | "
            f"{r['net_pct']:>6.2f}% | "
            f"{r['time_ms']:>8.1f} | "
            f"{status:>6}"
        )
        print(line)

    print("=" * sep_len + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="P0 Token Economy Comparative Benchmark (Placeholder & Mapping Evaluation)."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="Path to file or directory to benchmark"
    )
    parser.add_argument(
        "--tokenizer",
        default="auto",
        help="Tokenizer: 'auto', 'cl100k_base', 'o200k_base', 'hf:<name>', or 'heuristic'",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to export full benchmark results as JSON",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: input path does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)

    tok = tokenizer.get_tokenizer(args.tokenizer)
    is_approx = isinstance(tok, tokenizer.HeuristicBackend)
    tok_display = f"{tok.name} (HEURISTIC APPROXIMATION)" if is_approx else tok.name

    file_metas = core.scan_files(str(input_path))
    raw_contents = core.load_contents(file_metas)

    total_chars = sum(len(t) for t in raw_contents.values())
    target_type = "single file" if input_path.is_file() else f"{len(raw_contents)} file(s)"
    print(f"Target: {input_path} ({target_type}, {total_chars} characters total).")
    print(f"Active Tokenizer: {tok_display}")
    print("Running P0 & Alphabet Optimizer ablation suite...\n")

    matrix = get_p0_ablation_matrix()
    results: List[Dict[str, Any]] = []

    for name, ph_s, map_f, params in matrix:
        res = run_single_p0_benchmark(
            config_name=name,
            raw_contents=raw_contents,
            tok=tok,
            ph_style=ph_s,
            map_format=map_f,
            preset_params=params,
        )
        results.append(res)

    print_p0_ascii_table(results, tok_display)

    if args.json_out:
        out_p = Path(args.json_out)
        io_utils.write_json_atomic(out_p, results, indent=2)
        print(f"Benchmark results exported to: {out_p}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: cli.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Pipeline orchestrator supporting presets with granular parameter overrides,
boundary-aware chunking, exact roundtrip verification, and net token savings reporting.
"""

import argparse
import json
from pathlib import Path
import sys
import core
import io_utils

VERSION = "1.0.0"

# -------------------------
# Presets Configuration
# -------------------------
PRESETS = {
    "conservative": {
        "L_min": 64,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 5,
        "B_max_lines": 20,
        "min_total_saving": 100,
        "desc": "Safe default for large projects; replaces only long substrings and large blocks.",
    },
    "code-max": {
        "L_min": 32,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 3,
        "B_max_lines": 12,
        "min_total_saving": 25,
        "desc": "Optimized for codebases; compresses repeated functions, imports, and boilerplate.",
    },
    "text-balanced": {
        "L_min": 40,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 2,
        "B_max_lines": 8,
        "min_total_saving": 30,
        "desc": "Balanced profile for markdown docs and prose; keeps mapping dictionary compact.",
    },
    "aggressive": {
        "L_min": 20,
        "L_max": 2000,
        "N_min": 3,
        "B_min_lines": 2,
        "B_max_lines": 6,
        "min_total_saving": 15,
        "desc": "Aggressive deduplication for short recurring phrases (requires at least 3 occurrences).",
    },
}

EPILOG_EXAMPLES = """
----------------------------------------
PRESET PROFILES:
  conservative   L_min=64, L_max=2000, N_min=2, B_min=5, B_max=20, min_saving=100 (default)
  code-max       L_min=32, L_max=2000, N_min=2, B_min=3, B_max=12, min_saving=25  (recommended for code)
  text-balanced  L_min=40, L_max=2000, N_min=2, B_min=2, B_max=8,  min_saving=30  (recommended for docs)
  aggressive     L_min=20, L_max=2000, N_min=3, B_min=2, B_max=6,  min_saving=15  (maximum compression)

READY-TO-USE EXAMPLES:
  # 1. Compress a codebase using the code-max preset with integrity check:
  python3 cli.py -i ./my_project -o out --preset code-max --verify-roundtrip

  # 2. Compress a single Markdown or documentation file:
  python3 cli.py -i ./docs/spec.md -o out --preset text-balanced --verify-roundtrip

  # 3. Use a preset but override specific parameters (e.g. custom substring range):
  python3 cli.py -i ./my_project -o out --preset code-max --L_min 24 --L_max 1500 --min_total_saving 20

  # 4. Pure lossless compression (preserving all empty lines across every file):
  python3 cli.py -i ./my_project -o out_lossless --keep-empty-lines --verify-roundtrip

  # 5. Split large files into safe, boundary-aware chunks for LLM context limits:
  python3 cli.py -i ./my_file.py -o out_chunks --chunk-output --chunk-size 16000 --verify-roundtrip
----------------------------------------
"""


def parse_args():
    p = argparse.ArgumentParser(
        description="Local reversible text & code compressor optimized for LLM token economy.",
        epilog=EPILOG_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Version Flag
    p.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} (GPL-3.0-or-later)",
        help="Show program version number and exit",
    )

    # 1. Input & Output Paths
    g_io = p.add_argument_group("Input & Output Options")
    g_io.add_argument("--input", "-i", required=True, help="Input directory, single file, or file-list")
    g_io.add_argument("--output", "-o", default="compressed_output", help="Output directory (default: 'compressed_output')")
    g_io.add_argument(
        "--keep-empty-lines",
        action="store_true",
        help="Preserve empty lines across all files (pure lossless mode). Default strips empty lines from code files.",
    )
    g_io.add_argument(
        "--include-pointless",
        action="store_true",
        help="Do NOT exclude binary or non-text extensions during scanning (default: exclude)",
    )

    # 2. Preset & Algorithmic Tuning
    g_tuning = p.add_argument_group("Preset & Algorithmic Tuning (Freely Adjustable)")
    g_tuning.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default="conservative",
        help="Select a base tuning profile: 'conservative', 'code-max', 'text-balanced', or 'aggressive' (default: conservative)",
    )
    g_tuning.add_argument(
        "--L_min",
        type=int,
        default=None,
        help="Minimum substring character length (overrides preset value)",
    )
    g_tuning.add_argument(
        "--L_max",
        type=int,
        default=None,
        help="Maximum substring character length to expand (default: 2000, overrides preset value)",
    )
    g_tuning.add_argument(
        "--N_min",
        type=int,
        default=None,
        help="Minimum occurrences required for a substring candidate (overrides preset value)",
    )
    g_tuning.add_argument(
        "--B_min_lines",
        type=int,
        default=None,
        help="Minimum number of lines for a multi-line block candidate (overrides preset value)",
    )
    g_tuning.add_argument(
        "--B_max_lines",
        type=int,
        default=None,
        help="Maximum number of lines for a multi-line block candidate (overrides preset value)",
    )
    g_tuning.add_argument(
        "--min_total_saving",
        type=int,
        default=None,
        help="Minimum net character savings required to accept a replacement (overrides preset value)",
    )

    # 3. Token Placeholders Formatting
    g_tokens = p.add_argument_group("Placeholder Formatting")
    g_tokens.add_argument(
        "--placeholder-sub",
        default="§§s{:03d}§§",
        help="Formatting pattern for substring placeholders (default: '§§s{:03d}§§')",
    )
    g_tokens.add_argument(
        "--placeholder-blk",
        default="§§b{:03d}§§",
        help="Formatting pattern for block placeholders (default: '§§b{:03d}§§')",
    )

    # 4. Boundary-Aware Chunking
    g_chunk = p.add_argument_group("Chunking Options")
    g_chunk.add_argument(
        "--chunk-output",
        action="store_true",
        help="Generate boundary-aware chunks under OUT_DIR/chunks/ (prevents cutting inside placeholders)",
    )
    g_chunk.add_argument(
        "--chunk-size",
        type=int,
        default=16000,
        help="Maximum chunk character size when --chunk-output is enabled (default: 16000)",
    )

    # 5. Verification & Exports
    g_export = p.add_argument_group("Verification & Export Options")
    g_export.add_argument(
        "--verify-roundtrip",
        action="store_true",
        help="Perform exact string equality verification (recon == target) and report failures",
    )
    g_export.add_argument(
        "--export-manifest",
        action="store_true",
        help="Export compact manifest.json for processed files and checksums",
    )
    g_export.add_argument(
        "--no-export-mapping",
        nargs="?",
        const="",
        default=None,
        help=(
            "Control export of mapping_subset.json: omit flag to export all; provide without value to disable export; "
            "provide comma-separated paths to exclude specific files."
        ),
    )

    args = p.parse_args()

    # Resolve preset configuration and apply explicit user overrides
    preset_cfg = PRESETS[args.preset]
    if args.L_min is None:
        args.L_min = preset_cfg["L_min"]
    if args.L_max is None:
        args.L_max = preset_cfg["L_max"]
    if args.N_min is None:
        args.N_min = preset_cfg["N_min"]
    if args.B_min_lines is None:
        args.B_min_lines = preset_cfg["B_min_lines"]
    if args.B_max_lines is None:
        args.B_max_lines = preset_cfg["B_max_lines"]
    if args.min_total_saving is None:
        args.min_total_saving = preset_cfg["min_total_saving"]

    return args


def main():
    args = parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Invalid input path: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Establish root for relative path computations (parent folder if input is a single file)
    input_root = input_path.parent if input_path.is_file() else input_path

    output_dir = Path(args.output)
    io_utils.ensure_dir(output_dir)

    try:
        # 1) Scan input files
        file_metas = core.scan_files(
            str(input_path), exclude_pointless=not getattr(args, "include_pointless", False)
        )

        # 2) Load contents into memory
        contents = core.load_contents(file_metas)

        # 2b) Token saving rule: strip empty lines from non-documentation formats
        if not args.keep_empty_lines:
            try:
                contents = core.strip_empty_lines_by_extension(contents)
            except Exception as e:
                print(f"Error applying strip_empty_lines_by_extension: {e}", file=sys.stderr)
                sys.exit(1)

        # 3) Repetition analysis (substrings + blocks)
        candidates = core.find_repetitions(
            contents,
            L_min=args.L_min,
            N_min=args.N_min,
            B_min_lines=args.B_min_lines,
            B_max_lines=args.B_max_lines,
            L_max=args.L_max,
        )

        # 4) Replacement selection with true net saving formula
        replacements = core.select_replacements(
            candidates,
            placeholder_fmt_sub=args.placeholder_sub,
            placeholder_fmt_blk=args.placeholder_blk,
            min_total_saving=args.min_total_saving,
        )

        # 5) Apply placeholders
        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)

        # 6) Write transformed outputs and complete reverse_map.json
        _write_outputs(llm_ready, reverse_map, output_dir, input_root)

        # 6b) Export minimal flat mapping subset per file (LLM-ready)
        files = []
        no_export_val = getattr(args, "no_export_mapping", None)
        if no_export_val is None:
            for m in file_metas:
                try:
                    rel = Path(m["path"]).resolve().relative_to(input_root).as_posix()
                    if rel == ".":
                        rel = Path(m["path"]).name
                except Exception:
                    rel = Path(m["path"]).name
                files.append(rel)
        else:
            if no_export_val == "":
                files = []
            else:
                excludes = [s.strip() for s in str(no_export_val).split(",") if s.strip()]
                for m in file_metas:
                    try:
                        rel = Path(m["path"]).resolve().relative_to(input_root).as_posix()
                        if rel == ".":
                            rel = Path(m["path"]).name
                    except Exception:
                        rel = Path(m["path"]).name
                    if rel in excludes:
                        continue
                    files.append(rel)

        mapping_subset_path = output_dir / "mapping_subset.json"
        if files:
            core.write_mapping_subset(reverse_map, files, mapping_subset_path)
            print(f"Exported mapping_subset.json for {len(files)} file(s): {', '.join(files)}")
        else:
            print("No placeholders to export; mapping_subset.json not written.")

        # 6c) Optional manifest export
        if getattr(args, "export_manifest", False):
            try:
                manifest = core.build_manifest(file_metas, reverse_map, str(input_root))
                io_utils.write_atomic(
                    output_dir / "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                )
                print(f"Manifest written to: {output_dir / 'manifest.json'}")
            except Exception as e:
                print(f"Error generating manifest: {e}", file=sys.stderr)

        # 6d) Optional boundary-aware chunking
        if getattr(args, "chunk_output", False):
            try:
                chunks_manifest = core.chunk_outputs(
                    llm_ready,
                    output_dir,
                    args.chunk_size,
                    input_root=input_root,
                    reverse_map=reverse_map,
                )
                chunks_dir = output_dir / "chunks"
                io_utils.ensure_dir(chunks_dir)
                if isinstance(chunks_manifest, dict) and "chunks_dir" not in chunks_manifest:
                    chunks_manifest["chunks_dir"] = "chunks"
                io_utils.write_atomic(
                    chunks_dir / "manifest.json",
                    json.dumps(chunks_manifest, ensure_ascii=False, indent=2),
                )
                print(f"Chunks written to: {chunks_dir} (manifest.json included)")
            except Exception as e:
                print(f"Error generating chunks: {e}", file=sys.stderr)

        # 7) Exact string roundtrip verification
        if args.verify_roundtrip:
            ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
            print("=== EXACT ROUNDTRIP REPORT ===")
            for d in details:
                print(" -", d)
            print("=== END ROUNDTRIP REPORT ===")

            if not ok:
                print("Exact roundtrip verification FAILED:", file=sys.stderr)
                for d in details:
                    print(" -", d, file=sys.stderr)
                try:
                    io_utils.write_atomic(
                        output_dir / "roundtrip_failures.json",
                        json.dumps(details, ensure_ascii=False, indent=2),
                    )
                except Exception:
                    pass
                sys.exit(2)

        # 8) Savings report
        mapping_size = mapping_subset_path.stat().st_size if mapping_subset_path.exists() else 0
        stats = core.estimate_savings(contents, llm_ready, mapping_size=mapping_size)
        _print_report(stats, replacements, args.preset)

        print(f"Execution completed. Outputs in: {output_dir}")

    except Exception as e:
        print("Fatal error:", e, file=sys.stderr)
        sys.exit(1)


def _write_outputs(llm_ready, reverse_map, output_dir: Path, input_root: Path):
    """
    Write compressed files preserving relative paths relative to input_root.
    Guarantees out_path is never a directory when processing single files.
    """
    errors = []
    for abs_path, text in llm_ready.items():
        abs_p = Path(abs_path).resolve()
        try:
            rel = abs_p.relative_to(input_root)
            if rel == Path(".") or str(rel) == ".":
                rel = Path(abs_p.name)
        except Exception:
            rel = Path(abs_p.name)

        out_path = output_dir / rel
        io_utils.ensure_dir(out_path.parent)
        try:
            io_utils.write_atomic(out_path, text)
        except Exception as e:
            errors.append((str(out_path), str(e)))

    try:
        core.write_reverse_map(reverse_map, output_dir / "reverse_map.json")
    except Exception as e:
        errors.append((str(output_dir / "reverse_map.json"), str(e)))

    if errors:
        for p, err in errors:
            print(f"Write error for {p}: {err}", file=sys.stderr)
        raise RuntimeError("Errors encountered while writing outputs")


def _print_report(stats: dict, replacements: list, preset_name: str):
    """
    Print comprehensive compression and token economy report.
    """
    print(f"\n=== SAVINGS AND TOKEN REPORT (Profile: {preset_name}) ===")
    print(f"Original characters:               {stats['orig_total']}")
    print(f"Compressed characters:             {stats['new_total']}")
    print(f"Mapping subset overhead (chars):   {stats['mapping_size']}")
    print(f"Gross character savings:           {stats['saved_chars']} ({stats['saved_pct']}%)")
    print(f"Net character savings:             {stats['net_saved_chars']} ({stats['net_saved_pct']}%)")
    print(f"Estimated original tokens (LLM):   {stats['orig_tokens_est']}")
    print(f"Estimated compressed text tokens:  {stats['new_tokens_est']}")
    print(f"Estimated mapping prompt tokens:   {stats['mapping_tokens_est']}")
    print(f"Estimated net token savings (LLM): {stats['net_saved_tokens']}")
    print(f"Active replacements accepted:      {len(replacements)}")
    print("=========================================================\n")


if __name__ == "__main__":
    main()

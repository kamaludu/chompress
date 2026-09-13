#!/usr/bin/env python3
"""
Local LLM-ready Compressor (P0, P1, P2, P3 & P4 Token-Aware CLI Orchestrator)
File: cli.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Command-line interface orchestrator for LLM context compression:
- Selects real or heuristic tokenizer backends.
- Hardened scanner integration: automatically excludes output directory from input scan.
- Supports three primary operational modes:
  1. LOSSLESS: decompress(compress(x)) == x byte-for-byte exact roundtrip.
  2. SEMANTIC: safe canonicalization preserving semantic information.
  3. AGGRESSIVE: maximum token reduction via domain pipelines (P1, P2, P3, P4).
- P3.1 License & Copyright Annihilation: strips verbose boilerplate headers.
- P3.2 Human Error & Log Compaction: shortens exception and logger strings.
- P3.3 Single-File Direct LLM Context Streamer (--stdout / stdin pipe '-'):
  streams ready-to-use context payloads directly into LLM prompts or Unix pipes.
- P3.4 Polyglot Config Minifiers: whitespace stripping on JSON and YAML files.
- P4.1 Unused Import & Type Alias Annihilation: strips dead imports and typing aliases.
- P4.2 Assertions & Diagnostic Statement Pruning: strips assert statements in Python.
- P4.3 LLM System Prompt Envelope (--envelope / -e): encapsulates context payloads
  in a token-efficient system instruction header and footer.
- Positional zero-key mapping serializers and boundary-aware chunking.

Mathematical token model (pure ASCII notation):
net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
"""

import argparse
import inspect
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import core
import io_utils
import mapping as mapping_module
import minifiers
import placeholders as ph_module
import tokenizer

VERSION = "3.4.1"

ENVELOPE_HEADER = (
    "<context>\n"
    "[LLM-READY COMPRESSED CONTEXT - chunk-compress v3.4.1]\n"
    "[INSTRUCTION: Expand placeholders using mapping dictionary before execution or analysis.]\n"
)
ENVELOPE_FOOTER = "</context>\n"

# -----------------------------------------------------------------------------
# Tuning Presets
# -----------------------------------------------------------------------------
PRESETS: Dict[str, Dict[str, Any]] = {
    "conservative": {
        "L_min": 40,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 3,
        "B_max_lines": 15,
        "min_total_saving": 15,
        "desc": "Safe profile for large repositories; requires at least 15 net tokens saved.",
    },
    "code-max": {
        "L_min": 14,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 2,
        "B_max_lines": 10,
        "min_total_saving": 2,
        "desc": "Recommended for codebases and scripts; requires at least 2 net tokens saved.",
    },
    "text-balanced": {
        "L_min": 20,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 2,
        "B_max_lines": 8,
        "min_total_saving": 3,
        "desc": "Balanced profile for markdown docs and specs; requires at least 3 net tokens saved.",
    },
    "aggressive": {
        "L_min": 10,
        "L_max": 2000,
        "N_min": 2,
        "B_min_lines": 2,
        "B_max_lines": 6,
        "min_total_saving": 1,
        "desc": "Maximum token reduction; accepts any replacement with positive net token gain.",
    },
}

EPILOG_EXAMPLES = """
------------------------------------------------------------------------------
MODES OF OPERATION:
  --mode aggressive   (Default) Max token reduction: P1-P4 minifiers (docstrings,
                      types, ANSI, badges, error strings, licenses, imports, asserts)
                      + positional map.
  --mode semantic     Semantic-preserving minification (comment & docstring stripping,
                      table compacting, AST local renaming, unused imports pruning).
  --mode lossless     Strict decompress(compress(x)) == x, zero text alteration.

STREAMING, PIPES & PROMPT ENVELOPE (P3.3 & P4.3):
  --stdout            Stream ready-to-use self-contained context directly to stdout.
  -i -                Read input code directly from standard input (stdin pipe).
  --envelope, -e      Wrap stdout stream in an optimized LLM system prompt envelope.

READY-TO-USE EXAMPLES:
  # 1. Direct LLM context stream via pipe with prompt envelope (zero disk files):
  cat script.py | python3 cli.py -i - --stdout --envelope

  # 2. Single-file direct compression to prompt context with envelope:
  python3 cli.py -i service.py --stdout -e > prompt_context.txt

  # 3. Aggressive codebase compression with exact roundtrip verification:
  python3 cli.py -i ./src -o out --mode aggressive --verify-roundtrip
------------------------------------------------------------------------------
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Local LLM-ready Context Compressor (Token-First Architecture).",
        epilog=EPILOG_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} (GPL-3.0-or-later)",
        help="Show program version number and exit",
    )

    # 1. Primary Operational Mode
    g_mode = p.add_argument_group("Primary Compression Mode")
    g_mode.add_argument(
        "--mode",
        choices=["lossless", "semantic", "aggressive"],
        default="aggressive",
        help="Compression mode: 'aggressive' (default: max token reduction), 'semantic', or 'lossless'",
    )

    # 2. Input and Output Paths
    g_io = p.add_argument_group("Input and Output Options")
    g_io.add_argument(
        "--input", "-i", required=True, help="Input directory, single file, file-list, or '-' for stdin"
    )
    g_io.add_argument(
        "--output", "-o", default="compressed_output", help="Output directory (default: 'compressed_output')"
    )
    g_io.add_argument(
        "--stdout",
        action="store_true",
        help="Stream self-contained LLM-ready context directly to standard output",
    )
    g_io.add_argument(
        "--envelope",
        "-e",
        action="store_true",
        help="Wrap stdout stream in an optimized LLM system prompt envelope (P4.3)",
    )
    g_io.add_argument(
        "--include-pointless",
        action="store_true",
        help="Do NOT exclude binary or non-text extensions during scanning",
    )

    # 3. Tokenizer Selection
    g_tok = p.add_argument_group("Tokenizer Options")
    g_tok.add_argument(
        "--tokenizer",
        default="auto",
        help="Tokenizer backend: 'auto' (default), 'cl100k_base', 'o200k_base', 'hf:<name>', or 'heuristic'",
    )

    # 4. P0 Placeholder and Mapping Serialization
    g_p0 = p.add_argument_group("P0 Token Economics & Formats")
    g_p0.add_argument(
        "--placeholder-style",
        choices=["auto", "classic", "guillemet", "section", "bracket", "ascii_compact", "single_token"],
        default="auto",
        help="Placeholder delimiter alphabet (default: 'auto' for minimum measured tokens)",
    )
    g_p0.add_argument(
        "--mapping-format",
        choices=["auto", "positional", "delimited", "kv", "json"],
        default="auto",
        help="Dictionary mapping format (default: 'auto' -> positional zero-key format)",
    )

    # 5. Semantic Minification & Domain Pipelines (P1, P3 & P4)
    g_mini = p.add_argument_group("Semantic Minification & Domain Pipelines (P1, P3 & P4)")
    g_mini.add_argument(
        "--semantic-minify",
        action="store_true",
        help="Enable all safe semantic minifiers across Python, Bash, Markdown, JSON, YAML",
    )
    g_mini.add_argument(
        "--strip-comments",
        action="store_true",
        help="Strip safe full-line comments from Bash and Python code",
    )
    g_mini.add_argument(
        "--strip-docstrings",
        action="store_true",
        help="Strip Python module, class, and function docstrings",
    )
    g_mini.add_argument(
        "--strip-types",
        action="store_true",
        help="Strip Python PEP 484/526 type annotations",
    )
    g_mini.add_argument(
        "--strip-license",
        action="store_true",
        help="Strip verbose copyright notices, SPDX tags, and top-level license headers (P3.1)",
    )
    g_mini.add_argument(
        "--compact-errors",
        action="store_true",
        help="Compact verbose exception and logger strings to short semantic codes (P3.2)",
    )
    g_mini.add_argument(
        "--prune-imports",
        action="store_true",
        help="Prune unused imports, type aliases, and typing imports in Python (P4.1)",
    )
    g_mini.add_argument(
        "--prune-asserts",
        action="store_true",
        help="Prune assertions and diagnostic check statements in Python code (P4.2)",
    )
    g_mini.add_argument(
        "--strip-ansi",
        action="store_true",
        help="Strip Bash ANSI escape sequences (terminal colors and control codes)",
    )
    g_mini.add_argument(
        "--strip-badges",
        action="store_true",
        help="Strip Markdown shields.io, CI workflow, and HTML status badges",
    )
    g_mini.add_argument(
        "--compact-tables",
        action="store_true",
        help="Strip visual padding spaces inside Markdown table cells",
    )
    g_mini.add_argument(
        "--python-rename-locals",
        action="store_true",
        help="Enable conservative Python AST local variable renaming",
    )
    g_mini.add_argument(
        "--normalize-indent",
        action="store_true",
        help="Convert 4 leading spaces to single tabs in code files",
    )
    g_mini.add_argument(
        "--keep-empty-lines",
        action="store_true",
        help="Preserve all empty lines across all files (pure lossless mode)",
    )

    # 6. Preset and Algorithmic Tuning
    g_tuning = p.add_argument_group("Preset and Algorithmic Tuning")
    g_tuning.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default=None,
        help="Select tuning profile (default resolved from --mode)",
    )
    g_tuning.add_argument(
        "--L_min", type=int, default=None, help="Minimum substring character length"
    )
    g_tuning.add_argument(
        "--L_max", type=int, default=None, help="Maximum substring character length"
    )
    g_tuning.add_argument(
        "--N_min", type=int, default=None, help="Minimum occurrences required"
    )
    g_tuning.add_argument(
        "--B_min_lines", type=int, default=None, help="Minimum lines for block candidate"
    )
    g_tuning.add_argument(
        "--B_max_lines", type=int, default=None, help="Maximum lines for block candidate"
    )
    g_tuning.add_argument(
        "--min_total_saving", type=int, default=None, help="Minimum net TOKENS saved required"
    )

    # 7. Legacy Custom Placeholders Formatting
    g_tokens = p.add_argument_group("Legacy Placeholder Formatting")
    g_tokens.add_argument(
        "--placeholder-sub", default="__s{:d}__", help="Pattern for substring placeholders"
    )
    g_tokens.add_argument(
        "--placeholder-blk", default="__b{:d}__", help="Pattern for block placeholders"
    )

    # 8. Boundary-Aware Chunking
    g_chunk = p.add_argument_group("Chunking Options")
    g_chunk.add_argument(
        "--chunk-output", action="store_true", help="Generate boundary-aware atomic chunks"
    )
    g_chunk.add_argument(
        "--chunk-size", type=int, default=16000, help="Maximum chunk character size"
    )

    # 9. Verification and Exports
    g_export = p.add_argument_group("Verification and Export Options")
    g_export.add_argument(
        "--verify-roundtrip",
        action="store_true",
        help="Perform exact string equality verification",
    )
    g_export.add_argument(
        "--export-manifest", action="store_true", help="Export manifest.json for processed files"
    )
    g_export.add_argument(
        "--no-export-mapping",
        nargs="?",
        const="",
        default=None,
        help="Control export of mapping_subset: omit to export all; empty to disable",
    )

    args = p.parse_args()

    # Automatic stdout mode when reading from stdin or when envelope is requested without custom output dir
    if args.input == "-" and not args.stdout and args.output == "compressed_output":
        args.stdout = True
    if args.envelope and not args.stdout and args.output == "compressed_output":
        args.stdout = True

    # Identify explicitly passed arguments to preserve explicit CLI overrides
    explicit_args = set(sys.argv[1:])

    # Resolve mode defaults
    if args.mode == "lossless":
        args.keep_empty_lines = True
        args.strip_comments = False
        args.strip_docstrings = False
        args.strip_types = False
        args.strip_license = False
        args.compact_errors = False
        args.prune_imports = False
        args.prune_asserts = False
        args.strip_ansi = False
        args.strip_badges = False
        args.compact_tables = False
        args.python_rename_locals = False
        args.normalize_indent = False
        preset_choice = args.preset or "code-max"
    elif args.mode == "semantic":
        args.strip_comments = True
        args.strip_docstrings = True
        args.strip_types = True
        args.strip_license = True
        args.compact_errors = False
        args.prune_imports = True
        args.prune_asserts = False
        args.strip_ansi = True
        args.strip_badges = True
        args.compact_tables = True
        args.python_rename_locals = True
        args.normalize_indent = True
        preset_choice = args.preset or "code-max"
    else:  # aggressive (default)
        args.strip_comments = True
        args.strip_docstrings = True
        args.strip_types = True
        args.strip_license = True
        args.compact_errors = True
        args.prune_imports = True
        args.prune_asserts = True
        args.strip_ansi = True
        args.strip_badges = True
        args.compact_tables = True
        args.python_rename_locals = True
        args.normalize_indent = True
        preset_choice = args.preset or "aggressive"

    # Honor explicit CLI flags if passed directly
    if "--strip-comments" in explicit_args:
        args.strip_comments = True
    if "--strip-docstrings" in explicit_args:
        args.strip_docstrings = True
    if "--strip-types" in explicit_args:
        args.strip_types = True
    if "--strip-license" in explicit_args:
        args.strip_license = True
    if "--compact-errors" in explicit_args:
        args.compact_errors = True
    if "--prune-imports" in explicit_args:
        args.prune_imports = True
    if "--prune-asserts" in explicit_args:
        args.prune_asserts = True
    if "--strip-ansi" in explicit_args:
        args.strip_ansi = True
    if "--strip-badges" in explicit_args:
        args.strip_badges = True
    if "--compact-tables" in explicit_args:
        args.compact_tables = True
    if "--python-rename-locals" in explicit_args:
        args.python_rename_locals = True
    if "--normalize-indent" in explicit_args:
        args.normalize_indent = True

    preset_cfg = PRESETS[preset_choice]
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

    if args.semantic_minify:
        args.strip_comments = True
        args.strip_docstrings = True
        args.strip_types = True
        args.strip_license = True
        args.compact_errors = True
        args.prune_imports = True
        args.prune_asserts = True
        args.strip_ansi = True
        args.strip_badges = True
        args.compact_tables = True
        args.python_rename_locals = True
        args.normalize_indent = True

    return args


def main():
    start_total_time = time.perf_counter()
    args = parse_args()

    # Route diagnostic messages to stderr when --stdout is used for clean piping
    log_dest = sys.stderr if args.stdout else sys.stdout

    # 1. Handle Stdin Pipe (P3.3) vs Filesystem Input
    if args.input == "-":
        stdin_text = sys.stdin.read()
        file_metas = [
            {
                "path": "stdin.txt",
                "size": len(stdin_text.encode("utf-8")),
                "sha256": io_utils.sha256_text(stdin_text),
                "is_single_file": True,
            }
        ]
        raw_contents = {"stdin.txt": stdin_text}
        input_root = Path(".")
    else:
        input_path = Path(args.input).resolve()
        if not input_path.exists():
            print(f"Error: input path does not exist: {input_path}", file=sys.stderr)
            sys.exit(1)
        input_root = input_path.parent if input_path.is_file() else input_path
        out_target = None if args.stdout else args.output
        file_metas = core.scan_files(
            str(input_path),
            exclude_pointless=not getattr(args, "include_pointless", False),
            output_dir=out_target,
        )
        raw_contents = core.load_contents(file_metas)

    output_dir = Path(args.output)
    if not args.stdout:
        io_utils.ensure_dir(output_dir)

    try:
        # 2. Initialize Tokenizer Backend
        tok = tokenizer.get_tokenizer(args.tokenizer)
        is_approx = isinstance(tok, tokenizer.HeuristicBackend)
        tok_display = f"{tok.name} (HEURISTIC APPROXIMATION)" if is_approx else tok.name
        print(f"Active Tokenizer backend: {tok_display}", file=log_dest)
        print(f"Operating Mode: {args.mode.upper()}", file=log_dest)

        contents = dict(raw_contents)

        # 3. Stage 1: Domain-Specific Canonicalization (P1, P3 & P4)
        if (
            args.strip_comments
            or args.strip_docstrings
            or args.strip_types
            or args.strip_ansi
            or args.strip_badges
            or args.compact_tables
            or args.python_rename_locals
            or getattr(args, "strip_license", False)
            or getattr(args, "compact_errors", False)
            or getattr(args, "prune_imports", False)
            or getattr(args, "prune_asserts", False)
        ):
            canon_kwargs = {
                "enable_comments_removal": args.strip_comments,
                "enable_table_compaction": args.compact_tables,
                "enable_python_renaming": args.python_rename_locals,
                "enable_docstring_removal": args.strip_docstrings,
                "enable_type_annotations_removal": args.strip_types,
                "enable_ansi_stripping": args.strip_ansi,
                "enable_badge_removal": args.strip_badges,
            }
            sig = inspect.signature(core.canonicalize_contents)
            if "enable_license_stripping" in sig.parameters:
                canon_kwargs["enable_license_stripping"] = getattr(args, "strip_license", True)
            if "enable_error_string_compaction" in sig.parameters:
                canon_kwargs["enable_error_string_compaction"] = getattr(args, "compact_errors", True)
            if "enable_import_pruning" in sig.parameters:
                canon_kwargs["enable_import_pruning"] = getattr(args, "prune_imports", True)
            if "enable_assert_pruning" in sig.parameters:
                canon_kwargs["enable_assert_pruning"] = getattr(args, "prune_asserts", True)

            contents = core.canonicalize_contents(contents, **canon_kwargs)

        if not args.keep_empty_lines:
            try:
                contents = core.strip_empty_lines_by_extension(
                    contents, normalize_indent=args.normalize_indent
                )
            except Exception as e:
                print(f"Error during line stripping: {e}", file=sys.stderr)
                sys.exit(1)

        # 4. Initialize P0 Engines (Placeholder Alphabet & Mapping)
        all_raw_text = "".join(contents.values())
        ph_engine = ph_module.PlaceholderEngine(args.placeholder_style, tok=tok)
        calibrated_ph = ph_engine.auto_calibrate(all_raw_text)
        print(f"Active Placeholder style: {calibrated_ph} (BPE-optimized)", file=log_dest)

        map_serializer = mapping_module.get_mapping_serializer(args.mapping_format)
        print(f"Active Mapping serializer: {map_serializer.name}", file=log_dest)

        # 5. Stage 2: Repetition Discovery
        candidates = core.find_repetitions(
            contents,
            L_min=args.L_min,
            N_min=args.N_min,
            B_min_lines=args.B_min_lines,
            B_max_lines=args.B_max_lines,
            L_max=args.L_max,
        )

        # 6. Stage 3: P0-P4 Token-Aware Replacement Selection
        replacements = core.select_replacements(
            candidates,
            all_raw_text=all_raw_text,
            placeholder_fmt_sub=args.placeholder_sub,
            placeholder_fmt_blk=args.placeholder_blk,
            min_total_saving=args.min_total_saving,
            tok=tok,
            ph_engine=ph_engine,
            map_serializer=map_serializer,
        )

        # 7. Apply Placeholders and Generate Reverse Map
        llm_ready, reverse_map = core.apply_placeholders(
            contents, replacements, ph_engine=ph_engine
        )

        # 8. Export Mapping Subset / Global Repository Dictionary
        files: List[str] = []
        no_export_val = getattr(args, "no_export_mapping", None)
        if no_export_val is None:
            for m in file_metas:
                rel = _to_logical_relative(m["path"], input_root)
                files.append(rel)
        elif no_export_val != "":
            excludes = {
                Path(s.strip()).as_posix().lstrip("./")
                for s in str(no_export_val).split(",")
                if s.strip()
            }
            for m in file_metas:
                rel = _to_logical_relative(m["path"], input_root)
                if rel in excludes or Path(rel).name in excludes:
                    continue
                files.append(rel)

        mapping_payload = ""
        protocol_header = ""

        if files:
            ph_meta = reverse_map.get("ph_meta", {})
            subset_dict = core.extract_mapping_for_files(reverse_map, files)
            mapping_payload, protocol_header = map_serializer.serialize(
                subset_dict, raw_corpus=all_raw_text, ph_meta=ph_meta
            )

            if not args.stdout:
                mapping_subset_path = output_dir / "mapping_subset.txt"
                if map_serializer.name == "json":
                    json_path = output_dir / "mapping_subset.json"
                    io_utils.write_atomic(json_path, mapping_payload)
                else:
                    io_utils.write_atomic(mapping_subset_path, mapping_payload)
                    io_utils.write_atomic(output_dir / "protocol_header.txt", protocol_header)

                dict_label = "global repository dictionary" if len(files) > 1 else "mapping"
                print(
                    f"Exported {dict_label} ({map_serializer.name}) for {len(files)} file(s) "
                    f"({len(subset_dict)} entries)",
                    file=log_dest,
                )

        # 9. Direct LLM Context Streaming Output (--stdout & P4.3 --envelope)
        if args.stdout:
            _emit_direct_stream(
                llm_ready,
                mapping_payload,
                protocol_header,
                map_serializer.name,
                use_envelope=args.envelope,
            )
        else:
            # Write compressed output files to filesystem
            _write_outputs(llm_ready, reverse_map, output_dir, input_root)

        # 10. Optional Manifest Export
        if getattr(args, "export_manifest", False) and not args.stdout:
            try:
                manifest = core.build_manifest(file_metas, reverse_map, str(input_root))
                io_utils.write_atomic(
                    output_dir / "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                )
                print(f"Manifest written to: {output_dir / 'manifest.json'}", file=log_dest)
            except Exception as e:
                print(f"Error generating manifest: {e}", file=sys.stderr)

        # 11. Optional Boundary-Aware Chunking
        if getattr(args, "chunk_output", False) and not args.stdout:
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
                print(f"Chunks written to: {chunks_dir} (manifest.json included)", file=log_dest)
            except Exception as e:
                print(f"Error generating chunks: {e}", file=sys.stderr)

        # 12. Exact Decompression Roundtrip Verification
        if args.verify_roundtrip:
            ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
            print("=== EXACT ROUNDTRIP REPORT ===", file=log_dest)
            for d in details:
                print(" -", d, file=log_dest)
            print("=== END ROUNDTRIP REPORT ===", file=log_dest)

            if not ok:
                print("Exact roundtrip verification FAILED:", file=sys.stderr)
                if not args.stdout:
                    try:
                        io_utils.write_atomic(
                            output_dir / "roundtrip_failures.json",
                            json.dumps(details, ensure_ascii=False, indent=2),
                        )
                    except Exception:
                        pass
                sys.exit(2)

        # 13. Multi-Stage Token Economy Report
        elapsed_total_sec = time.perf_counter() - start_total_time
        _print_multi_stage_report(
            raw_contents=raw_contents,
            canonical_contents=contents,
            llm_ready=llm_ready,
            mapping_payload=mapping_payload,
            protocol_header=protocol_header,
            replacements=replacements,
            mode=args.mode,
            ph_style=calibrated_ph,
            map_format=map_serializer.name,
            tok=tok,
            elapsed_sec=elapsed_total_sec,
            use_envelope=args.envelope,
            dest=log_dest,
        )

        if not args.stdout:
            print(f"Execution completed. Outputs in: {output_dir}", file=log_dest)

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


def _emit_direct_stream(
    llm_ready: Dict[str, str],
    mapping_payload: str,
    protocol_header: str,
    map_format: str,
    use_envelope: bool = False,
) -> None:
    """
    P3.3 & P4.3: Emits self-contained, clean context stream to stdout for direct LLM ingestion.
    When use_envelope is True, encapsulates output in an LLM prompt envelope.
    Zero filesystem writes, ready for pipes or prompt composition.
    """
    if use_envelope:
        sys.stdout.write(ENVELOPE_HEADER)

    if protocol_header:
        sys.stdout.write(protocol_header.strip() + "\n")
    if mapping_payload:
        sys.stdout.write(mapping_payload.strip() + "\n")

    is_single = len(llm_ready) == 1
    if is_single:
        single_content = next(iter(llm_ready.values()))
        sys.stdout.write("\n" + single_content)
        if not single_content.endswith("\n"):
            sys.stdout.write("\n")
    else:
        for path, text in sorted(llm_ready.items()):
            sys.stdout.write(f"\n--- FILE: {path} ---\n")
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")

    if use_envelope:
        sys.stdout.write(ENVELOPE_FOOTER)


def _to_logical_relative(file_path: str, input_root: Path) -> str:
    p = Path(file_path)
    try:
        rel = p.relative_to(input_root).as_posix()
        return rel if rel != "." else p.name
    except Exception:
        try:
            rel = p.resolve().relative_to(input_root.resolve()).as_posix()
            return rel if rel != "." else p.name
        except Exception:
            return p.name


def _write_outputs(
    llm_ready: dict, reverse_map: dict, output_dir: Path, input_root: Path
) -> None:
    errors = []
    for abs_path, text in llm_ready.items():
        rel_str = _to_logical_relative(abs_path, input_root)
        out_path = output_dir / Path(rel_str)
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


def _print_multi_stage_report(
    raw_contents: dict,
    canonical_contents: dict,
    llm_ready: dict,
    mapping_payload: str,
    protocol_header: str,
    replacements: list,
    mode: str,
    ph_style: str,
    map_format: str,
    tok: tokenizer.BaseTokenizer,
    elapsed_sec: float,
    use_envelope: bool = False,
    dest: Any = sys.stdout,
) -> None:
    """
    Renders comprehensive multi-stage token economy report (P0, P1, P2, P3 & P4).
    Evaluates:
        net_tokens_saved = original_tokens - (compressed_tokens + mapping_tokens + protocol_tokens)
        net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
    """
    raw_total_chars = sum(len(v) for v in raw_contents.values())
    raw_tokens = sum(tok.count(v) for v in raw_contents.values())

    canon_total_chars = sum(len(v) for v in canonical_contents.values())
    canon_tokens = sum(tok.count(v) for v in canonical_contents.values())

    comp_total_chars = sum(len(v) for v in llm_ready.values())
    comp_tokens = sum(tok.count(v) for v in llm_ready.values())

    map_chars = len(mapping_payload)
    map_tokens = tok.count(mapping_payload) if mapping_payload else 0
    proto_tokens = tok.count(protocol_header) if protocol_header else 0

    envelope_text = (ENVELOPE_HEADER + ENVELOPE_FOOTER) if use_envelope else ""
    envelope_tokens = tok.count(envelope_text) if envelope_text else 0
    total_protocol_overhead = proto_tokens + envelope_tokens

    # Stage 1: Ingestion & Domain-Specific Canonicalization (P1, P3 & P4)
    stage1_saved_tokens = raw_tokens - canon_tokens
    stage1_saved_pct = (
        ((stage1_saved_tokens) * 100.0) / (raw_tokens) if raw_tokens > 0 else 0.0
    )

    # Stage 2: Repetition Deduplication
    stage2_gross_tokens = canon_tokens - comp_tokens
    stage2_net_tokens = canon_tokens - (comp_tokens + map_tokens + total_protocol_overhead)
    stage2_net_pct = (
        ((stage2_net_tokens) * 100.0) / (canon_tokens) if canon_tokens > 0 else 0.0
    )

    # Stage 3: Sovereign Net Economy (LLM Context Window)
    total_net_tokens = raw_tokens - (comp_tokens + map_tokens + total_protocol_overhead)
    total_net_pct = (
        ((total_net_tokens) * 100.0) / (raw_tokens) if raw_tokens > 0 else 0.0
    )

    throughput_kchars = (
        ((raw_total_chars) / (1000.0)) / (elapsed_sec) if elapsed_sec > 0 else 0.0
    )

    sep = 65
    print("\n" + "=" * sep, file=dest)
    print(f"=== P0-P4 TOKEN ECONOMY REPORT (Mode: {mode.upper()}, Backend: {tok.name}) ===", file=dest)
    print("=" * sep, file=dest)
    print(f"Configurations: Style={ph_style} | Mapping={map_format}", file=dest)
    if use_envelope:
        print("Prompt Envelope: ACTIVE (P4.3 LLM System Envelope)", file=dest)
    print("--- Stage 1: Ingestion and Domain-Specific Canonicalization ---", file=dest)
    print(f"Original content:            {raw_total_chars:>8d} chars | {raw_tokens:>7d} tokens", file=dest)
    print(f"Canonicalized content:       {canon_total_chars:>8d} chars | {canon_tokens:>7d} tokens", file=dest)
    print(f"Canonicalization savings:    {stage1_saved_tokens:>8d} tokens ({round(stage1_saved_pct, 2):.2f}%)", file=dest)
    print("", file=dest)
    print("--- Stage 2: Token-Aware Repetition Deduplication ---", file=dest)
    print(f"Compressed payload:          {comp_total_chars:>8d} chars | {comp_tokens:>7d} tokens", file=dest)
    print(f"Mapping dictionary payload:  {map_chars:>8d} chars | {map_tokens:>7d} tokens", file=dest)
    print(f"Protocol header overhead:                       | {proto_tokens:>7d} tokens", file=dest)
    if use_envelope:
        print(f"Envelope prompt overhead:                       | {envelope_tokens:>7d} tokens", file=dest)
    print(f"Gross deduplication savings: {stage2_gross_tokens:>8d} tokens", file=dest)
    print(f"Net deduplication savings:   {stage2_net_tokens:>8d} tokens ({round(stage2_net_pct, 2):.2f}%)", file=dest)
    print(f"Active replacements:         {len(replacements):>8d}", file=dest)
    print("", file=dest)
    print("--- Stage 3: Sovereign Net Economy (LLM Context Window) ---", file=dest)
    print(f"TOTAL NET TOKENS SAVED:      {total_net_tokens:>8d} tokens ({round(total_net_pct, 2):.2f}%)", file=dest)
    print(f"Elapsed execution time:      {round(elapsed_sec, 2):.2f}s (~{round(throughput_kchars, 1):.1f} kChars/s)", file=dest)
    print("=" * sep + "\n", file=dest)


if __name__ == "__main__":
    main()

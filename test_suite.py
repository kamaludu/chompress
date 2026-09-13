#!/usr/bin/env python3
"""
Comprehensive Test Suite for chunk-compress (P0, P1, P2, P3 & P4 Architecture)
File: test_suite.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Unit test suite verifying architectural integrity, domain minifiers, and P0-P4 token economics:
- Single-File First workflow and path isolation.
- P1 & P3 Domain-Specific Minifiers:
  * Python AST: docstrings removal, PEP 484/526 types stripping, safe local renaming.
  * P3.1: License and copyright boilerplate header annihilation preserving shebang.
  * P3.2: Human error and log message compaction to concise tokens in Python AST.
  * P3.4: Polyglot configuration minifiers for JSON and YAML files.
  * Bash: ANSI terminal color stripping, comment preservation, shebang protection.
  * Markdown: Shields.io/CI badge stripping, table cell padding compaction.
- P4 Aggressive Token-Saving Minifiers & LLM Integration:
  * P4.1: Unused import & type alias annihilation in Python AST.
  * P4.2: Diagnostic assertion statement pruning in Python AST.
  * P4.3: LLM prompt envelope encapsulation for direct context streaming.
- Global Repository Dictionary (P1.3): cross-file deduplication amortization.
- Exact lossless roundtrip verification across all placeholder alphabets.
- Undeclared and orphan placeholder detection.
- Boundary-aware atomic chunking protecting placeholder spans.
- All mapping serializers (JSON, Delimited, Positional, KV) exact roundtrip.
- Tokenizer-aware placeholder auto-calibration and token efficiency.
- P2.1: BPE alignment verification, CamelCase subword splitting, atomic CJK, statistical calibration.
- P2.2: Dynamic Sliding Block Discovery via 60-bit line rolling hash state machine.
- P2.3: Multi-Range CJK protocol headers and hybrid CJK+Prefix spillover (<= 40 tokens).
- Rabin-Karp rolling hash 64-bit state machine with offset zero.
- Asymmetric substring expansion and multi-line block candidate discovery.
- Mathematical savings accounting with protocol overhead.

Mathematical token model (pure ASCII notation):
net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
"""

import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import cli
import core
import io_utils
import mapping
import minifiers
import placeholders
import tokenizer


class TestChunkCompressPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cc_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # P4 Tests: Unused Imports, Assert Pruning, LLM Prompt Envelope
    # -------------------------------------------------------------------------
    def test_p4_1_unused_import_pruning(self):
        """P4.1: Verify pruning of unused imports, type aliases, and typing imports."""
        code = (
            "import os\n"
            "import sys\n"
            "import math\n"
            "from typing import List, Dict, Optional, Union\n"
            "from collections import defaultdict\n\n"
            "def calculate_circle_area(radius: float) -> float:\n"
            "    return math.pi * (radius ** 2)\n\n"
            "def get_counts():\n"
            "    return defaultdict(int)\n"
        )
        contents = {"/virtual/app.py": code}
        canonical = core.canonicalize_contents(
            contents,
            enable_import_pruning=True,
            enable_docstring_removal=True,
            enable_type_annotations_removal=True,
        )
        res = canonical["/virtual/app.py"]

        self.assertNotIn("import os", res)
        self.assertNotIn("import sys", res)
        self.assertNotIn("from typing import", res)
        self.assertIn("import math", res)
        self.assertIn("from collections import defaultdict", res)

        # Executable equivalence check
        compiled = compile(res, "<test_p4_1>", "exec")
        scope = {}
        exec(compiled, scope)
        self.assertAlmostEqual(scope["calculate_circle_area"](2), 12.56637, places=4)

    def test_p4_2_assertion_pruning(self):
        """P4.2: Verify pruning of diagnostic assert statements in aggressive mode."""
        code = (
            "def compute_quotient(a: int, b: int) -> float:\n"
            "    assert b != 0, 'Denominator must never be zero'\n"
            "    assert a >= 0, 'Numerator must be non-negative'\n"
            "    return a / b\n"
        )
        contents = {"/virtual/calc.py": code}

        # 1. Aggressive mode: assertions pruned
        canonical_pruned = core.canonicalize_contents(
            contents,
            enable_assert_pruning=True,
        )
        res_pruned = canonical_pruned["/virtual/calc.py"]
        self.assertNotIn("assert", res_pruned)
        self.assertNotIn("Denominator must never be zero", res_pruned)
        self.assertIn("return a / b", res_pruned)

        compiled_pruned = compile(res_pruned, "<test_p4_2>", "exec")
        scope = {}
        exec(compiled_pruned, scope)
        self.assertEqual(scope["compute_quotient"](10, 2), 5.0)

        # 2. Semantic/Lossless mode: assertions preserved
        canonical_kept = core.canonicalize_contents(
            contents,
            enable_assert_pruning=False,
        )
        res_kept = canonical_kept["/virtual/calc.py"]
        self.assertIn("assert", res_kept)

    def test_p4_3_llm_prompt_envelope(self):
        """P4.3: Verify LLM prompt envelope encapsulation for --stdout streaming."""
        llm_ready = {"service.py": "def run():\n    return 42\n"}
        mapping_payload = "一\nhello\n"
        protocol_header = "[MAP:INDEXED cjk_start=19968 count=1]"

        # Test WITH envelope:
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            cli._emit_direct_stream(
                llm_ready,
                mapping_payload,
                protocol_header,
                map_format="positional",
                use_envelope=True,
            )
            output_with_env = mock_stdout.getvalue()

        self.assertIn("<context>", output_with_env)
        self.assertIn("</context>", output_with_env)
        self.assertIn("[LLM-READY COMPRESSED CONTEXT", output_with_env)
        self.assertIn(protocol_header, output_with_env)
        self.assertIn("def run():", output_with_env)

        # Test WITHOUT envelope:
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            cli._emit_direct_stream(
                llm_ready,
                mapping_payload,
                protocol_header,
                map_format="positional",
                use_envelope=False,
            )
            output_no_env = mock_stdout.getvalue()

        self.assertNotIn("<context>", output_no_env)
        self.assertNotIn("</context>", output_no_env)
        self.assertIn(protocol_header, output_no_env)

    # -------------------------------------------------------------------------
    # P3 Tests: License Stripping, Error/Log Compaction, Polyglot Config
    # -------------------------------------------------------------------------
    def test_p3_1_license_annihilation(self):
        """P3.1: Verify license, copyright, and SPDX header stripping preserving shebang."""
        code_with_c_license = (
            "/*\n"
            " * Copyright (C) 2026 Enterprise Corp.\n"
            " * SPDX-License-Identifier: GPL-3.0-or-later\n"
            " * All rights reserved.\n"
            " */\n\n"
            "def compute_val(x):\n"
            "    return x * 2\n"
        )
        stripped_c = minifiers.strip_license_header(code_with_c_license, ".py")
        self.assertNotIn("Copyright (C) 2026", stripped_c)
        self.assertNotIn("SPDX-License-Identifier", stripped_c)
        self.assertIn("def compute_val(x):", stripped_c)

        code_with_hash_license = (
            "#!/usr/bin/env python3\n"
            "# Copyright 2026 Open Source Project\n"
            "# Licensed under Apache License 2.0\n"
            "# All rights reserved.\n\n"
            "print('running service')\n"
        )
        stripped_hash = minifiers.strip_license_header(code_with_hash_license, ".py")
        self.assertTrue(stripped_hash.startswith("#!/usr/bin/env python3"))
        self.assertNotIn("Copyright 2026", stripped_hash)
        self.assertNotIn("Apache License 2.0", stripped_hash)
        self.assertIn("print('running service')", stripped_hash)

    def test_p3_2_error_and_log_string_compaction(self):
        """P3.2: Verify verbose exception and logger strings are compacted to semantic tokens."""
        code = (
            "import logging\n\n"
            "logger = logging.getLogger(__name__)\n\n"
            "def validate_and_run(val: int):\n"
            "    if val < 0:\n"
            "        raise ValueError('The provided parameter is completely invalid and out of bounds')\n"
            "    logger.info('Successfully validated the incoming value and continuing execution')\n"
            "    return val * 10\n"
        )
        minified = minifiers.minify_python(
            code,
            rename_locals=False,
            strip_docstrings=True,
            strip_types=True,
            compact_error_strings=True,
        )
        self.assertNotIn("The provided parameter is completely invalid", minified)
        self.assertNotIn("Successfully validated the incoming value", minified)
        self.assertIn("raise ValueError('ERR')", minified)
        self.assertIn("logger.info('LOG')", minified)

        # Verify executable equivalence
        compiled = compile(minified, "<test_p3_2>", "exec")
        scope = {}
        exec(compiled, scope)
        self.assertEqual(scope["validate_and_run"](5), 50)
        with self.assertRaises(ValueError):
            scope["validate_and_run"](-1)

    def test_p3_4_polyglot_config_minifiers(self):
        """P3.4: Verify JSON visual whitespace compaction and YAML comment stripping."""
        json_raw = (
            "{\n"
            '  "service": "worker_daemon",\n'
            '  "replicas": 3,\n'
            '  "enabled": true,\n'
            '  "tags": [\n'
            '    "production",\n'
            '    "critical"\n'
            "  ]\n"
            "}\n"
        )
        minified_json = minifiers.minify_json(json_raw)
        self.assertEqual(
            minified_json,
            '{"service":"worker_daemon","replicas":3,"enabled":true,"tags":["production","critical"]}',
        )

        yaml_raw = (
            "# Service deployment configuration\n"
            "# Version: 2.0\n"
            "version: '3.8'\n"
            "services:\n"
            "  app:\n"
            "    image: enterprise/app:latest\n"
            "    # Port mapping for internal network\n"
            "    ports:\n"
            "      - '8080:8080'\n"
        )
        minified_yaml = minifiers.minify_yaml(yaml_raw)
        self.assertNotIn("Service deployment configuration", minified_yaml)
        self.assertNotIn("Port mapping for internal network", minified_yaml)
        self.assertIn("version: '3.8'", minified_yaml)
        self.assertIn("- '8080:8080'", minified_yaml)

    # -------------------------------------------------------------------------
    # P2 Tests: BPE Alignment, Dynamic Sliding Blocks, Multi-Range Headers
    # -------------------------------------------------------------------------
    def test_p2_1_bpe_alignment_and_calibration(self):
        """P2.1: Verify BPE subword alignment, atomic CJK tokens, and statistical calibration suite."""
        tok_h = tokenizer.get_tokenizer("heuristic")

        # 1. Verify single CJK characters are strictly 1 token each
        self.assertEqual(tok_h.count("一"), 1)
        self.assertEqual(tok_h.count("一丁丂"), 3)

        # 2. Verify leading space merges with words in BPE
        self.assertEqual(tok_h.count(" test"), 1)
        self.assertEqual(tok_h.count("test"), 1)

        # 3. Verify CamelCase subword splitting (each word segment is <= 12 chars -> 1 token each)
        self.assertEqual(tok_h.count("camelCaseVar"), 3)

        # 4. Verify statistical calibration calculations
        samples = [
            "def calculate_metric(x: float, y: float) -> float:\n    return x * 1.5 + y\n",
            "echo '[OK] Service started successfully'\nexit 0\n",
            "# Documentation title\nTable content | col1 | col2 |\n",
        ]
        calib = tokenizer.calibrate_tokenizer_suite(tok_h, tok_h, samples)
        self.assertEqual(calib["samples"], 3)
        self.assertEqual(calib["aggregate_error_pct"], 0.0)
        self.assertEqual(calib["mean_sample_error_pct"], 0.0)
        self.assertEqual(calib["mean_ratio"], 1.0)
        self.assertEqual(calib["ci_95_diff"], [0.0, 0.0])

    def test_p2_2_dynamic_sliding_block_discovery(self):
        """P2.2: Verify 60-bit line-level polynomial rolling hash block repetition detector."""
        block_pattern = (
            "    validate_session(request)\n"
            "    user = authenticate(request.token)\n"
            "    authorize(user, 'READ')\n"
            "    dispatch_event(user)\n"
        )
        content_a = "# File A\n" + (block_pattern * 4) + "    end_service_a()\n"
        content_b = "# File B\n" + (block_pattern * 3) + "    end_service_b()\n"
        contents = {"/virtual/a.py": content_a, "/virtual/b.py": content_b}

        cands = core.find_repetitions(
            contents, L_min=30, N_min=2, B_min_lines=3, B_max_lines=6
        )
        block_cands = [c for c in cands if c["type"] == "block"]
        self.assertTrue(len(block_cands) >= 1)

        matched = False
        for c in block_cands:
            if "validate_session(request)" in c["content"] and "dispatch_event(user)" in c["content"]:
                matched = True
                self.assertGreaterEqual(len(c["occurrences"]), 2)
                break
        self.assertTrue(matched, "Dynamic sliding block detector must identify repeating line block")

    def test_p2_3_multi_range_positional_headers(self):
        """P2.3: Verify multi-range CJK and hybrid CJK+Prefix positional headers in <= 40 tokens."""
        serializer = mapping.get_mapping_serializer("positional")
        tok = tokenizer.get_tokenizer("heuristic")

        # 1. Disjoint CJK ranges (e.g. 0x4E00-0x4E01 and 0x4E50-0x4E51)
        cjk_1 = [chr(0x4E00), chr(0x4E01)]  # 一, 丁
        cjk_2 = [chr(0x4E50), chr(0x4E51)]  # 乐, 乑
        disjoint_map = {
            cjk_1[0]: "BLOCK_1",
            cjk_1[1]: "BLOCK_2",
            cjk_2[0]: "BLOCK_3",
            cjk_2[1]: "BLOCK_4",
        }
        payload_d, header_d = serializer.serialize(disjoint_map)
        self.assertIn("cjk_ranges=", header_d)
        self.assertLessEqual(tok.count(header_d), 40)
        recon_d = serializer.deserialize(payload_d, header_d)
        self.assertEqual(disjoint_map, recon_d)

        # 2. Hybrid Tier 1 CJK + Tier 2 Prefix spillover
        hybrid_map = {
            chr(0x4E00): "CONTENT_A",
            chr(0x4E01): "CONTENT_B",
            "^1": "CONTENT_C",
            "^2": "CONTENT_D",
        }
        payload_h, header_h = serializer.serialize(hybrid_map)
        self.assertIn("prefix=", header_h)
        self.assertLessEqual(tok.count(header_h), 40)
        recon_h = serializer.deserialize(payload_h, header_h)
        self.assertEqual(hybrid_map, recon_h)

        # 3. Exact lossless roundtrip verification with hybrid map
        target_text = (
            "header\nCONTENT_A\nmiddle\nCONTENT_B\nother\nCONTENT_C\nfinal\nCONTENT_D\n"
        )
        transformed_text = "header\n一\nmiddle\n丁\nother\n^1\nfinal\n^2\n"
        contents = {"/v/hybrid.txt": target_text}
        llm_ready = {"/v/hybrid.txt": transformed_text}
        rev_map = {
            "placeholders": {
                k: {"token": k, "content": v} for k, v in hybrid_map.items()
            }
        }
        ok, details = core.roundtrip_check(contents, llm_ready, rev_map)
        self.assertTrue(ok, f"Hybrid CJK+Prefix roundtrip failed: {details}")

    # -------------------------------------------------------------------------
    # P1 Domain-Specific Minifier Tests (P1.1 & P1.2)
    # -------------------------------------------------------------------------
    def test_p1_python_strip_docstrings_and_types(self):
        """P1.1: Verify Python AST docstrings and type annotations stripping."""
        source_code = (
            '"""Module level docstring explanation."""\n\n'
            'def compute_payload(data_vector: list, factor_val: float = 1.5) -> dict:\n'
            '    """Function docstring to be stripped."""\n'
            '    local_accumulator: float = 0.0\n'
            '    for element in data_vector:\n'
            '        local_accumulator += element * factor_val\n'
            '    return {"sum": local_accumulator}\n\n'
            'class WorkerHandler:\n'
            '    """Class docstring to be stripped."""\n'
            '    def run(self) -> None:\n'
            '        pass\n'
        )
        minified = minifiers.minify_python(
            source_code,
            rename_locals=False,
            strip_docstrings=True,
            strip_types=True,
            compact_error_strings=False,
        )

        self.assertNotIn("Module level docstring", minified)
        self.assertNotIn("Function docstring to be stripped", minified)
        self.assertNotIn("Class docstring to be stripped", minified)

        self.assertNotIn("data_vector: list", minified)
        self.assertNotIn("factor_val: float", minified)
        self.assertNotIn("-> dict", minified)
        self.assertNotIn("-> None", minified)
        self.assertNotIn("local_accumulator: float", minified)

        compiled_code = compile(minified, "<test_minified>", "exec")
        test_scope = {}
        exec(compiled_code, test_scope)
        self.assertIn("compute_payload", test_scope)
        self.assertEqual(test_scope["compute_payload"]([2, 4], 2.0), {"sum": 12.0})

    def test_p1_bash_strip_ansi_escapes(self):
        """P1.1: Verify Bash ANSI escape codes are stripped while preserving code logic."""
        bash_script = (
            "#!/usr/bin/env bash\n"
            "# Setup script with colored terminal output\n"
            'RED="\\033[31m"\n'
            'GREEN="\\x1b[32m"\n'
            'RESET="\\e[0m"\n'
            'echo -e "\\033[31m[ERROR]\\033[0m Failed to connect"\n'
            'echo -e "\\x1b[32m[OK]\\x1b[0m Service running"\n'
            "exit 0\n"
        )
        minified = minifiers.minify_bash(
            bash_script,
            remove_comments=True,
            remove_ansi=True,
        )

        self.assertTrue(minified.startswith("#!/usr/bin/env bash"))
        self.assertNotIn("Setup script with colored terminal output", minified)
        self.assertNotIn("\\033[31m", minified)
        self.assertNotIn("\\033[0m", minified)
        self.assertNotIn("\\x1b[32m", minified)
        self.assertNotIn("\\e[0m", minified)

        self.assertIn("[ERROR] Failed to connect", minified)
        self.assertIn("[OK] Service running", minified)
        self.assertIn("exit 0", minified)

    def test_p1_markdown_strip_badges_and_tables(self):
        """P1.2: Verify Markdown shields.io badge removal and table cell compaction."""
        doc = (
            "# Project Title\n\n"
            "[![Build Status](https://img.shields.io/github/actions/workflow/ci.yml)](https://ci.org)\n"
            "![Coverage](https://img.shields.io/codecov/c/github/repo.svg)\n"
            '<a href="#"><img src="https://img.shields.io/badge/license-GPL-blue.svg"></a>\n\n'
            "Here is a table:\n\n"
            "|   Column A    |    Column B       |\n"
            "|:--------------|------------------:|\n"
            "|   value 1     |    longer data    |\n"
            "|   x           |    y              |\n\n"
            "```bash\n"
            "# Code blocks must remain completely unchanged\n"
            "|  do not touch  |  inside code  |\n"
            "```\n"
        )
        minified = minifiers.minify_markdown(
            doc,
            compact_tables=True,
            remove_badges=True,
        )

        self.assertNotIn("img.shields.io", minified)
        self.assertNotIn("Build Status", minified)
        self.assertNotIn("license-GPL", minified)

        self.assertIn("| Column A | Column B |", minified)
        self.assertIn("| value 1 | longer data |", minified)
        self.assertIn("| x | y |", minified)
        self.assertIn("|  do not touch  |  inside code  |", minified)

    # -------------------------------------------------------------------------
    # P1 Global Repository Dictionary Tests (P1.3)
    # -------------------------------------------------------------------------
    def test_p1_global_repo_dictionary(self):
        """P1.3: Verify multi-file global dictionary amortizes repeated blocks across files."""
        shared_routine = (
            "def shared_verification_routine(auth_header, secret_token):\n"
            "    if not auth_header.startswith('Bearer '):\n"
            "        raise ValueError('Invalid auth scheme')\n"
            "    return hash_hmac(auth_header[7:], secret_token)\n"
        )
        f1_content = shared_routine + "\nvar_a = run_service_a()\n"
        f2_content = shared_routine + "\nvar_b = run_service_b()\n"
        f3_content = shared_routine + "\nvar_c = run_service_c()\n"

        contents = {
            "/repo/src/a.py": f1_content,
            "/repo/src/b.py": f2_content,
            "/repo/src/c.py": f3_content,
        }

        candidates = core.find_repetitions(
            contents, L_min=40, N_min=2, B_min_lines=2, B_max_lines=10
        )
        replacements = core.select_replacements(
            candidates,
            all_raw_text=f1_content + f2_content + f3_content,
            min_total_saving=10,
        )
        self.assertTrue(len(replacements) >= 1)

        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)

        global_map = core.extract_global_mapping(reverse_map)
        self.assertTrue(len(global_map) >= 1)

        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok, f"Global repo dictionary exact roundtrip failed: {details}")

    # -------------------------------------------------------------------------
    # P0 Tests: Integrity, Path Identity & Roundtrip Verification
    # -------------------------------------------------------------------------
    def test_p0_exact_roundtrip(self):
        """P0.1: Verify exact string roundtrip (recon == target)."""
        pattern = (
            "def compute_heavy_tensor_transformation(vector_input):\n"
            "    return [x * 2.5 for x in vector_input]\n"
        )
        content = (pattern + "\n") * 15
        contents = {"/virtual/file.py": content}

        candidates = core.find_repetitions(
            contents, L_min=30, N_min=2, B_min_lines=2, B_max_lines=10
        )
        replacements = core.select_replacements(
            candidates, all_raw_text=content, min_total_saving=50
        )
        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)

        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok, f"Exact roundtrip failed: {details}")

    def test_p0_roundtrip_detects_undeclared_placeholder(self):
        """P0.3: Verify roundtrip_check detects placeholders in text not declared in reverse_map."""
        contents = {"/virtual/file.py": "def test():\n    return 42\n"}
        llm_ready = {"/virtual/file.py": "def test():\n    return __s999__\n"}
        reverse_map = {
            "placeholders": {
                "__s001__": {
                    "token": "__s001__",
                    "content": "42",
                    "sha256": "abc",
                    "length": 2,
                    "occurrences": [],
                }
            }
        }
        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertFalse(ok, "Must detect undeclared placeholder __s999__")
        self.assertTrue(any("missing: __s999__" in d for d in details))

    def test_p0_roundtrip_preserves_legitimate_delimiters(self):
        """P0.3: Verify no false positive when source code legitimately contains placeholder delimiters."""
        content = 'regex_pattern = "__demo_token__"\nvalue = calculate_hash()\n' * 5
        contents = {"/virtual/script.py": content}

        candidates = core.find_repetitions(
            contents, L_min=20, N_min=2, B_min_lines=1, B_max_lines=5
        )
        replacements = core.select_replacements(
            candidates, all_raw_text=content, min_total_saving=20
        )
        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)

        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok, f"Roundtrip must succeed when recon == target: {details}")

    def test_p0_distinct_paths_same_filename(self):
        """P0.2: Verify extract_mapping_for_files prevents basename collisions across directories."""
        rev_map = {
            "placeholders": {
                "__s001__": {
                    "token": "__s001__",
                    "content": "secret_api_key",
                    "occurrences": [{"path": "/repo/api/index.py"}],
                },
                "__s002__": {
                    "token": "__s002__",
                    "content": "render_ui_template",
                    "occurrences": [{"path": "/repo/ui/index.py"}],
                },
            }
        }
        ui_subset = core.extract_mapping_for_files(rev_map, ["ui/index.py"])
        self.assertIn("__s002__", ui_subset)
        self.assertNotIn("__s001__", ui_subset)

        api_subset = core.extract_mapping_for_files(rev_map, ["api/index.py"])
        self.assertIn("__s001__", api_subset)
        self.assertNotIn("__s002__", api_subset)

    def test_p0_boundary_aware_chunking(self):
        """P0.2: Verify chunks never cut inside tokens and backtrack to newline."""
        token = "«1»"
        line_prefix = "a" * 80 + "\n"
        text = line_prefix + ("b" * 90) + token + ("\n" + "c" * 80)
        llm_ready = {"/virtual/chunk_test.txt": text}
        rev_map = {
            "placeholders": {
                token: {"token": token, "content": "LONG_REPLACED_CONTENT"}
            }
        }

        manifest = core.chunk_outputs(
            llm_ready,
            Path(self.test_dir),
            chunk_size=180,
            input_root=Path("/virtual"),
            reverse_map=rev_map,
        )

        chunk_files = manifest["files"]["chunk_test.txt"]["chunks"]
        recombined = ""
        for rel_chunk in chunk_files:
            chunk_path = Path(self.test_dir) / "chunks" / rel_chunk
            chunk_content = io_utils.read_text(chunk_path)
            self.assertFalse(token[:1] in chunk_content and token not in chunk_content)
            recombined += chunk_content

        self.assertEqual(recombined, text, "Chunk recombination must be lossless")

    def test_p0_keep_empty_lines(self):
        """P0: Verify empty line stripping on code vs preservation on documentation."""
        code_with_blanks = "import math\n\n\ndef run():\n\n    return math.pi\n"
        contents = {"script.py": code_with_blanks}

        stripped = core.strip_empty_lines_by_extension(contents)
        self.assertEqual(
            stripped["script.py"], "import math\ndef run():\n    return math.pi\n"
        )

        doc_contents = {"doc.md": "# Title\n\nParagraph text\n"}
        doc_stripped = core.strip_empty_lines_by_extension(doc_contents)
        self.assertEqual(doc_stripped["doc.md"], "# Title\n\nParagraph text\n")

    # -------------------------------------------------------------------------
    # P0 Tests: Mapping Serializers, Alphabet Optimizer & Single File
    # -------------------------------------------------------------------------
    def test_p0_mapping_serializers_roundtrip(self):
        """P0: Verify all mapping serializers deserialize identically: deserialize(serialize(M)) == M."""
        orig_map = {
            "«1»": "def process_data(records):\n    return [r.clean() for r in records]\n",
            "«2»": 'const API_ENDPOINT = "https://api.internal/v1/stream";',
            "«3»": "calculate_hash",
        }
        for name in ["json", "delimited", "positional", "kv"]:
            serializer = mapping.get_mapping_serializer(name)
            payload, header = serializer.serialize(orig_map, raw_corpus="")
            recon_map = serializer.deserialize(payload, header)
            for k, v in orig_map.items():
                self.assertEqual(
                    orig_map[k],
                    recon_map.get(k),
                    f"Serializer '{name}' failed on key {k}",
                )

    def test_p0_placeholder_token_efficiency(self):
        """P0: Verify compact placeholder styles require fewer tokens than classic verbose __s1__."""
        tok = tokenizer.get_tokenizer("heuristic")
        engine_classic = placeholders.PlaceholderEngine("classic", tok=tok)
        engine_guillemet = placeholders.PlaceholderEngine("guillemet", tok=tok)

        cost_classic = sum(
            engine_classic.get_token_cost("sub", i) for i in range(1, 20)
        )
        cost_guillemet = sum(
            engine_guillemet.get_token_cost("sub", i) for i in range(1, 20)
        )

        self.assertLess(
            cost_guillemet,
            cost_classic,
            "Guillemet style must strictly save tokens compared to classic __s1__",
        )

    def test_p0_auto_calibrate_avoids_collisions(self):
        """P0: Verify PlaceholderEngine.auto_calibrate avoids selecting styles that collide with corpus."""
        raw_corpus = "def test():\n    return '«1»'\n"
        tok = tokenizer.get_tokenizer("heuristic")
        engine = placeholders.PlaceholderEngine("auto", tok=tok)
        calibrated = engine.auto_calibrate(raw_corpus)
        self.assertNotEqual(
            calibrated, "guillemet", "Must not select guillemet if '«1»' exists in corpus"
        )

    def test_p0_positional_zero_keys_overhead(self):
        """P0: Verify positional serializer eliminates keys from the payload body."""
        orig_map = {
            "«1»": "BLOCK_A",
            "«2»": "BLOCK_B",
            "«3»": "BLOCK_C",
        }
        serializer = mapping.get_mapping_serializer("positional")
        payload, header = serializer.serialize(orig_map, raw_corpus="")
        self.assertNotIn("«1»", payload)
        self.assertNotIn("«2»", payload)
        self.assertNotIn("«3»", payload)

        recon = serializer.deserialize(payload, header)
        self.assertEqual(orig_map, recon)

    def test_p0_positional_contiguous_cjk_header(self):
        """P0: Verify positional serializer generates ~8-token cjk_start header for contiguous symbols."""
        keys = [chr(0x4E00), chr(0x4E01), chr(0x4E02)]  # 一, 丁, 丂
        orig_map = {keys[0]: "ALPHA", keys[1]: "BETA", keys[2]: "GAMMA"}
        serializer = mapping.get_mapping_serializer("positional")

        ph_meta = {"type": "cjk_contiguous", "start_cp": 0x4E00, "count": 3}
        payload, header = serializer.serialize(orig_map, ph_meta=ph_meta)

        self.assertIn("cjk_start=19968", header)
        self.assertIn("count=3", header)
        recon = serializer.deserialize(payload, header)
        self.assertEqual(orig_map, recon)

    def test_p0_alphabet_optimizer_single_token_roundtrip(self):
        """P0: Verify end-to-end exact roundtrip using atomic 1-token symbols."""
        pattern = "def process_batch_stream(data):\n    return [d.strip() for d in data]\n"
        content = (pattern + "\n") * 10
        contents = {"/virtual/script.py": content}

        candidates = core.find_repetitions(contents, L_min=20, N_min=2)
        tok = tokenizer.get_tokenizer("heuristic")
        ph_engine = placeholders.PlaceholderEngine("single_token", tok=tok)
        map_serializer = mapping.get_mapping_serializer("positional")

        replacements = core.select_replacements(
            candidates,
            all_raw_text=content,
            min_total_saving=10,
            tok=tok,
            ph_engine=ph_engine,
            map_serializer=map_serializer,
        )
        self.assertTrue(len(replacements) >= 1)

        llm_ready, reverse_map = core.apply_placeholders(
            contents, replacements, ph_engine=ph_engine
        )
        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok, f"Single-token exact roundtrip failed: {details}")

    def test_p0_single_file_first_workflow(self):
        """P0: Verify single file scanning sets is_single_file and extracts subset cleanly."""
        test_file = Path(self.test_dir) / "standalone.py"
        test_file.write_text("print('hello world')\n", encoding="utf-8")

        metas = core.scan_files(str(test_file))
        self.assertEqual(len(metas), 1)
        self.assertTrue(metas[0].get("is_single_file", False))

        rev_map = {
            "placeholders": {
                "一": {"content": "hello world", "occurrences": []}
            }
        }
        subset = core.extract_mapping_for_files(rev_map, ["."])
        self.assertIn("一", subset)
        self.assertEqual(subset["一"], "hello world")

    # -------------------------------------------------------------------------
    # P1 Algorithmic Correctness (Expansion & Block Detection)
    # -------------------------------------------------------------------------
    def test_p1_asymmetric_substring_expansion(self):
        """P1.1: Verify asymmetric left context does not prematurely truncate common right expansion."""
        shared_suffix = "_COMMON_CORE_PHRASE_" + ("Z" * 50)
        file1 = "AAA_LONG_MATCHING_PREFIX_12345" + shared_suffix
        file2 = "B_DIFF" + shared_suffix
        contents = {"/v/f1.txt": file1, "/v/f2.txt": file2}

        candidates = core.find_repetitions(
            contents,
            L_min=19,
            N_min=2,
            B_min_lines=10,
            B_max_lines=20,
            L_max=100,
        )
        sub_cands = [c for c in candidates if c["type"] == "substring"]
        self.assertTrue(len(sub_cands) >= 1)

        max_len = max(len(c["content"]) for c in sub_cands)
        self.assertGreaterEqual(max_len, len(shared_suffix))

    def test_p1_intermediate_block_candidates(self):
        """P1.2: Verify 5-line block candidate is fully detected under code-max preset."""
        block_5_lines = (
            "    validate_token(request)\n"
            "    user = get_authenticated_user()\n"
            "    log_audit_event(user, 'ACCESS')\n"
            "    check_permission_matrix(user)\n"
            "    return True\n"
        )
        content = (block_5_lines + "    process_step()\n") * 6
        contents = {"/v/service.py": content}

        candidates = core.find_repetitions(
            contents, L_min=50, N_min=2, B_min_lines=3, B_max_lines=12
        )
        block_cands = [c for c in candidates if c["type"] == "block"]

        lengths_in_lines = [len(c["content"].splitlines()) for c in block_cands]
        self.assertIn(5, lengths_in_lines, "Must detect the 5-line block candidate unitarily")

    # -------------------------------------------------------------------------
    # P1.5 Scalability & State Machine (Rolling Hash)
    # -------------------------------------------------------------------------
    def test_p1_5_rolling_hash_state_machine_offset_zero(self):
        """P1.5: Verify state machine handles offset 0 across files and normalizes consumer."""
        identical_header = "/* ENTERPRISE COPYRIGHT NOTICE 2026 */\n"
        f1 = identical_header + "var a = 1;\n"
        f2 = identical_header + "var b = 2;\n"
        contents = {"/v/module_a.js": f1, "/v/module_b.js": f2}

        candidates = core.find_repetitions(
            contents, L_min=25, N_min=2, B_min_lines=10, B_max_lines=20
        )
        sub_cands = [c for c in candidates if c["type"] == "substring"]

        self.assertTrue(
            len(sub_cands) >= 1,
            "Must find repetitions starting at offset 0 without overwriting",
        )
        self.assertIn(
            "/* ENTERPRISE COPYRIGHT NOTICE 2026 */", sub_cands[0]["content"]
        )

    # -------------------------------------------------------------------------
    # P2 Metrics & Estimation
    # -------------------------------------------------------------------------
    def test_p2_savings_calculation(self):
        """P2.1: Verify gross and net character and token savings formula."""
        orig = {"/f1.txt": "a" * 1000}
        comp = {"/f1.txt": "a" * 600}
        mapping_size = 150
        protocol_tokens = 10

        stats = core.estimate_savings(
            orig,
            comp,
            mapping_size=mapping_size,
            chars_per_token=4.0,
            protocol_tokens=protocol_tokens,
        )

        self.assertEqual(stats["saved_chars"], 400)
        self.assertEqual(stats["net_saved_chars"], 250)
        self.assertEqual(stats["orig_tokens_est"], 250)
        self.assertEqual(stats["new_tokens_est"], 150)
        self.assertEqual(stats["mapping_tokens_est"], 38)
        self.assertEqual(stats["protocol_tokens"], 10)
        self.assertEqual(stats["net_saved_tokens"], 52)


if __name__ == "__main__":
    unittest.main(verbosity=2)

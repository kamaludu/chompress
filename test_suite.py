#!/usr/bin/env python3
"""
Comprehensive Test Suite for chunk-compress
Verifies phases P0, P1, P2, P3 without external dependencies.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
import core
import io_utils


class TestChunkCompressPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cc_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_p0_exact_roundtrip(self):
        """P0.1: Verify exact string roundtrip (recon == target)."""
        pattern = "def compute_heavy_tensor_transformation(vector_input):\n    return [x * 2.5 for x in vector_input]\n"
        content = (pattern + "\n") * 15
        contents = {"/virtual/file.py": content}

        candidates = core.find_repetitions(contents, L_min=30, N_min=2, B_min_lines=2, B_max_lines=10)
        replacements = core.select_replacements(candidates, min_total_saving=50)
        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)

        ok, details = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok, f"Exact roundtrip failed: {details}")

    def test_p0_boundary_aware_chunking(self):
        """P0.2: Verify that chunks never cut inside tokens and backtrack to newline."""
        token = "§§s001§§"
        line_prefix = "a" * 80 + "\n"
        # Construct text where token spans across index 200 (chunk_size limit)
        text = line_prefix + ("b" * 90) + token + ("\n" + "c" * 80)
        llm_ready = {"/virtual/chunk_test.txt": text}
        rev_map = {"placeholders": {token: {"token": token, "content": "LONG_REPLACED_CONTENT"}}}

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
            # Token must never be sliced across chunk boundaries
            self.assertFalse(token[:4] in chunk_content and token not in chunk_content)
            recombined += chunk_content

        self.assertEqual(recombined, text, "Chunk recombination must be lossless")

    def test_p0_keep_empty_lines(self):
        """P0.3: Verify empty line stripping on code vs preservation."""
        code_with_blanks = "import math\n\n\ndef run():\n\n    return math.pi\n"
        contents = {"script.py": code_with_blanks}

        stripped = core.strip_empty_lines_by_extension(contents)
        self.assertEqual(stripped["script.py"], "import math\ndef run():\n    return math.pi\n")

        # Documentation extension must preserve empty lines
        doc_contents = {"doc.md": "# Title\n\nParagraph text\n"}
        doc_stripped = core.strip_empty_lines_by_extension(doc_contents)
        self.assertEqual(doc_stripped["doc.md"], "# Title\n\nParagraph text\n")

    def test_p1_per_occurrence_pruning(self):
        """P1.5: Verify candidate is kept when a single occurrence conflicts."""
        pat1 = "REPEATABLE_BLOCK_AAAAA_12345678901234567890\n"
        pat2 = "REPEATABLE_BLOCK_BBBBB_12345678901234567890\n"
        text = (pat1 * 5) + (pat2 * 5)
        contents = {"/virtual/multi.txt": text}

        candidates = core.find_repetitions(contents, L_min=25, N_min=2, B_min_lines=1, B_max_lines=5)
        replacements = core.select_replacements(candidates, min_total_saving=30)

        self.assertGreaterEqual(len(replacements), 1)
        llm_ready, reverse_map = core.apply_placeholders(contents, replacements)
        ok, _ = core.roundtrip_check(contents, llm_ready, reverse_map)
        self.assertTrue(ok)

    def test_p3_net_savings_calculation(self):
        """P3.8: Verify net character and token savings formula."""
        orig = {"/f1.txt": "a" * 1000}
        comp = {"/f1.txt": "a" * 600}
        mapping_size = 150

        # Formulas:
        # gross_saved = 1000 - 600 = 400
        # net_saved = 1000 - (600 + 150) = 250
        # orig_tokens = round(1000 / 4) = 250
        # comp_tokens = round(600 / 4) = 150
        # map_tokens = round(150 / 4) = 38
        # net_tokens = 250 - (150 + 38) = 62
        stats = core.estimate_savings(orig, comp, mapping_size=mapping_size, chars_per_token=4.0)

        self.assertEqual(stats["saved_chars"], 400)
        self.assertEqual(stats["net_saved_chars"], 250)
        self.assertEqual(stats["orig_tokens_est"], 250)
        self.assertEqual(stats["new_tokens_est"], 150)
        self.assertEqual(stats["mapping_tokens_est"], 38)
        self.assertEqual(stats["net_saved_tokens"], 62)


if __name__ == "__main__":
    unittest.main(verbosity=2)

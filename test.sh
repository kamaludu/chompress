#!/usr/bin/env bash
# ==============================================================================
# File: test.sh
# Description: End-to-end integration and smoke-test harness for chunk-compress.
#              Tests CLI argument parsing, directory tree preservation,
#              exact roundtrip verification (default lossy vs. pure lossless),
#              boundary-aware atomic chunking, and executes the unit test suite.
# ==============================================================================

set -e

echo "=== 1. PREPARING TEST DATA (NESTED DIRECTORIES & REPETITIVE CODE) ==="
rm -rf test_input test_output test_output_lossless test_output_chunks
mkdir -p test_input/nested

# Generate test fixtures containing multi-line repetitions and empty lines
python3 -c '
header = "/*\n * Copyright (C) 2026 Enterprise Corp.\n * All rights reserved.\n */\n\n"
func = "def standard_handler_routine(event, context):\n    validate_input(event)\n    return process_record(context)\n\n"
body = "\n".join([f"var_{i} = calculate_value({i})\n" for i in range(200)])

with open("test_input/service_a.py", "w") as f:
    f.write(header + (func * 15) + body)

with open("test_input/service_b.py", "w") as f:
    f.write(header + (func * 12) + body)

with open("test_input/nested/module.py", "w") as f:
    f.write(header + (func * 8) + body)

with open("test_input/readme.md", "w") as f:
    f.write("# Project Docs\n\nEmpty lines in markdown must remain untouched.\n\nEnd of doc.\n")
'
echo "Generated input files under test_input/:"
ls -lh test_input/
ls -lh test_input/nested/

echo ""
echo "=== 2. STANDARD COMPRESSION + EXACT ROUNDTRIP + MANIFEST (P0.1, P0.3, P3.8) ==="
python3 cli.py -i test_input -o test_output --verify-roundtrip --export-manifest

# Verify that nested directory structure was preserved
if [ ! -f "test_output/nested/module.py" ]; then
    echo "ERROR: Directory structure not preserved in test_output/nested/module.py" >&2
    exit 1
fi

echo ""
echo "=== 3. PURE LOSSLESS MODE (--keep-empty-lines) ==="
python3 cli.py -i test_input -o test_output_lossless --keep-empty-lines --verify-roundtrip

echo ""
echo "=== 4. BOUNDARY-AWARE ATOMIC CHUNKING (P0.2) ==="
python3 cli.py -i test_input -o test_output_chunks --chunk-output --chunk-size 2048 --verify-roundtrip

echo ""
echo "Inspecting generated chunks directory:"
ls -lh test_output_chunks/chunks/
ls -lh test_output_chunks/chunks/service_a.py/
ls -lh test_output_chunks/chunks/nested/module.py/

echo ""
echo "=== 5. EXECUTING UNIT TEST SUITE ==="
python3 test_suite.py

echo ""
echo "==================================================================="
echo "ALL INTEGRATION, CLI, AND UNIT TESTS COMPLETED SUCCESSFULLY."
echo "==================================================================="

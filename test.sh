#!/usr/bin/env bash
# ==============================================================================
# File: test.sh
# Description: End-to-end integration and smoke-test harness for chompress.
# Enforces POSIX line endings (\n) to prevent shell carriage return errors (P0.1).
# Verifies P0 token economy, P1 domain minifiers, P2 BPE/Multi-Range,
# P3 license/error compaction, polyglot configs, P3.3 stdout/pipe streaming,
# P4.1 unused import pruning, P4.2 assert pruning, and P4.3 prompt envelope.
#
# Mathematical token model (pure ASCII notation):
# net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
# net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
# ==============================================================================

set -e

echo "=== 1. PREPARING TEST DATA (PYTHON, BASH, MARKDOWN, JSON, YAML) ==="
rm -rf test_input test_output test_output_lossless test_output_single test_output_chunks test_stdout.txt test_stdout_envelope.txt test_pipe.txt
mkdir -p test_input/nested

python3 -c '
header = "/*\n * Copyright (C) 2026 Enterprise Corp.\n * SPDX-License-Identifier: GPL-3.0-or-later\n * All rights reserved.\n */\n\n"
imports = "import os\nimport sys\nimport math\nfrom typing import List, Dict, Optional, Union\n\n"
func = """def standard_handler_routine(event: dict, context: object = None) -> bool:
    \"\"\"Process incoming event record and return status.\"\"\"
    assert event is not None, "Event parameter cannot be None"
    local_accumulator: float = 0.0
    if event is None:
        raise ValueError("The provided event parameter is completely invalid and null")
    validate_input(event)
    return process_record(context)

"""
body = "\n".join([f"var_{i} = calculate_value({i})\n" for i in range(200)])

with open("test_input/service_a.py", "w", encoding="utf-8") as f:
    f.write(header + imports + (func * 15) + body)

with open("test_input/service_b.py", "w", encoding="utf-8") as f:
    f.write(header + imports + (func * 12) + body)

with open("test_input/nested/module.py", "w", encoding="utf-8") as f:
    f.write(header + imports + (func * 8) + body)

with open("test_input/deploy.sh", "w", encoding="utf-8") as f:
    f.write(
        "#!/usr/bin/env bash\n"
        "# Copyright 2026 Deployment Automation\n"
        "# License: Apache-2.0\n"
        "echo -e \"\\033[32m[STARTING]\\033[0m Deploying services...\"\n"
        "python3 service_a.py\n"
        "exit 0\n"
    )

with open("test_input/readme.md", "w", encoding="utf-8") as f:
    f.write(
        "# Project Docs\n\n"
        "[![Build Status](https://img.shields.io/github/actions/workflow/test.yml)](https://ci.org)\n\n"
        "|   Service   |   Status   |\n"
        "|:------------|-----------:|\n"
        "|   srv_a     |   active   |\n"
        "|   srv_b     |   active   |\n\n"
        "End of doc.\n"
    )

with open("test_input/config.json", "w", encoding="utf-8") as f:
    f.write("{\n  \"service\": \"api_gateway\",\n  \"port\": 8080,\n  \"active\": true\n}\n")

with open("test_input/config.yaml", "w", encoding="utf-8") as f:
    f.write("# Environment Configuration\nversion: '3.8'\nservices:\n  gateway:\n    image: nginx\n")
'
echo "Generated input files under test_input/:"
ls -lh test_input/
ls -lh test_input/nested/

echo ""
echo "=== 2. AGGRESSIVE MODE + P1-P4 CANONICALIZATION + DEDUPLICATION ==="
python3 chompress.py -i test_input -o test_output --mode aggressive --verify-roundtrip --export-manifest

# Verify directory structure was preserved
if [ ! -f "test_output/nested/module.py" ]; then
    echo "ERROR: Directory structure not preserved in test_output/nested/module.py" >&2
    exit 1
fi

# Verify Python docstrings and types were stripped
if grep -q "Process incoming event record" test_output/service_a.py; then
    echo "ERROR: Docstrings were not stripped from service_a.py" >&2
    exit 1
fi

# Verify P3.1 License headers were stripped
if grep -q "Enterprise Corp" test_output/service_a.py; then
    echo "ERROR: License header was not stripped from service_a.py" >&2
    exit 1
fi

# Verify P3.2 Error strings were compacted
if grep -q "The provided event parameter is completely invalid" test_output/service_a.py; then
    echo "ERROR: Verbose error string was not compacted in service_a.py" >&2
    exit 1
fi

# Verify P4.1 Unused imports and typing aliases were pruned
if grep -q "from typing import" test_output/service_a.py; then
    echo "ERROR: Unused typing imports were not stripped from service_a.py" >&2
    exit 1
fi
if grep -q "import os" test_output/service_a.py; then
    echo "ERROR: Unused import os was not stripped from service_a.py" >&2
    exit 1
fi

# Verify P4.2 Assertions were pruned
if grep -q "assert event is not None" test_output/service_a.py; then
    echo "ERROR: Assertion statement was not pruned from service_a.py" >&2
    exit 1
fi

# Verify Bash ANSI escapes were stripped
if grep -q "\\\\033\\[32m" test_output/deploy.sh; then
    echo "ERROR: ANSI escape sequences were not stripped from deploy.sh" >&2
    exit 1
fi

# Verify Markdown badges were stripped
if grep -q "img.shields.io" test_output/readme.md; then
    echo "ERROR: Shields.io badges were not stripped from readme.md" >&2
    exit 1
fi

# Verify P3.4 JSON visual whitespace compaction
if grep -q "  \"service\"" test_output/config.json; then
    echo "ERROR: JSON visual whitespace was not compacted in config.json" >&2
    exit 1
fi

echo ""
echo "=== 3. SINGLE-FILE FIRST DIRECT COMPRESSION WORKFLOW ==="
python3 chompress.py -i test_input/service_a.py -o test_output_single --mode aggressive --verify-roundtrip
if [ ! -f "test_output_single/service_a.py" ]; then
    echo "ERROR: Single file direct output missing in test_output_single/service_a.py" >&2
    exit 1
fi

echo ""
echo "=== 4. P3.3 & P4.3 DIRECT LLM CONTEXT STREAMING (--stdout, --envelope AND STDIN PIPE) ==="
python3 chompress.py -i test_input/service_a.py --stdout > test_stdout.txt
if [ ! -s "test_stdout.txt" ]; then
    echo "ERROR: --stdout produced an empty stream" >&2
    exit 1
fi
if ! grep -q "\[MAP:" test_stdout.txt; then
    echo "ERROR: --stdout stream is missing protocol header" >&2
    exit 1
fi

# Test P4.3 LLM Prompt Envelope wrapping
python3 chompress.py -i test_input/service_a.py --stdout --envelope > test_stdout_envelope.txt
if ! grep -q "<context>" test_stdout_envelope.txt; then
    echo "ERROR: Prompt envelope <context> tag missing in test_stdout_envelope.txt" >&2
    exit 1
fi
if ! grep -q "</context>" test_stdout_envelope.txt; then
    echo "ERROR: Prompt envelope </context> tag missing in test_stdout_envelope.txt" >&2
    exit 1
fi
if ! grep -q "\[LLM-READY COMPRESSED CONTEXT" test_stdout_envelope.txt; then
    echo "ERROR: Prompt envelope instruction header missing in test_stdout_envelope.txt" >&2
    exit 1
fi

# Test UNIX stdin pipe
cat test_input/service_a.py | python3 chompress.py -i - --stdout > test_pipe.txt
if [ ! -s "test_pipe.txt" ]; then
    echo "ERROR: Stdin pipe produced an empty stream" >&2
    exit 1
fi

echo "P3.3 and P4.3 direct context stream verified successfully (envelope stream: $(wc -c < test_stdout_envelope.txt) bytes)."

echo ""
echo "=== 5. PURE LOSSLESS MODE (--mode lossless) ==="
python3 chompress.py -i test_input -o test_output_lossless --mode lossless --verify-roundtrip

echo ""
echo "=== 6. BOUNDARY-AWARE ATOMIC CHUNKING (P0.2) ==="
python3 chompress.py -i test_input -o test_output_chunks --chunk-output --chunk-size 2048 --verify-roundtrip

echo ""
echo "Inspecting generated chunks directory:"
ls -lh test_output_chunks/chunks/
ls -lh test_output_chunks/chunks/service_a.py/
ls -lh test_output_chunks/chunks/nested/module.py/

echo ""
echo "=== 7. EXECUTING COMPREHENSIVE UNIT TEST SUITE (30 TESTS) ==="
python3 test_suite.py

echo ""
echo "==================================================================="
echo "ALL P0, P1, P2, P3, AND P4 INTEGRATION, CLI, AND UNIT TESTS COMPLETED SUCCESSFULLY."
echo "==================================================================="

#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: minifiers.py (P1, P3 & P4 Semantic Canonicalization & Aggressive Compactor)
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Safe, language-aware semantic minifiers and aggressive LLM canonicalizers:
- License & Boilerplate Annihilation (P3.1): Strips verbose top-level copyright notices,
  SPDX tags, and multi-line license headers while strictly preserving shebangs (#!/...).
- Python AST Compactor (P1.1, P3.2, P4.1 & P4.2):
  * AST-based removal of docstrings and PEP 484/526 type annotations.
  * P3.2 Human Error & Log String Compaction: Shortens verbose exception strings
    (raise ValueError("...")) and logger calls to concise semantic tokens.
  * P4.1 Unused Import & Type Alias Annihilation: Strips unused imports, dead type aliases,
    and leftover typing imports after type annotation removal.
  * P4.2 Assertions & Diagnostic Statement Pruning: Eliminates assert statements
    and diagnostic checks in aggressive LLM compression mode.
  * Conservative local variable renaming (_v1, _v2) on safe scopes.
  * Executable integrity verified via compile().
- Bash Canonicalizer (P1.1): Strips ANSI terminal escape codes, full-line comments,
  and collapses trailing whitespace runs.
- Markdown Canonicalizer (P1.2): Strips shields.io/CI status badges and compacts table cell visual padding.
- Polyglot Config Minifiers (P3.4):
  * JSON: Whitespace and indentation stripping.
  * YAML/YML: Safe comment and redundant blank line elimination.

Mathematical token model (pure ASCII notation):
tokens_license_saved = sum(i=1 to n_files, tokens(license_header_i) - tokens(lic_marker))
ROI_license_pct = ((tokens_license_saved) * 100.0) / (original_tokens)
tokens_err_saved = sum(j=1 to m_exceptions, tokens(verbose_str_j) - tokens(short_id_j))
tokens_import_saved = sum(k=1 to p_imports, tokens(unused_import_k))
tokens_assert_saved = sum(q=1 to r_asserts, tokens(assert_stmt_q))
net_tokens_saved = original_tokens - (compressed_payload_tokens + mapping_tokens + protocol_tokens)
net_compression_ratio = ((net_tokens_saved) * 100.0) / (original_tokens)
"""

import ast
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# 0. LICENSE AND BOILERPLATE HEADER ANNIHILATOR (P3.1)
# ==============================================================================

LICENSE_KEYWORDS_RE = re.compile(
    r"(?:copyright\s+(?:\(c\)|©|\d{4})|license|spdx-license-identifier|all rights reserved)",
    re.IGNORECASE,
)


def strip_license_header(code: str, ext: str) -> str:
    """
    P3.1: Strips verbose top-level license and copyright blocks.
    - Preserves shebang (#!/...) on the first line.
    - Matches multi-line C-style comment headers (/* ... */).
    - Matches consecutive single-line comment blocks (# or //).
    - Leaves the code structurally intact if no license keywords are found.
    """
    if not code:
        return ""

    lines = code.splitlines(keepends=True)
    if not lines:
        return ""

    shebang = ""
    start_idx = 0
    if lines[0].startswith("#!"):
        shebang = lines[0]
        start_idx = 1

    remaining_text = "".join(lines[start_idx:])
    trimmed_remaining = remaining_text.lstrip()

    # Check 1: C-style block comments /* ... */
    if trimmed_remaining.startswith("/*"):
        end_block = trimmed_remaining.find("*/")
        if end_block != -1:
            comment_block = trimmed_remaining[: end_block + 2]
            if LICENSE_KEYWORDS_RE.search(comment_block):
                after_block = trimmed_remaining[end_block + 2 :].lstrip("\r\n")
                return (shebang + after_block) if shebang else after_block

    # Check 2: Consecutive single-line comments (# or //)
    comment_lines: List[str] = []
    code_start_idx = start_idx
    for idx in range(start_idx, min(len(lines), start_idx + 40)):
        ln = lines[idx]
        stripped = ln.strip()
        if stripped.startswith(("#", "//", "/*", "*", "*/")):
            comment_lines.append(ln)
            code_start_idx = idx + 1
        elif not stripped:
            comment_lines.append(ln)
            code_start_idx = idx + 1
        else:
            break

    if comment_lines:
        full_comment = "".join(comment_lines)
        if LICENSE_KEYWORDS_RE.search(full_comment):
            after_comments = "".join(lines[code_start_idx:]).lstrip("\r\n")
            return (shebang + after_comments) if shebang else after_comments

    return code


# ==============================================================================
# 1. BASH MINIFIER (SAFE SUBSET WITH ANSI & COMMENT STRIPPING)
# ==============================================================================

# Regex matching ANSI escape sequences (terminal color and control codes).
ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1b|\033|\\e|\\033|\\x1b)\[[0-9;]*[a-zA-Z]"
)


def minify_bash(
    code: str,
    remove_comments: bool = True,
    remove_ansi: bool = True,
) -> str:
    """
    Safe Bash canonicalizer:
    - Preserves shebang (#!/...) on the first line.
    - Strips full-line comments whose first non-whitespace char is '#'.
    - Strips ANSI escape sequences (color codes and cursor commands) when remove_ansi is True.
    - Removes trailing spaces from each line.
    - Collapses runs of multiple blank lines into a single blank line.
    - Leaves inline comments and quotes untouched to avoid breaking shell expansions.
    """
    lines = code.splitlines(keepends=False)
    if not lines:
        return ""

    out_lines: List[str] = []
    prev_empty = False

    for i, line in enumerate(lines):
        # Always preserve shebang on line 0
        if i == 0 and line.startswith("#!"):
            out_lines.append(line.rstrip())
            continue

        current_line = line
        if remove_ansi:
            current_line = ANSI_ESCAPE_RE.sub("", current_line)

        stripped = current_line.strip()

        # Remove whole-line comments safely
        if remove_comments and stripped.startswith("#"):
            continue

        # Handle empty lines
        if not stripped:
            if not prev_empty and out_lines:
                out_lines.append("")
                prev_empty = True
            continue

        prev_empty = False
        out_lines.append(current_line.rstrip())

    result = "\n".join(out_lines)
    if code.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


# ==============================================================================
# 2. MARKDOWN CANONICALIZER (BADGE & TABLE COMPACTION)
# ==============================================================================

# Regex matching Markdown badge links: [![Alt](image_url)](link_url)
BADGE_MD_LINK_RE = re.compile(
    r"\[!\[[^\]]*\]\((?:https?://)?[^\)]*(?:shields\.io|badgen\.net|codecov|travis-ci|github\.com/[^/]+/[^/]+/actions/workflows)[^\)]*\)\]\([^\)]*\)"
)

# Regex matching standalone Markdown badge images: ![Alt](image_url)
BADGE_MD_IMG_RE = re.compile(
    r"!\[[^\]]*\]\((?:https?://)?[^\)]*(?:shields\.io|badgen\.net|codecov|travis-ci)[^\)]*\)"
)

# Regex matching HTML badge links and images
BADGE_HTML_RE = re.compile(
    r"<a\s+[^>]*>\s*<img\s+[^>]*(?:shields\.io|badgen\.net|codecov)[^>]*>\s*</a>|<img\s+[^>]*(?:shields\.io|badgen\.net|codecov)[^>]*>",
    re.IGNORECASE,
)


def _compact_markdown_table_row(row_line: str) -> str:
    """
    Compacts table rows by stripping visual padding spaces inside cells:
    '|  col1     |  col2        |' -> '| col1 | col2 |'
    """
    stripped = row_line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return row_line

    cells = stripped.split("|")
    # First and last are empty strings due to leading/trailing pipe
    inner_cells = cells[1:-1]

    compact_cells: List[str] = []
    for cell in inner_cells:
        c = cell.strip()
        # Preserve separator alignment dashes (e.g. :---: or ---)
        if re.match(r"^:?-+:?$", c):
            compact_cells.append(c)
        else:
            compact_cells.append(f" {c} " if c else " ")

    return "|" + "|".join(compact_cells) + "|"


def minify_markdown(
    doc: str,
    compact_tables: bool = True,
    remove_badges: bool = True,
) -> str:
    """
    Safe Markdown compactor:
    - Removes visual badges (shields.io, workflow status, codecov).
    - Compacts visual whitespace in Markdown tables (high token ROI).
    - Collapses 3 or more consecutive newlines down to 2 (preserves paragraph break).
    - Leaves YAML front matter, headers, and code fences structurally intact.
    """
    lines = doc.splitlines(keepends=False)
    out_lines: List[str] = []
    in_code_block = False
    prev_blank = False

    for line in lines:
        # Check code fence boundaries
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            out_lines.append(line.rstrip())
            prev_blank = False
            continue

        if in_code_block:
            out_lines.append(line)
            continue

        current_line = line
        if remove_badges:
            current_line = BADGE_MD_LINK_RE.sub("", current_line)
            current_line = BADGE_MD_IMG_RE.sub("", current_line)
            current_line = BADGE_HTML_RE.sub("", current_line)

        stripped = current_line.strip()

        # Handle blank lines
        if not stripped:
            if not prev_blank and out_lines:
                out_lines.append("")
                prev_blank = True
            continue

        prev_blank = False

        # Table row compaction
        if compact_tables and stripped.startswith("|") and stripped.endswith("|"):
            out_lines.append(_compact_markdown_table_row(current_line))
        else:
            out_lines.append(current_line.rstrip())

    result = "\n".join(out_lines)
    if doc.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


# ==============================================================================
# 3. PYTHON AST CONSERVATIVE & AGGRESSIVE MINIFIER
# ==============================================================================

class _DocstringStripper(ast.NodeTransformer):
    """
    Strips module, class, and function docstrings.
    Replaces body with 'pass' if docstring was the only statement in block.
    """

    def _strip_docstring(self, node: ast.AST) -> None:
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            return
        first = body[0]
        if isinstance(first, ast.Expr):
            val = getattr(first, "value", None)
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                if len(body) == 1 and not isinstance(node, ast.Module):
                    node.body = [ast.copy_location(ast.Pass(), first)]
                else:
                    node.body = body[1:]
                    if not node.body and not isinstance(node, ast.Module):
                        node.body = [ast.copy_location(ast.Pass(), first)]

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self.generic_visit(node)
        self._strip_docstring(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        self._strip_docstring(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        self._strip_docstring(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        self._strip_docstring(node)
        return node


class _TypeAnnotationStripper(ast.NodeTransformer):
    """
    Removes PEP 484 and PEP 526 type annotations:
    - Removes function argument annotations and return type annotations.
    - Converts annotated assignment (x: int = 5) into plain assignment (x = 5).
    - Eliminates bare variable annotations (x: int) without value.
    - Ensures non-empty bodies with 'pass' to preserve valid Python syntax.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.returns = None
        self._clean_arguments(node.args)
        self.generic_visit(node)
        self._ensure_non_empty_body(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        node.returns = None
        self._clean_arguments(node.args)
        self.generic_visit(node)
        self._ensure_non_empty_body(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        self._ensure_non_empty_body(node)
        return node

    def _clean_arguments(self, args: ast.arguments) -> None:
        for arg in getattr(args, "posonlyargs", []):
            arg.annotation = None
        for arg in args.args:
            arg.annotation = None
        for arg in getattr(args, "kwonlyargs", []):
            arg.annotation = None
        if args.vararg:
            args.vararg.annotation = None
        if args.kwarg:
            args.kwarg.annotation = None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Optional[ast.AST]:
        if node.value is not None:
            assign_node = ast.Assign(targets=[node.target], value=node.value)
            return ast.copy_location(assign_node, node)
        return None

    def _ensure_non_empty_body(self, node: ast.AST) -> None:
        if hasattr(node, "body") and not node.body:
            node.body = [ast.copy_location(ast.Pass(), node)]


class _ErrorAndLogStringCompactor(ast.NodeTransformer):
    """
    P3.2: Human Error & Log Message Compactor.
    In LLM context compression, human readability is not a requirement.
    Compacts verbose human explanation strings in:
    - Exceptions: raise ValueError("very long message...") -> raise ValueError("ERR")
    - Logging calls: logger.info("verbose log...") -> logger.info("LOG")
    Preserves exception types, control flow logic, and non-constant arguments.
    """

    LOG_METHOD_NAMES = {
        "debug", "info", "warning", "warn", "error", "critical", "exception", "log"
    }

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.exc, ast.Call):
            for i, arg in enumerate(node.exc.args):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if len(arg.value) > 8:
                        node.exc.args[i] = ast.copy_location(
                            ast.Constant(value="ERR"), arg
                        )
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        is_log_call = False
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.LOG_METHOD_NAMES:
            if isinstance(node.func.value, ast.Name) and (
                "log" in node.func.value.id.lower() or node.func.value.id in ("self", "cls")
            ):
                is_log_call = True

        if is_log_call and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                if len(first_arg.value) > 8:
                    node.args[0] = ast.copy_location(
                        ast.Constant(value="LOG"), first_arg
                    )

        return node


class _AssertPruner(ast.NodeTransformer):
    """
    P4.2: Assertions and Diagnostic Statement Pruner.
    Strips assert statements in aggressive LLM compression mode.
    Preserves syntactic validity via _EmptyBodyFixer.
    """

    def visit_Assert(self, node: ast.Assert) -> Optional[ast.AST]:
        return None


class _UsedNamesCollector(ast.NodeVisitor):
    """
    Collects all identifiers actually referenced (loaded) across the AST.
    Accounts for runtime references, decorators, base classes, and __all__ exports.
    Excludes import statements themselves so unreferenced imports can be identified.
    """

    def __init__(self) -> None:
        self.used_names: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        pass

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        pass

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            self.used_names.add(elt.value)
        self.generic_visit(node)


class _UnusedImportPruner(ast.NodeTransformer):
    """
    P4.1: Unused Import & Type Alias Annihilator.
    Prunes imported names that are never loaded in runtime code.
    Safely eliminates dead modules and unused typing imports (List, Dict, etc.)
    once type annotations have been stripped.
    Always preserves '__future__' imports and wildcard imports ('*').
    """

    def __init__(self, used_names: Set[str]) -> None:
        self.used_names = used_names

    def visit_Import(self, node: ast.Import) -> Optional[ast.AST]:
        kept_names = []
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".")[0]
            if bound_name in self.used_names:
                kept_names.append(alias)
        if not kept_names:
            return None
        node.names = kept_names
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Optional[ast.AST]:
        # Always preserve from __future__ import ...
        if node.module == "__future__":
            return node
        # Preserve wildcard imports
        if any(alias.name == "*" for alias in node.names):
            return node

        kept_names = []
        for alias in node.names:
            bound_name = alias.asname or alias.name
            if bound_name in self.used_names:
                kept_names.append(alias)
        if not kept_names:
            return None
        node.names = kept_names
        return node


class _EmptyBodyFixer(ast.NodeTransformer):
    """
    Ensures that any block whose body was emptied by stripping (docstrings, asserts,
    annotations, or unused imports) contains at least one statement ('pass')
    to preserve valid Python syntax.
    """

    def generic_visit(self, node: ast.AST) -> ast.AST:
        super().generic_visit(node)
        for attr in ("body", "orelse", "finalbody"):
            b = getattr(node, attr, None)
            if isinstance(b, list) and len(b) == 0 and not isinstance(node, ast.Module):
                setattr(node, attr, [ast.copy_location(ast.Pass(), node)])
        return node


class _LocalScopeAnalyzer(ast.NodeVisitor):
    """
    Analyzes a FunctionDef node to determine if local variable renaming is safe:
    - Bails out if dynamic reflection is detected (eval, exec, locals, globals,
      getattr, setattr, hasattr, vars).
    - Excludes argument names, imported aliases, globals, nonlocals, and dunder names.
    - Identifies strictly local variables that never escape to global or closure scope.
    """

    DANGEROUS_CALLS = {
        "eval", "exec", "locals", "globals", "getattr", "setattr", "hasattr", "vars"
    }

    def __init__(self, func_node: ast.AST):
        self.func_node = func_node
        self.is_safe = True
        self.stored_names: Set[str] = set()
        self.loaded_names: Set[str] = set()
        self.excluded_names: Set[str] = set()

        args_node = getattr(func_node, "args", None)
        if args_node:
            for arg in getattr(args_node, "posonlyargs", []):
                self.excluded_names.add(arg.arg)
            for arg in args_node.args:
                self.excluded_names.add(arg.arg)
            if args_node.vararg:
                self.excluded_names.add(args_node.vararg.arg)
            if args_node.kwarg:
                self.excluded_names.add(args_node.kwarg.arg)
            for arg in getattr(args_node, "kwonlyargs", []):
                self.excluded_names.add(arg.arg)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.DANGEROUS_CALLS:
            self.is_safe = False
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self.excluded_names.add(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.excluded_names.add(name)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.excluded_names.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.excluded_names.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is not self.func_node:
            self.excluded_names.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is not self.func_node:
            self.excluded_names.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.excluded_names.add(node.name)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__") and node.id.endswith("__"):
            self.excluded_names.add(node.id)
            return

        if isinstance(node.ctx, ast.Store):
            self.stored_names.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.loaded_names.add(node.id)

    def get_renamable_locals(self) -> Dict[str, str]:
        """Returns mapping from old_name -> short_name if safe, else empty dict."""
        if not self.is_safe:
            return {}

        candidates = self.stored_names - self.excluded_names
        renamable: Dict[str, str] = {}
        counter = 1
        for name in sorted(candidates):
            if len(name) > 3:
                short_id = f"_v{counter}"
                renamable[name] = short_id
                counter += 1

        return renamable


class _LocalRenamer(ast.NodeTransformer):
    """Applies local variable renaming to a function AST node."""

    def __init__(self, rename_map: Dict[str, str]):
        self.rename_map = rename_map

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self.rename_map:
            return ast.copy_location(
                ast.Name(id=self.rename_map[node.id], ctx=node.ctx), node
            )
        return node


def minify_python(
    code: str,
    rename_locals: bool = True,
    strip_docstrings: bool = True,
    strip_types: bool = True,
    compact_error_strings: bool = True,
    prune_imports: bool = True,
    prune_asserts: bool = True,
) -> str:
    """
    Conservative & Aggressive Python AST minifier (P1, P3, P4):
    - Parses AST and checks for syntax validity.
    - Strips docstrings when strip_docstrings is True.
    - Strips PEP 484/526 type annotations when strip_types is True.
    - Compacts verbose exception and logger strings when compact_error_strings is True (P3.2).
    - Prunes diagnostic assert statements when prune_asserts is True (P4.2).
    - Prunes unused imports and dead typing modules when prune_imports is True (P4.1).
    - Performs safe local-only variable renaming when rename_locals is True.
    - Preserves syntactic validity across empty blocks via _EmptyBodyFixer.
    - Unparses AST back to valid Python code.
    - Verifies executable equivalence via compile().
    - Returns original code safely on any error or bailout.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    try:
        if strip_docstrings:
            tree = _DocstringStripper().visit(tree)

        if strip_types:
            tree = _TypeAnnotationStripper().visit(tree)

        if compact_error_strings:
            tree = _ErrorAndLogStringCompactor().visit(tree)

        if prune_asserts:
            tree = _AssertPruner().visit(tree)

        if prune_imports:
            collector = _UsedNamesCollector()
            collector.visit(tree)
            tree = _UnusedImportPruner(collector.used_names).visit(tree)

        if rename_locals:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, getattr(ast, "AsyncFunctionDef", ()))):
                    analyzer = _LocalScopeAnalyzer(node)
                    analyzer.visit(node)
                    mapping = analyzer.get_renamable_locals()
                    if mapping:
                        renamer = _LocalRenamer(mapping)
                        for stmt in node.body:
                            renamer.visit(stmt)

        tree = _EmptyBodyFixer().visit(tree)
        ast.fix_missing_locations(tree)
    except Exception:
        return code

    try:
        if hasattr(ast, "unparse"):
            transformed_code = ast.unparse(tree)
        else:
            return code

        compile(transformed_code, "<minified>", "exec")
        return transformed_code
    except Exception:
        return code


# ==============================================================================
# 4. POLYGLOT CONFIGURATION MINIFIERS (JSON & YAML - P3.4)
# ==============================================================================

def minify_json(code: str) -> str:
    """
    P3.4: Compacts JSON files by stripping formatting whitespace.
    Preserves exact JSON semantics without string modification.
    """
    stripped = code.strip()
    if not stripped:
        return ""
    try:
        obj = json.loads(stripped)
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return code


def minify_yaml(code: str) -> str:
    """
    P3.4: Compacts YAML/YML files by stripping full-line comments
    and collapsing redundant empty lines while preserving indentation.
    """
    lines = code.splitlines(keepends=False)
    out_lines: List[str] = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            if not prev_blank and out_lines:
                out_lines.append("")
                prev_blank = True
            continue
        prev_blank = False
        out_lines.append(line.rstrip())
    res = "\n".join(out_lines)
    if code.endswith("\n") and not res.endswith("\n"):
        res += "\n"
    return res


# ==============================================================================
# 5. UNIFIED DISPATCHER
# ==============================================================================

def canonicalize_content(
    file_path: str,
    content: str,
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
) -> str:
    """
    Dispatches content to the appropriate safe minifier based on file extension.
    Applies P3.1 license header stripping, P3.2 error compaction, P3.4 config minification,
    P4.1 unused import pruning, and P4.2 assertion pruning.
    """
    p = Path(file_path)
    ext = p.suffix.lower()
    name = p.name.lower()

    # Apply P3.1 top-level license stripping across all code files
    if enable_license_stripping and ext in (
        ".py", ".sh", ".bash", ".js", ".ts", ".c", ".h", ".cpp", ".rs", ".go"
    ):
        content = strip_license_header(content, ext)

    # Bash / Shell files
    if ext in (".sh", ".bash") or name in ("bash4llm", "configure"):
        return minify_bash(
            content,
            remove_comments=enable_comments_removal,
            remove_ansi=enable_ansi_stripping,
        )

    # Markdown documentation
    if ext in (".md", ".markdown"):
        return minify_markdown(
            content,
            compact_tables=enable_table_compaction,
            remove_badges=enable_badge_removal,
        )

    # Python source files (P1, P3, P4)
    if ext == ".py":
        return minify_python(
            content,
            rename_locals=enable_python_renaming,
            strip_docstrings=enable_docstring_removal,
            strip_types=enable_type_annotations_removal,
            compact_error_strings=enable_error_string_compaction,
            prune_imports=enable_import_pruning,
            prune_asserts=enable_assert_pruning,
        )

    # JSON configuration (P3.4)
    if ext == ".json":
        return minify_json(content)

    # YAML configuration (P3.4)
    if ext in (".yaml", ".yml"):
        return minify_yaml(content)

    return content

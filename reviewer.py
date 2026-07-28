#!/usr/bin/env python3
"""
AI Code Reviewer — CLI tool that uses Claude to review source code for bugs,
security issues, style problems, and performance concerns.

Usage:
    python reviewer.py path/to/file_or_directory
    python reviewer.py path/to/project/ --output report.md
    python reviewer.py path/to/file.py --json report.json
"""

import os
import sys
import json
import time
import argparse
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2000
MAX_CHARS_PER_CHUNK = 6000
RETRY_LIMIT = 3
RETRY_BACKOFF_SECONDS = 2

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".c", ".cpp"}
IGNORE_PATTERNS = ["*/node_modules/*", "*/.git/*", "*/venv/*", "*/__pycache__/*", "*/dist/*", "*/build/*"]

SEVERITY_ORDER = {"critical": 0, "warning": 1, "suggestion": 2}
SEVERITY_ICON = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}

REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. You will be shown a chunk of source code.
Analyze it carefully for:
- bugs (logic errors, off-by-one errors, null/undefined handling, race conditions)
- security issues (injection, unsafe deserialization, hardcoded secrets, unsafe eval, etc.)
- style issues (naming, structure, readability, violations of common conventions for the language)
- performance issues (unnecessary loops, inefficient data structures, blocking calls)

Respond with ONLY valid JSON (no markdown fences, no preamble), matching this schema exactly:

{
  "issues": [
    {
      "line": <int or null>,
      "severity": "critical" | "warning" | "suggestion",
      "category": "bug" | "security" | "style" | "performance",
      "summary": "<one line description>",
      "explanation": "<1-3 sentence explanation of why this matters and how to fix it>"
    }
  ]
}

If there are no issues, return {"issues": []}. Do not invent line numbers you are not
reasonably confident about — use null if unsure. Be precise and avoid generic filler feedback.
"""


@dataclass
class Issue:
    file: str
    line: Optional[int]
    severity: str
    category: str
    summary: str
    explanation: str


@dataclass
class ChunkResult:
    file: str
    chunk_index: int
    issues: List[Issue] = field(default_factory=list)
    error: Optional[str] = None


def discover_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target] if target.suffix in SUPPORTED_EXTENSIONS else []

    files = []
    for root, dirs, filenames in os.walk(target):
        dirs[:] = [d for d in dirs if not any(
            fnmatch.fnmatch(os.path.join(root, d), pat) for pat in IGNORE_PATTERNS
        )]
        for fname in filenames:
            full = Path(root) / fname
            if full.suffix in SUPPORTED_EXTENSIONS:
                if not any(fnmatch.fnmatch(str(full), pat) for pat in IGNORE_PATTERNS):
                    files.append(full)
    return sorted(files)


def chunk_source(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    lines = text.splitlines(keepends=True)
    chunks, current, current_len = [], [], 0

    for line in lines:
        if current_len + len(line) > max_chars and current:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)

    if current:
        chunks.append("".join(current))

    return chunks if chunks else [text]


def review_chunk(client: anthropic.Anthropic, filename: str, chunk: str, chunk_index: int) -> ChunkResult:
    prompt = f"File: {filename} (chunk {chunk_index + 1})\n\n```\n{chunk}\n```"

    last_error = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=REVIEW_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.lower().startswith("json"):
                    raw_text = raw_text[4:]

            parsed = json.loads(raw_text)
            issues = [
                Issue(
                    file=filename,
                    line=item.get("line"),
                    severity=item.get("severity", "suggestion"),
                    category=item.get("category", "style"),
                    summary=item.get("summary", ""),
                    explanation=item.get("explanation", ""),
                )
                for item in parsed.get("issues", [])
            ]
            return ChunkResult(file=filename, chunk_index=chunk_index, issues=issues)

        except anthropic.RateLimitError as e:
            last_error = f"Rate limited: {e}"
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        except anthropic.APIStatusError as e:
            last_error = f"API error ({e.status_code}): {e}"
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        except json.JSONDecodeError as e:
            last_error = f"Could not parse model response as JSON: {e}"
            break
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            break

    return ChunkResult(file=filename, chunk_index=chunk_index, error=last_error)


def print_terminal_report(results: List[ChunkResult]):
    all_issues = [i for r in results for i in r.issues]
    errors = [r for r in results if r.error]

    print("\n" + "=" * 60)
    print("  AI CODE REVIEW REPORT")
    print("=" * 60)

    if not all_issues and not errors:
        print("\n✅ No issues found. Code looks clean.\n")
        return

    all_issues.sort(key=lambda i: (i.file, SEVERITY_ORDER.get(i.severity, 3)))

    current_file = None
    for issue in all_issues:
        if issue.file != current_file:
            current_file = issue.file
            print(f"\n📄 {current_file}")
            print("-" * 60)
        line_str = f"L{issue.line}" if issue.line else "L?"
        icon = SEVERITY_ICON.get(issue.severity, "⚪")
        print(f"  {icon} [{issue.severity.upper():10}] {line_str:6} ({issue.category}) — {issue.summary}")
        print(f"        {issue.explanation}")

    critical = sum(1 for i in all_issues if i.severity == "critical")
    warning = sum(1 for i in all_issues if i.severity == "warning")
    suggestion = sum(1 for i in all_issues if i.severity == "suggestion")

    print("\n" + "-" * 60)
    print(f"  Summary: {critical} critical, {warning} warning, {suggestion} suggestion(s)")

    if errors:
        print(f"\n⚠️  {len(errors)} chunk(s) failed to review:")
        for e in errors:
            print(f"   - {e.file} (chunk {e.chunk_index + 1}): {e.error}")
    print()


def export_json(results: List[ChunkResult], path: str):
    all_issues = [i for r in results for i in r.issues]
    data = {
        "issues": [issue.__dict__ for issue in all_issues],
        "errors": [{"file": r.file, "chunk": r.chunk_index, "error": r.error} for r in results if r.error],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"JSON report written to {path}")


def export_markdown(results: List[ChunkResult], path: str):
    all_issues = [i for r in results for i in r.issues]
    all_issues.sort(key=lambda i: (i.file, SEVERITY_ORDER.get(i.severity, 3)))

    lines = ["# AI Code Review Report\n"]
    if not all_issues:
        lines.append("No issues found. ✅\n")
    else:
        current_file = None
        for issue in all_issues:
            if issue.file != current_file:
                current_file = issue.file
                lines.append(f"\n## {current_file}\n")
            icon = SEVERITY_ICON.get(issue.severity, "⚪")
            line_str = f"Line {issue.line}" if issue.line else "Line unknown"
            lines.append(f"- {icon} **[{issue.severity.upper()}]** ({issue.category}, {line_str}): {issue.summary}")
            lines.append(f"  - {issue.explanation}")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Markdown report written to {path}")


def main():
    parser = argparse.ArgumentParser(description="AI-powered automated code reviewer using Claude.")
    parser.add_argument("target", help="Path to a file or directory to review")
    parser.add_argument("--output", help="Write a Markdown report to this path")
    parser.add_argument("--json", help="Write a JSON report to this path")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS_PER_CHUNK,
                         help="Max characters per chunk sent to the API")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: set the ANTHROPIC_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    target = Path(args.target)
    if not target.exists():
        print(f"Error: path '{target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    files = discover_files(target)
    if not files:
        print("No supported source files found.")
        sys.exit(0)

    client = anthropic.Anthropic(api_key=api_key)
    results: List[ChunkResult] = []

    print(f"Reviewing {len(files)} file(s)...")
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            results.append(ChunkResult(file=str(f), chunk_index=0, error=f"Could not read file: {e}"))
            continue

        if not text.strip():
            continue

        chunks = chunk_source(text, max_chars=args.max_chars)
        for idx, chunk in enumerate(chunks):
            print(f"  -> {f} (chunk {idx + 1}/{len(chunks)})")
            results.append(review_chunk(client, str(f), chunk, idx))

    print_terminal_report(results)

    if args.output:
        export_markdown(results, args.output)
    if args.json:
        export_json(results, args.json)


if __name__ == "__main__":
    main()


# AI Code Reviewer

A CLI tool that uses Claude (Anthropic API) to automatically review source code for
bugs, security vulnerabilities, style issues, and performance problems — and outputs
a structured, severity-ranked report in the terminal, Markdown, or JSON.

## Features

- **Recursive project scanning** — point it at a single file or an entire directory;
  it walks the tree, skipping `node_modules`, `.git`, `venv`, `dist`, `build`, etc.
- **Smart chunking** — large files are split into manageable chunks by size so
  reviews stay within a reasonable token budget per API call, instead of failing
  or silently truncating on big files.
- **Structured output** — the model is prompted to return strict JSON
  (`severity`, `category`, `line`, `summary`, `explanation`) rather than free-text,
  so results can be sorted, filtered, and exported reliably.
- **Multiple report formats** — terminal output with color-coded severity icons,
  plus optional `--output report.md` and `--json report.json` exports.
- **Resilience** — retries with exponential backoff on rate limits / transient API
  errors; malformed JSON responses are caught and reported per-chunk instead of
  crashing the whole run.

## Why this isn't just "call an API and print the response"

- Code is chunked using a size-aware heuristic rather than sent as one blob, so it
  scales to real files without blowing past context limits.
- The system prompt enforces a strict output schema, and the client-side code
  defensively parses/validates that JSON (including stripping stray markdown
  fences the model sometimes adds), rather than trusting raw text.
- Errors are isolated per file/chunk — one bad chunk doesn't kill the whole scan.
- Reports are aggregated and sorted by severity across the entire codebase, not
  just dumped in file order.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here
```

## Usage

```bash
# Review a single file
python reviewer.py path/to/file.py

# Review an entire project directory
python reviewer.py path/to/project/

# Export a Markdown report
python reviewer.py path/to/project/ --output report.md

# Export a JSON report (e.g. to feed into another tool or CI step)
python reviewer.py path/to/project/ --json report.json

# Try it on the included buggy sample
python reviewer.py sample_code/buggy_example.py
```

## Example output

```
📄 sample_code/buggy_example.py
------------------------------------------------------------
  🔴 [CRITICAL  ] L3     (security) — Hardcoded API key
        Secrets should never be hardcoded; use environment variables.
  🔴 [CRITICAL  ] L12    (security) — SQL injection vulnerability
        String concatenation into SQL allows injection; use parameterized queries.
  🟡 [WARNING   ] L6     (bug) — No zero-division check
        Dividing by zero will raise an exception; validate b before dividing.

Summary: 2 critical, 1 warning, 0 suggestion(s)
```

## Supported languages

`.py .js .ts .jsx .tsx .java .go .rb .c .cpp` (extend `SUPPORTED_EXTENSIONS` in
`reviewer.py` to add more).

## Known limitations

- LLM-based review can miss issues a compiler/linter would catch, and can
  occasionally flag false positives — it's a complement to tools like ESLint/
  Pylint/SonarQube, not a replacement for them.
- Line numbers are best-effort since chunk boundaries can shift context.
- No AST-based parsing — chunking is size-based, not semantically aware of
  function/class boundaries (a possible future improvement).

## Possible extensions

- GitHub Action wrapper to auto-review PRs on push
- AST-aware chunking (split by function/class instead of raw size)
- Diff-only mode (review just the changed lines in a PR)
- Local caching to avoid re-reviewing unchanged files

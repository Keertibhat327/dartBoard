# Data handling

- Keep paper PDFs, syllabuses, notes, extracted real question text, and any private
  data under `data/`. This directory is ignored in its entirety.
- Generated synthetic corpora and manifests also go under `data/`, visibly marked
  synthetic. Avoid copying text-bearing outputs into source, tests, or documentation.
- `models/`, `artifacts/`, `.env`, `.venv/`, Python caches, test/lint caches, build
  output, and `node_modules/` are also ignored. Existing ignore lines were retained.
- Tests use invented text and temporary synthetic files; they do not need real papers.
- M0 makes no API calls, uploads, account records, telemetry, or analytics events.
- No git commands are executed. The user controls version control later. Ignore
  rules cannot prevent an explicit forced add or remove already tracked files.
- There is no public-safe exporter in M0. Do not publish full fixture/data files
  as a substitute for the planned subject/year/marks/topic-ID-only export.

The generator checks output paths after resolving them and refuses output outside
the project's `data/` directory. It rejects existing output files instead of
overwriting them. It is an ordinary local CLI, not a security boundary against an
adversary concurrently modifying filesystem links.

## Current account and data workflow

The local app now has separate user and developer sign-in pages, VTU and BMSIT
collections, source-PDF history, paper reading, and frozen predictions scored on
later imports. See [docs/DATA_WORKFLOW.md](docs/DATA_WORKFLOW.md). This prospective
baseline does not complete the M2 rolling-origin backtest milestone.

# dartboard — VTU and BMSIT exam preparation workspace

A dart in the dark, but it keeps the score.

## Current app: login, profile, and developer studio

The latest request expands the UI into a local BMSIT workspace. Sign up with
email/password, click the top-right avatar to open your profile, and use its links
to access your dashboards. Internal assessments and semester-end collections are
tracked separately. No actual BMSIT paper pattern has been assumed.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,app]"
.\.venv\Scripts\python.exe -m api.server
```

Open `http://127.0.0.1:8001`. After registering your account, grant yourself developer
access locally with `.\.venv\Scripts\python.exe -m scripts.grant_developer --email "your-email@example.com"`.
Developer studio then appears in your profile. It accepts labeled Seer JSON datasets
and records their revision history; it does not extract PDFs or run backtests.

Success metrics show **Not evaluated** until the evaluation pipeline is implemented.
Email verification and password recovery are not connected. This server is for local
use, not deployment. See [account setup and limitations](docs/ACCOUNTS.md).

## M0 research scaffold

M0 implements the data contracts and reproducible synthetic fixture generator for
CPU-only exam preparation research. The core uses Python's standard library, works
without API keys, and requires no GPU. No forecasting or evaluation is implemented
yet. M2 starts only after explicit approval; M1 and other milestones are out of scope.

## Python setup (Windows PowerShell)

Use Python 3.11 or newer, from this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The generator itself needs no installation when run from the project root. Tool
versions for development are pinned in `pyproject.toml`. The GitHub Actions file is
provided for future use and has not been run. No git commands are part of this setup.

## Generate synthetic fixtures

```powershell
python -m scripts.generate_synthetic --config configs/synthetic.json --scenario strong_repeat
python -m scripts.generate_synthetic --config configs/synthetic.json --scenario weak_repeat
python -m scripts.generate_synthetic --config configs/synthetic.json --scenario pure_noise
```

Outputs go to `data/synthetic/<scenario>.json` and a matching `.manifest.json`.
Existing outputs are never overwritten. To compare a new configuration, supply
`--output data/synthetic/my_new_run.json`. Every generated record has
`is_synthetic: true`; question text and topic names also have a `[SYNTHETIC]` marker.
The manifest prints only computed counts and provenance, not evaluation metrics.

Edit `configs/synthetic.json` to choose the seed, years, subjects, scheme, sittings,
topic pool size, preferred pool size, and scenario strength. The year list must
span at least six distinct years. `configs/paper_structure.synthetic.json` controls
modules, question numbering, sub-parts, and marks. Its settings are arbitrary toy
inputs marked **UNVERIFIED**, not claims about VTU.

Scenario behavior:

- `strong_repeat`: strongly favors a fixed, randomly selected pool of topics.
- `weak_repeat`: mixes preferred-topic selection with uniform selection.
- `pure_noise`: uniform topic sampling within each module, without year memory or
  a planted preference. Incidental repeats can occur naturally.

`preferred_probability` is a generation control, not a measured probability that
a topic will appear in a real exam. A uniform fallback can also select a preferred
topic. No M2 significance or accuracy claims have been made.

If Windows restricts the default temporary directory, use a fresh test directory
inside ignored `data/` (pytest owns and clears the selected `--basetemp`):

```powershell
New-Item -ItemType Directory -Force data/.pytest-tmp | Out-Null
python -m pytest --basetemp=data/.pytest-tmp/local-check
```

## Project guide

- `labeling/schema.py`: subjects, schemes, papers, questions, topics, and labels;
  runtime validation and JSON round trips.
- `forecast/config.py`: strict configuration loading and reproducible hashes.
- `forecast/synthetic.py`: toy corpus generation, private output paths, and manifests.
- `scripts/generate_synthetic.py`: command-line entry point.
- `topicmap/`, `retrieval/`, `planner/`: documented package placeholders only.
- `api/`: local accounts and dataset revision tracking added after M0.
- `tests/`: schema, config, generator, storage, and CLI checks.
- `LEARNING.md`: module explanations and exercises.
- `docs/SCHEMA.md`, `docs/DECISIONS.md`, `docs/ASSUMPTIONS.md`,
  `docs/DATA_POLICY.md`: contracts, rationale, unverified assumptions, and data handling.

All paper PDFs, syllabus files, notes, and real question text must stay under
ignored `data/`. Do not put them in source, configs, docs, or tests. Ignore rules
are a safeguard, not protection against manually forcing a file into version control.

## Original UI prototype history

A responsive frontend based on the four supplied design references. The `web/`
folder was left untouched during M0. The subsequent explicit login/profile request
authorized UI edits. The current entry point is `workspace.js`, using the local API.
The original unloaded `app.js` remains as a historical visual prototype; its
manually supplied demo values are not pipeline results.

## Run

Use the account server shown above. Static file serving alone no longer supports
the login-enabled interface.

## Included

- Overview with lavender/orange accents and synthetic topic recurrence.
- White light mode and dark brown dark mode, persisted in browser storage.
- Subject library with paper filtering and subject switching.
- Document-style analysis with year selection and an evidence sidebar.
- Study planner with adjustable days/hours and CSV export.
- Local checklist persistence and mobile layouts.

## Data and limitations

All papers, question prompts, topic counts, and rankings are synthetic, manually supplied demonstrations. Document previews are illustrative and do not generate the recurrence counts. No real VTU pattern, marks, scheme, prediction accuracy, or forecast is asserted. No documents are uploaded, no accounts are created, and no paid service is used. Google Fonts is optional; system sans-serif fallbacks work offline. The planner rotates demo topics and allocates 75% of time to practice and 25% to recap; it does not optimize expected marks.

The workspace is local only. No site was published. Local SQLite accounts and
inventory APIs now exist; ingestion, OCR, trained models, retrieval, real BMSIT
data, and measured backtests remain separate future work.

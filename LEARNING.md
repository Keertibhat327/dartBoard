# Learning Seer, starting with M0

## Added later: the BMSIT account workspace

The user authorized UI edits after M0. `web/workspace.js` is now the active entry
point; `web/app.js` is retained but not loaded. M0's forecast experiments have not
advanced to M2. The local app is separate from the future hosted architecture.

`api/accounts.py` stores salted password hashes, not passwords. Session tokens
are random values in HttpOnly cookies; only their hashes are saved. Roles are read
from the database on every request so hiding a button cannot grant access.

Exercises: trace signup's default role; explain why password changes delete all
sessions; compare password hashing with hashing a random session token.

`api/server.py` joins static pages to protected API endpoints. Mutation requests
check their origin, authentication attempts are limited, and bodies have size
limits. The browser receives whitelisted profile fields, not database rows.

Exercises: request the developer endpoint as a regular user; inspect a cookie's
HttpOnly flag; explain why loopback HTTP settings must change for a hosted app.

`api/tracking.py` validates uploaded Seer JSON using the M0 schema and computes
inventory snapshots. BMSIT internals and semester-end collections have separate
keys. Missing metrics stay null; recording more papers is not itself evaluation.

Exercises: import a dataset twice; add one synthetic paper and compare revisions;
explain why a topic's historical frequency is not a forecast success rate.

`scripts/grant_developer.py` is a local operator command. `workspace.js` fetches
session state and renders login, profile, student views, and developer studio.

Exercises: follow the avatar link to profile; explain why client state cannot
change a server role; locate how the UI distinguishes synthetic collections.

The implemented path is: read configuration, validate it, generate synthetic
records, validate their relationships, then save private JSON and a manifest.
The browser prototype is independent and read-only. Forecasting begins only in M2.

## labeling/schema.py — records and relationships

A dataclass defines the fields of a record. Frozen records prevent ordinary
attribute reassignment. Each record validates its basic fields; the dataset checks
relationships across records. A foreign key is just an ID that must point to an
existing record. A scheme year and a paper year describe different things.

Why it matters: a topic attached to the wrong subject can corrupt an experiment
without causing a numerical calculation to crash. Rejecting it early is clearer.
`ValueError` checks still run with Python optimization; `assert` is reserved for tests.

Exercises:

1. Use `dataclasses.replace` in a scratch test to give a label an unknown topic ID.
   Explain the error.
2. Add a second sitting for an existing calendar year. Explain why it needs another ID.
3. Add a second valid topic label to one question. Explain why a future marks metric
   must count the question's marks only once.

## forecast/config.py — settings and hashes

JSON holds experimental choices outside code. Strict loading rejects duplicate
keys, missing controls, and values that would make generation invalid. A SHA-256
hash is a fingerprint of bytes. Canonical JSON formatting makes that fingerprint
independent of JSON indentation or object-key order in the input files.

The configuration hash includes both files, so changing marks changes provenance
even if the main generator settings stay the same. Frozen dataclasses do not freeze
nested dictionaries; generation revalidates them to catch changes after loading.

Exercises:

1. Copy the config, change its seed, and compare configuration hashes.
2. Change only whitespace and object-key order. Explain why the hash stays the same.
3. Set the noise preference above zero. Read the validation error and explain why
   the program rejects it.

## forecast/synthetic.py — controlled data and private storage

The generator uses its own seeded pseudorandom sequence. A preferred topic pool
creates deliberate repetition. A topic is removed from the current paper's pool
after being selected, which is sampling without replacement. Pure noise uses
uniform choices within each module. It can repeat topics by chance.

Generated counts are derived from records. The data hash is derived from bytes.
Neither is a forecast accuracy measurement. `data_path` resolves paths before
checking their location; this catches ordinary `..` escapes and external symlinks.

Exercises:

1. Generate the same scenario twice to different fresh output paths. Compare the
   data hashes and explain why the filenames do not affect dataset bytes.
2. Change the weak-repeat preference and inspect which labels change. Do not claim
   statistical significance from this inspection.
3. Attempt `--output outside.json` and explain why it is rejected before writing.

## scripts/generate_synthetic.py — a command-line boundary

`argparse` converts terminal arguments into typed paths and a known scenario name.
The entry point connects loading, generation, and writing. Input errors exit with
an explanatory message. Running a module with `python -m` works from the project
root on Windows without setting `PYTHONPATH` or editing shell profiles.

Exercises:

1. Run the command with `--help` and locate the required arguments.
2. Request a missing configuration file and read the failure message.
3. Try an existing output path and verify that the existing bytes remain unchanged.

## tests/ — evidence for software behavior

`conftest.py` supplies reusable in-memory configuration and dataset fixtures.
Schema tests exercise invalid data and valid edge cases. Config tests check bad
inputs and hashing. Generator tests check reproducibility, scenario construction,
private paths, serialization, manifests, and CLI behavior.

Tests do not demonstrate forecast accuracy. In particular, checking that a planted
pool exists is different from showing a predictor can recover it using past years.

Exercises:

1. Run one test with `python -m pytest -k duplicate_labels`.
2. Add a case for a blank topic name and confirm validation rejects it.
3. Explain why an unknown reference test is useful even though all generated data
   currently comes from our own program.

## The prospective upload workflow

Read `forecast/prospective.py` first: it filters by year before counting topic
appearances. `freeze_ranking` returns the selected topics plus reproducibility
evidence. `score_paper` uses sets so multi-topic questions cannot double marks.
Try removing a target label: scoring abstains instead of treating missing data as
a wrong prediction. The leakage tests remove all target/future papers and require
exactly the same ranking and training hash.

Next read `api/evidence.py` and `api/tracking.py`. An upload is an event; a snapshot
is a distinct dataset revision. Predictions are saved before target arrival,
then evaluated inside the import transaction. This order prevents a new paper
from influencing the prediction used to judge it. An import can create no score,
one score, or several scores depending on which frozen targets arrive.

Finally read `web/studio.js`: the browser formats server-produced metrics but
does not invent scores. The progress bars display individual measured results.
Changing performance across different papers is not statistical evidence that
the forecasting method improved. The broader M2 harness is still future work.

Accounts use stored roles, rather than the selected login tab, for authorization.
Inspect `tests/test_accounts.py` to see ordinary users rejected by developer APIs
while still reading VTU and BMSIT papers. No real account is used by those tests.

## Reserved packages

The following packages contain only explanatory docstrings. Their exercises are
reading/design prompts, not instructions to implement later milestones now.

| Package | Intended purpose | Exercises for later study |
| --- | --- | --- |
| topicmap | Map question text to topics. | Explain a human label; explain abstention; identify why evaluation should group by year. |
| retrieval | Find passages with citations. | Define a passage; describe a source/page citation; distinguish retrieved text from a generated answer. |
| planner | Allocate study time. | List required user inputs; describe an hours budget; explain why unmeasured forecast confidence should not look precise. |

## Project tooling

`pyproject.toml` declares the Python version, package discovery, and pytest/Ruff
settings. Ruff checks and formats code; it is not a type checker. The workflow file
records how future GitHub Actions runs should check Windows compatibility. Adding
the file does not mean CI has run. `.gitignore` records data exclusions without
executing version-control operations.

Exercises:

1. Locate the development-tool versions in `pyproject.toml`.
2. Explain why `dependencies` is empty while the `dev` extra contains tools.
3. Explain why an ignore rule is not sufficient protection if someone deliberately
   forces a private file into version control.

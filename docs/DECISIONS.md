# Decisions

## Later request: BMSIT accounts and developer studio

The user subsequently requested login, profile, a developer dashboard, and a
BMSIT-specific scope. This explicitly authorizes editing `web/` and adding a local
account API. The no-git rule continues. M0's research core remains unchanged and
M2 is not started. Scope entries below describe decisions at the M0 milestone.

Use the Sites skill's local implementation/preview path, retaining the established
theme and avoiding publication. FastAPI is an optional app dependency; the research
core still has no runtime dependencies. A pinned compatible Starlette/HTTPX pair
supports tests under the current Python runtime.

New users cannot choose their role. Developer grants use a local operator command,
and every private endpoint checks the stored role. SQLite accounts are a local
implementation, not the eventual stateless hosted architecture. Success metrics
stay null until a real evaluation pipeline exists. Internal and semester-end
datasets use distinct history keys. See ACCOUNTS.md for details and limitations.

## Scope and user-owned boundaries

Implement M0 only. Reserve packages for later components without implementing their
features. The existing `web/` prototype remains read-only. No git commands are run.
The next permitted milestone is M2 after the user says go; M1 and M3 are not started.

## Prospective evaluation and dual institution workspace

The later user request authorizes separate user/developer login pages, VTU/BMSIT
collections and evaluation of a saved prediction when its target paper arrives.
This is a narrow prospective workflow, not completion of the separate M2 milestone.
The global-frequency baseline uses strictly earlier years and observed topic IDs
only. Import and prediction writes serialize through SQLite transactions. Frozen
predictions and first measured outcomes cannot be replaced through the API.

All listed marks form the scoring denominator, with any-topic matching and no
double counting. Uploaders explicitly confirm target completeness. Optional exam
choices are not inferred. Configuration hashes include the scoring convention;
timeline deltas compare like configurations within one collection.

Uploads and dataset revisions are separate tables: repeated submissions remain
auditable even if their canonical JSON is unchanged. Source PDFs are optional,
stored under hashes in data/, and linked to paper IDs. They are not training text
until a reviewed labeled JSON represents them. User APIs now expose paper text and
attached PDF downloads to signed-in accounts, as explicitly requested.

New SQLite tables are additive, preserving existing accounts and snapshots.
Separate sign-in endpoints enforce the stored role; public signup cannot grant
developer access. Both institutions are available to every signed-in account.
See `docs/DATA_WORKFLOW.md` for the operator workflow and metric limitations.

## Standard library core

Use dataclasses, JSON, pathlib, hashlib, and a local `random.Random` instance.
These keep the CPU/Windows setup small and understandable. pytest and Ruff are
development tools only. No model downloads, network calls, paid APIs, database,
or environment secrets are needed by the core.

## Explicit records and validation

Keep the shared contract in `labeling/schema.py`, where question-to-topic links
can be checked against the rest of the corpus. Frozen records discourage accidental
changes. Unknown references, duplicate identities, invalid marks, inconsistent
origins, and labels crossing subjects/schemes/modules are errors. Python type hints
help readers, while runtime validation also checks untrusted JSON.

`Dataset` may contain unlabeled questions because future manual labeling will need
that state. The generator always labels every question. Multiple distinct topic
labels are supported; duplicate label pairs are rejected. M2 must choose and
document marks attribution without double-counting question marks.

## Configuration and experiment inputs

Use JSON to avoid a YAML dependency. Strict keys catch typos. The paper structure
is a separate file resolved relative to the generator config. It is explicitly
UNVERIFIED and synthetic. Future real paper rules require verification and may
require extending this toy structure (especially choice groups).

## Synthetic signal controls

For each subject/module, randomly select a stable preferred topic pool. For each
question slot, choose from remaining preferred topics with the configured
probability, otherwise from all remaining topics. Remove the chosen topic for the
rest of that paper/module. The preferred pool must cover the module's slots and
be smaller than its full topic pool. This keeps endpoint behavior easy to inspect.

Pure noise fixes preference to zero. This means no planted topic identity signal
conditional on module constraints, not that finite samples cannot contain repeats
or chance correlations. M0 does not run statistical tests or claim significance.

`planted_topic_ids` is privileged fixture metadata for checking construction.
Future predictors must not read it, future labels, or other generator internals.
It exists to test experiments, not as a predictive feature.

## Provenance and privacy

Canonical UTF-8 JSON uses sorted object keys and a final newline. The configuration
hash covers both the full generator config and the resolved structure. The data
hash covers exact saved dataset bytes. A manifest contains computed counts, seed,
scenario, generator version, and hashes; no hardcoded evaluation numbers.

Every generated record has `is_synthetic: true`, with textual markers on questions
and topics. Outputs are restricted to resolved paths within this project's `data/`
folder and refuse overwrites. Source and documentation contain no real questions.
M0 has no public export or deployment operation.

The dataset and manifest are written separately; the writer is not a transactional
database. A disk failure can leave a dataset without a manifest. Treat such a run
as incomplete and generate to a fresh path. No concurrent-write support is claimed.

## Reproducibility and checks

Use an isolated seeded random generator to avoid changing global random state.
Record the generator version and retain the fixture bytes. Pin the direct check
tools. The provided CI configuration targets Windows with the declared minimum
Python version and the locally available version; it has not been executed here.

## Website name

The user renamed the website to lowercase **dartboard**, with the exact tagline
"A dart in the dark, but it keeps the score." Visible branding and export filenames
use this name. Existing package names, folder paths, session cookies, request
headers and stored theme keys retain their identifiers for compatibility.

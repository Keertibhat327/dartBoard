# VTU and BMSIT: upload, predict, compare

Use `http://127.0.0.1:8001/#login` for user accounts and
`http://127.0.0.1:8001/#developer-login` for developer accounts.
These are separate role-checked sign-in routes. They share the existing account
store; existing accounts and passwords remain valid. Public signup creates only
user accounts. A local operator grants developer access to an existing account:

```powershell
.\.venv\Scripts\python.exe -m scripts.grant_developer --email "your-email@example.com"
```

Sign in through the developer page after promotion. Developers can also browse
the user dashboards. No default developer password exists.

## Feed historical data

1. Choose VTU or BMSIT in Developer studio, then the assessment type.
2. Select a complete Seer dataset JSON, following `docs/SCHEMA.md`. Preserve old
   records and IDs when appending papers. Keep the provenance scenario stable.
3. Optionally select source PDFs and enter the matching paper ID for each file.
   Each PDF must refer to a paper present in that dataset. PDFs are retained as
   evidence; their text is not automatically extracted or labeled.
4. Record the revision. Every successful submission appears in upload history,
   including repeated identical datasets. A duplicate does not create another
   collection revision or score. The normalized JSON and original PDF bytes can
   be downloaded. Canonical dataset and PDF hashes identify the saved content.

All source data stays beneath `data/`. Each uploaded dataset belongs to exactly
one institution and assessment type. Subject, scheme, real/synthetic status, and
scenario further separate collections. Do not mix institutions in one file.
Synthetic records are always visibly marked; never relabel fixture data as real.

## Freeze before the target arrives

1. Select the subject collection and enter the future paper's exact ID, exam year,
   and sitting. These must later match the uploaded paper record.
2. Choose top k no greater than the number of historically observed topics.
3. Freeze the prediction. The current baseline counts the number of historical
   papers containing each topic, with deterministic topic-ID tie breaking.
   Only papers from years **strictly before the target year** contribute.
4. Save a different target for each future paper you want to score. Predictions
   cannot be overwritten. A target already present in any earlier revision is
   rejected, even if someone later removes it from the current collection.

There is no assumed schedule or automatically guessed next sitting. Same-year
internals are excluded from training to preserve the earlier year-based leakage
rule. A collection containing only the target year cannot produce a prediction.
Historical topic IDs must remain stable for target labels to match them.

## Add the next actual paper

Add its questions and reviewed labels to the cumulative JSON, attach its PDF if
available, and upload into the same institution, assessment and collection.
Check the completeness confirmation only when all target questions, marks and
labels have been reviewed. The server then scores any exact matching pending
prediction. Missing labels, empty papers, unconfirmed completeness, or no prior
prediction produce no percentage. Confirmation can be supplied in a later upload.

Success rate is **marks coverage @ k**: marks of questions with any predicted-topic
match divided by all listed question marks. Each question contributes its marks
at most once. Precision is matched topics divided by k; recall is matched topics
divided by all target topics. New target topics count against recall even if they
were never seen during training.

This denominator is **not an inferred official exam maximum**. Optional questions
are all counted as listed; choice groups and compulsory-answer constraints are
not modeled. Marks coverage is topic coverage, not a student's expected grade or
the probability of predicting an exact question.

Each result stores its target data hash, training hash, source snapshot, config
hash, seed and upload event. Scores stay immutable after first evaluation; later
corrections are retained in upload history but do not silently rewrite a result.
For a data correction requiring reevaluation, a reviewed versioning workflow is
still needed. The current app has no delete/reset score control.

The timeline compares successive scored papers with the same configuration in
the same collection and shows changes in percentage points. This is descriptive,
not evidence of statistical significance or general improvement. The full M2
rolling-origin harness, baseline comparison and significance checks remain pending.

Users can switch between both institutions, open transcribed question papers,
and download attached PDFs. They cannot upload data, freeze predictions, access
developer history, or grant themselves developer access.

## API additions

- `POST /api/login/user` and `/api/login/developer`: email and password.
- `POST /api/developer/datasets`: dataset, institution, assessment_type, filename,
  sources (name, paper_id, content_base64), evaluation_ready (boolean).
- `POST /api/developer/predictions`: series, paper_id, year, sitting, k.
- `GET /api/developer`: subject revisions, upload events and saved predictions.
- `GET /api/papers/{series}/{paper_id}`: signed-in paper reader.

Legacy `/api/login` is the user portal. Old dataset requests without an institution
default to the configured BMSIT institution for compatibility. New UI submissions
always include institution explicitly. Size limits and forecast defaults live in
`configs/local_app.json`; no paid APIs or model downloads are used.

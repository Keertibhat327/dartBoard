# Dual workspace verification

## VERIFIED

- `python -m pytest -q --basetemp data/.pytest-tmp/dual-portals-final --tb=short`:
  **94 passed**. Executed outside the Windows sandbox because its default pytest
  temporary directory was inaccessible. All fixtures use isolated project data.
- `python -m ruff check .` and `python -m ruff format --check .`: passed.
- `node --check web/workspace.js` and `node --check web/studio.js`: passed.
- Automated checks cover role-specific login, developer authorization, institution
  isolation, signed-in paper access, PDF bytes and download authorization, duplicate
  upload history, invalid attachments, immutable predictions/results, completeness
  confirmation, strict historical cutoff, unseen topic exclusion, and marks arithmetic.
- Browser checked against an isolated synthetic database: developer login, saved
  prediction form, JSON file picker, target import, automatic scoring, success-rate
  timeline, separate VTU state, user login, paper text reader and institution switch.
- Reloading a bookmarked VTU subject retains the correct institution.
- Real accounts and collections were not used for test imports. Synthetic test
  content and screenshots remain beneath ignored data/. No git command was run.

## NOT VERIFIED

- Real VTU/BMSIT prediction performance or statistical significance.
- Official exam structures, optional-choice rules and maximum marks.
- Browser PDF picker/download interaction (the backend upload/download API was tested).
- Full M2 rolling-origin harness, baseline comparisons and CLI: not implemented here.
- PDF OCR, automatic topic labeling, email verification/recovery and production hosting.
- GitHub Actions workflow execution and mobile-device browser testing.

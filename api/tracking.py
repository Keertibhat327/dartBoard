"""Track actual dataset revisions without inventing evaluation results."""

import json
import time
from pathlib import Path
from typing import Any

from api.accounts import Accounts
from api.evidence import evaluate_pending, source_files
from forecast.config import canonical_bytes, sha256
from labeling.schema import Dataset


def record_dataset(
    accounts: Accounts,
    root: Path,
    payload: dict[str, Any],
    institution: str,
    assessment_type: str,
    filename: str = "dataset.json",
    sources: list[dict[str, Any]] | None = None,
    evaluation_ready: bool = False,
) -> int:
    """Store validated source privately and preserve each distinct subject snapshot.

    Scores can only come from a previously frozen prediction. Upload-provided
    metrics are never used; attached PDFs are evidence, not automatic OCR inputs.
    """
    dataset = Dataset.from_dict(payload)
    if not isinstance(filename, str) or not filename or len(filename) > 200:
        raise ValueError("Provide a dataset filename of at most 200 characters.")
    if type(evaluation_ready) is not bool:
        raise ValueError("Evaluation readiness must be confirmed as a boolean.")
    attachments = source_files(root, dataset, sources if sources is not None else [])
    content = canonical_bytes(dataset.to_dict())
    digest = sha256(content)
    source_dir = root / "data" / "imports"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{digest}.json"
    if not source_path.exists():
        with source_path.open("xb") as stream:
            stream.write(content)
    scenario = str(dataset.provenance.get("scenario", "unspecified"))
    labels = {label.question_id for label in dataset.labels}
    question_papers = {question.id: question.paper_id for question in dataset.questions}
    appearances: dict[str, set[str]] = {}
    for label in dataset.labels:
        appearances.setdefault(label.topic_id, set()).add(question_papers[label.question_id])
    inserted = 0
    with accounts.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        upload = db.execute(
            "INSERT INTO uploads (recorded_at,institution,assessment_type,data_hash,payload) "
            "VALUES (?,?,?,?,?)",
            (
                int(time.time()),
                institution,
                assessment_type,
                digest,
                json.dumps(
                    {
                        "filename": filename,
                        "bytes": len(content),
                        "sources": attachments,
                        "is_synthetic": dataset.is_synthetic,
                        "evaluation_ready": evaluation_ready,
                        "paper_ids": [p.id for p in dataset.papers],
                        "question_count": len(dataset.questions),
                    }
                ),
            ),
        )
        for subject in dataset.subjects:
            for scheme in dataset.schemes:
                papers = [
                    p
                    for p in dataset.papers
                    if p.subject_id == subject.id and p.scheme_id == scheme.id
                ]
                if not papers:
                    continue
                paper_ids = sorted(p.id for p in papers)
                questions = [q for q in dataset.questions if q.paper_id in paper_ids]
                topics = [
                    t
                    for t in dataset.topics
                    if t.subject_id == subject.id and t.scheme_id == scheme.id
                ]
                series = sha256(
                    canonical_bytes(
                        [
                            institution,
                            assessment_type,
                            subject.id,
                            scheme.id,
                            dataset.is_synthetic,
                            scenario,
                        ]
                    )
                )
                previous = db.execute(
                    "SELECT payload FROM snapshots WHERE series = ? ORDER BY id DESC LIMIT 1",
                    (series,),
                ).fetchone()
                old_ids = set(json.loads(previous[0])["paper_ids"]) if previous else set()
                evaluations = (
                    evaluate_pending(db, dataset, series, paper_ids, digest, upload.lastrowid)
                    if evaluation_ready
                    else []
                )
                snapshot = {
                    "institution": institution,
                    "assessment_type": assessment_type,
                    "subject_id": subject.id,
                    "name": subject.name,
                    "scheme": scheme.name,
                    "is_synthetic": dataset.is_synthetic,
                    "scenario": scenario,
                    "data_hash": digest,
                    "config_hash": dataset.provenance.get("config_hash"),
                    "seed": dataset.provenance.get("seed"),
                    "paper_ids": paper_ids,
                    "paper_count": len(papers),
                    "question_count": len(questions),
                    "labeled_count": sum(q.id in labels for q in questions),
                    "topic_count": len(topics),
                    "topics": [
                        {
                            "id": t.id,
                            "name": t.name,
                            "module": t.module,
                            "appearances": len(appearances.get(t.id, set())),
                        }
                        for t in topics
                    ],
                    "added_papers": len(set(paper_ids) - old_ids),
                    "removed_papers": len(old_ids - set(paper_ids)),
                    "papers": [{"id": p.id, "year": p.year, "sitting": p.sitting} for p in papers],
                    "metrics": evaluations[0]["metrics"] if len(evaluations) == 1 else None,
                    "evaluation_status": "Evaluated" if evaluations else "Not evaluated",
                    "evaluations": evaluations,
                    "upload_id": upload.lastrowid,
                    "filename": filename,
                    "sources": [item for item in attachments if item["paper_id"] in paper_ids],
                }
                cursor = db.execute(
                    """INSERT OR IGNORE INTO snapshots
                    (series, data_hash, recorded_at, payload) VALUES (?, ?, ?, ?)""",
                    (series, digest, int(time.time()), json.dumps(snapshot)),
                )
                inserted += cursor.rowcount
    return inserted


def subject_history(accounts: Accounts) -> list[dict[str, Any]]:
    """Read append-only inventory history; null metrics must stay visibly unavailable."""
    with accounts.connection() as db:
        rows = db.execute("SELECT * FROM snapshots ORDER BY id").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        snapshot = json.loads(row["payload"])
        item = {**snapshot, "snapshot_id": row["id"], "recorded_at": row["recorded_at"]}
        series = row["series"]
        if series not in result:
            result[series] = {"id": series, "history": []}
        result[series]["latest"] = item
        result[series]["history"].append(item)
    return list(result.values())

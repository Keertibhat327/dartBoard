"""Preserve private source evidence and prospective prediction history locally."""

import base64
import binascii
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from api.accounts import Accounts
from forecast.config import read_json, sha256
from forecast.prospective import freeze_ranking, score_paper
from labeling.schema import Dataset


def source_files(root: Path, dataset: Dataset, values: Any) -> list[dict[str, Any]]:
    """Validate all attachments before storing bytes under content hashes, never filenames."""
    if not isinstance(values, list):
        raise ValueError("Sources must be a list of PDF attachments.")
    prepared = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("Invalid PDF attachment.")
        name = item.get("name")
        paper_id = item.get("paper_id")
        if (
            not isinstance(name, str)
            or not name.lower().endswith(".pdf")
            or len(name) > 200
            or any(c in name for c in "/\\\r\n")
            or paper_id not in {p.id for p in dataset.papers}
        ):
            raise ValueError("Each PDF needs a filename and a paper ID in this dataset.")
        try:
            content = base64.b64decode(item.get("content_base64", ""), validate=True)
        except (ValueError, TypeError, binascii.Error) as exc:
            raise ValueError("Invalid PDF encoding.") from exc
        if not content.startswith(b"%PDF-"):
            raise ValueError("Source attachment must contain PDF bytes. OCR is not performed.")
        prepared.append(
            (
                content,
                {
                    "name": name,
                    "paper_id": paper_id,
                    "hash": sha256(content),
                    "bytes": len(content),
                    "is_synthetic": dataset.is_synthetic,
                },
            )
        )
    directory = root / "data" / "sources"
    directory.mkdir(parents=True, exist_ok=True)
    for content, metadata in prepared:
        path = directory / f"{metadata['hash']}.pdf"
        if not path.exists():
            path.write_bytes(content)
    return [metadata for _, metadata in prepared]


def upload_history(accounts: Accounts) -> list[dict[str, Any]]:
    """Keep duplicate submissions visible even when the dataset revision is unchanged."""
    with accounts.connection() as db:
        rows = db.execute("SELECT * FROM uploads ORDER BY id DESC").fetchall()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


def prediction_history(accounts: Accounts) -> list[dict[str, Any]]:
    """Return frozen ranks and outcomes without recomputing an older score on newer data."""
    with accounts.connection() as db:
        rows = db.execute("SELECT * FROM predictions ORDER BY id").fetchall()
    return [
        {
            **dict(row),
            "payload": json.loads(row["payload"]),
            "result": json.loads(row["result"]) if row["result"] else None,
        }
        for row in rows
    ]


def save_prediction(
    accounts: Accounts, root: Path, values: dict[str, Any], settings: dict[str, Any]
) -> int:
    """Serialize freezing with imports, so an already ingested target cannot be forecast."""
    target_id, sitting = values.get("paper_id"), values.get("sitting")
    year = values.get("year")
    if any(not isinstance(v, str) or not v.strip() for v in (target_id, sitting)):
        raise ValueError("Provide the exact future paper ID and sitting.")
    with accounts.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT * FROM snapshots WHERE series = ? ORDER BY id", (values.get("series"),)
        ).fetchall()
        if not rows:
            raise ValueError("Import a subject collection first.")
        snapshots = [json.loads(row["payload"]) for row in rows]
        for snapshot in snapshots:
            if any(
                p["id"] == target_id or (p["year"] == year and p["sitting"] == sitting)
                for p in snapshot["papers"]
            ):
                raise ValueError(
                    "This target was already imported; a prior prediction is required."
                )
        latest = snapshots[-1]
        dataset = Dataset.from_dict(
            read_json(root / "data" / "imports" / f"{latest['data_hash']}.json")
        )
        scheme = next(p.scheme_id for p in dataset.papers if p.id in latest["paper_ids"])
        frozen = freeze_ranking(
            dataset,
            latest["subject_id"],
            scheme,
            year,
            values.get("k", settings["top_k"]),
            settings["seed"],
        )
        frozen.update(
            {
                "source_snapshot": rows[-1]["id"],
                "source_hash": latest["data_hash"],
                "institution": latest["institution"],
                "assessment_type": latest["assessment_type"],
                "subject_name": latest["name"],
            }
        )
        try:
            cursor = db.execute(
                "INSERT INTO predictions (series,target_id,target_year,target_sitting,recorded_at,"
                "payload) VALUES (?,?,?,?,?,?)",
                (values["series"], target_id, year, sitting, int(time.time()), json.dumps(frozen)),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "A prediction for this target is already frozen and cannot be replaced."
            ) from exc
        return cursor.lastrowid


def evaluate_pending(
    db: sqlite3.Connection,
    dataset: Dataset,
    series: str,
    paper_ids: list[str],
    digest: str,
    upload_id: int,
) -> list[dict[str, Any]]:
    """Score only an exact target match against an earlier immutable ranking."""
    scored = []
    for row in db.execute(
        "SELECT * FROM predictions WHERE series = ? AND result IS NULL", (series,)
    ).fetchall():
        target = next(
            (p for p in dataset.papers if p.id == row["target_id"] and p.id in paper_ids), None
        )
        if target is None or (target.year, target.sitting) != (
            row["target_year"],
            row["target_sitting"],
        ):
            continue
        frozen = json.loads(row["payload"])
        metrics = score_paper(dataset, target.id, [t["id"] for t in frozen["topics"]])
        if metrics is None:
            continue
        result = {
            "metrics": metrics,
            "data_hash": digest,
            "upload_id": upload_id,
            "recorded_at": int(time.time()),
            "prediction_id": row["id"],
            "paper_id": target.id,
            "k": frozen["config"]["k"],
            "config_hash": frozen["config_hash"],
            "is_synthetic": dataset.is_synthetic,
        }
        db.execute(
            "UPDATE predictions SET result = ? WHERE id = ? AND result IS NULL",
            (json.dumps(result), row["id"]),
        )
        scored.append(result)
    return scored

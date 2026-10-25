"""Freeze a simple baseline before seeing its target; this is not the M2 backtest."""

from collections import defaultdict
from typing import Any

from forecast.config import canonical_bytes, sha256
from labeling.schema import Dataset


def freeze_ranking(
    dataset: Dataset, subject_id: str, scheme_id: str, target_year: int, k: int, seed: int
) -> dict[str, Any]:
    """Exclude the whole target year, including its topic labels, to prevent leakage.

    Only topics actually labeled in earlier papers are candidates. Deterministic
    ID tie breaking keeps the baseline auditable without a model or paid service.
    """
    if type(target_year) is not int or target_year < 1:
        raise ValueError("Target year must be a positive integer.")
    if type(k) is not int or k < 1:
        raise ValueError("Top k must be a positive integer.")
    papers = [
        p
        for p in dataset.papers
        if p.subject_id == subject_id and p.scheme_id == scheme_id and p.year < target_year
    ]
    paper_ids = {p.id for p in papers}
    questions = {q.id: q for q in dataset.questions if q.paper_id in paper_ids}
    labels = [label for label in dataset.labels if label.question_id in questions]
    if not papers or not questions or {label.question_id for label in labels} != set(questions):
        raise ValueError("Need fully labeled papers from years before the target year.")
    appearances: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        appearances[label.topic_id].add(questions[label.question_id].paper_id)
    if k > len(appearances):
        raise ValueError(f"Choose k no greater than the {len(appearances)} historical topics.")
    ranked = sorted(appearances, key=lambda topic: (-len(appearances[topic]), topic))[:k]
    names = {topic.id: topic.name for topic in dataset.topics if topic.id in appearances}
    raw = dataset.to_dict()
    training = {
        "papers": [p for p in raw["papers"] if p["id"] in paper_ids],
        "questions": [q for q in raw["questions"] if q["id"] in questions],
        "labels": [label for label in raw["labels"] if label["question_id"] in questions],
    }
    config = {
        "method": "global_frequency_v1",
        "k": k,
        "seed": seed,
        "cutoff": "year strictly before target",
        "tie_break": "topic_id",
        "marks_basis": "all_listed_marks_any_matching_topic_v1",
    }
    return {
        "topics": [{"id": topic, "name": names[topic]} for topic in ranked],
        "training_paper_ids": sorted(paper_ids),
        "training_max_year": max(p.year for p in papers),
        "training_hash": sha256(canonical_bytes(training)),
        "config": config,
        "config_hash": sha256(canonical_bytes(config)),
        "is_synthetic": dataset.is_synthetic,
    }


def score_paper(dataset: Dataset, paper_id: str, ranked: list[str]) -> dict[str, float] | None:
    """Count each question's marks once even if several predicted topics match it.

    The denominator is all listed question marks, not an assumed official exam
    maximum. Missing labels prevent a percentage instead of implying a failure.
    """
    questions = [q for q in dataset.questions if q.paper_id == paper_id]
    labels: dict[str, set[str]] = defaultdict(set)
    for label in dataset.labels:
        labels[label.question_id].add(label.topic_id)
    if not questions or not ranked or any(not labels[q.id] for q in questions):
        return None
    actual = set().union(*(labels[q.id] for q in questions))
    predicted = set(ranked)
    total = sum(q.marks for q in questions)
    covered = sum(q.marks for q in questions if labels[q.id] & predicted)
    return {
        "marks_coverage": covered / total,
        "precision": len(actual & predicted) / len(predicted),
        "recall": len(actual & predicted) / len(actual),
        "covered_marks": covered,
        "total_listed_marks": total,
    }

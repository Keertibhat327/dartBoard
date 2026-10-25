"""Synthetic tests guard the cutoff and marks arithmetic independently of the UI."""

from dataclasses import replace

import pytest

from forecast.prospective import freeze_ranking, score_paper
from labeling.schema import Dataset


def test_target_and_future_years_cannot_change_ranking(dataset: Dataset) -> None:
    subject, scheme = dataset.subjects[0].id, dataset.schemes[0].id
    year = sorted({p.year for p in dataset.papers})[3]
    before = freeze_ranking(dataset, subject, scheme, year, 1, 1729)
    historical_ids = {p.id for p in dataset.papers if p.year < year}
    question_ids = {q.id for q in dataset.questions if q.paper_id in historical_ids}
    historical = replace(
        dataset,
        papers=tuple(p for p in dataset.papers if p.id in historical_ids),
        questions=tuple(q for q in dataset.questions if q.id in question_ids),
        labels=tuple(label for label in dataset.labels if label.question_id in question_ids),
    )
    after = freeze_ranking(historical, subject, scheme, year, 1, 1729)
    assert before == after
    assert before["training_max_year"] < year
    assert set(before["training_paper_ids"]) <= historical_ids


def test_future_only_topic_cannot_be_selected(dataset: Dataset) -> None:
    first = min(p.year for p in dataset.papers)
    q = dataset.questions[0]
    label = next(label for label in dataset.labels if label.question_id == q.id)
    unique = replace(next(t for t in dataset.topics if t.id == label.topic_id), id="SYN-FUTURE")
    future = replace(dataset.papers[0], id="SYN-FUTURE-P", year=first + 2, sitting="SYN-FUTURE")
    question = replace(q, id="SYN-FUTURE-Q", paper_id=future.id)
    changed = replace(
        dataset,
        topics=dataset.topics + (unique,),
        papers=dataset.papers + (future,),
        questions=dataset.questions + (question,),
        labels=dataset.labels + (replace(label, question_id=question.id, topic_id=unique.id),),
    )
    result = freeze_ranking(changed, future.subject_id, future.scheme_id, first + 1, 1, 1729)
    assert all(t["id"] != unique.id for t in result["topics"])


def test_marks_and_multiple_labels_are_not_double_counted(dataset: Dataset) -> None:
    paper = dataset.papers[0]
    questions = [q for q in dataset.questions if q.paper_id == paper.id]
    label = next(label for label in dataset.labels if label.question_id == questions[0].id)
    topic = next(t for t in dataset.topics if t.id == label.topic_id)
    another = replace(topic, id="SYN-SECOND-LABEL")
    changed = replace(
        dataset,
        topics=dataset.topics + (another,),
        labels=dataset.labels + (replace(label, topic_id=another.id),),
    )
    predicted = [topic.id, another.id]
    matched = {label.question_id for label in changed.labels if label.topic_id in predicted}
    expected = sum(q.marks for q in questions if q.id in matched) / sum(q.marks for q in questions)
    actual = {
        label.topic_id for label in changed.labels if label.question_id in {q.id for q in questions}
    }
    result = score_paper(changed, paper.id, predicted)
    assert result["marks_coverage"] == pytest.approx(expected)
    assert result["precision"] == 1
    assert result["recall"] == pytest.approx(2 / len(actual))
    missing = replace(
        changed,
        labels=tuple(label for label in changed.labels if label.question_id != questions[0].id),
    )
    assert score_paper(missing, paper.id, predicted) is None
    assert score_paper(changed, paper.id, ["SYN-ABSENT"]) == {
        "marks_coverage": 0,
        "precision": 0,
        "recall": 0,
        "covered_marks": 0,
        "total_listed_marks": sum(q.marks for q in questions),
    }


def test_no_history_and_bad_k_are_rejected(dataset: Dataset) -> None:
    p = dataset.papers[0]
    for year, k in [(min(p.year for p in dataset.papers), 1), (2030, 0), (2030, 999), (True, 1)]:
        with pytest.raises(ValueError):
            freeze_ranking(dataset, p.subject_id, p.scheme_id, year, k, 1729)

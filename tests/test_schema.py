"""Bad joins and duplicate records must be rejected before experiments can use them."""

from dataclasses import replace

import pytest

from labeling.schema import Dataset, Label, Question, Scheme, Subject


def test_serialization_roundtrip(dataset: Dataset) -> None:
    assert Dataset.from_dict(dataset.to_dict()) == dataset


@pytest.mark.parametrize("marks", [0, -1, float("nan"), float("inf"), True, "5"])
def test_invalid_marks(dataset: Dataset, marks: object) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        replace(dataset.questions[0], marks=marks)


@pytest.mark.parametrize("year", [0, -1, True, "2024"])
def test_invalid_year(dataset: Dataset, year: object) -> None:
    with pytest.raises(ValueError, match="integer"):
        replace(dataset.papers[0], year=year)


def test_record_origin_is_explicit(dataset: Dataset) -> None:
    with pytest.raises(ValueError, match="boolean"):
        replace(dataset.subjects[0], is_synthetic="true")
    with pytest.raises(ValueError, match="marker"):
        replace(dataset.questions[0], text="Unmarked demonstration")
    with pytest.raises(ValueError, match="mixed"):
        replace(
            dataset,
            subjects=(replace(dataset.subjects[0], is_synthetic=False),) + dataset.subjects[1:],
        )


@pytest.mark.parametrize("collection", ["subjects", "schemes", "papers", "questions", "topics"])
def test_duplicate_ids(dataset: Dataset, collection: str) -> None:
    rows = getattr(dataset, collection)
    with pytest.raises(ValueError, match="duplicate .* id"):
        replace(dataset, **{collection: rows + (rows[0],)})


def test_duplicate_sitting_and_position(dataset: Dataset) -> None:
    paper = replace(dataset.papers[0], id="SYN-OTHER-PAPER")
    with pytest.raises(ValueError, match="duplicate paper sitting"):
        replace(dataset, papers=dataset.papers + (paper,))
    question = replace(dataset.questions[0], id="SYN-OTHER-QUESTION")
    with pytest.raises(ValueError, match="duplicate question position"):
        replace(dataset, questions=dataset.questions + (question,))


@pytest.mark.parametrize(
    ("collection", "field", "message"),
    [
        ("papers", "subject_id", "unknown subject"),
        ("papers", "scheme_id", "unknown scheme"),
        ("questions", "paper_id", "unknown paper"),
        ("topics", "subject_id", "unknown subject"),
        ("topics", "scheme_id", "unknown scheme"),
        ("labels", "question_id", "unknown question"),
        ("labels", "topic_id", "unknown topic"),
    ],
)
def test_unknown_references(dataset: Dataset, collection: str, field: str, message: str) -> None:
    rows = getattr(dataset, collection)
    with pytest.raises(ValueError, match=message):
        replace(dataset, **{collection: (replace(rows[0], **{field: "MISSING"}),) + rows[1:]})


@pytest.mark.parametrize("crossing", ["subject", "scheme", "module"])
def test_cross_boundary_labels(dataset: Dataset, crossing: str) -> None:
    original = dataset.topics[0]
    extra_schemes = dataset.schemes
    if crossing == "subject":
        topic = replace(original, subject_id=dataset.subjects[1].id)
    elif crossing == "scheme":
        other = Scheme(id="SYN-OTHER", name="Synthetic other scheme", year=2001, is_synthetic=True)
        extra_schemes += (other,)
        topic = replace(original, scheme_id=other.id)
    else:
        topic = replace(original, module="SYN-OTHER-MODULE")
    topic = replace(topic, id="SYN-CROSS-TOPIC")
    label = Label(question_id=dataset.questions[0].id, topic_id=topic.id, is_synthetic=True)
    with pytest.raises(ValueError, match=f"crosses {crossing}"):
        replace(
            dataset,
            schemes=extra_schemes,
            topics=dataset.topics + (topic,),
            labels=dataset.labels + (label,),
        )


def test_duplicate_labels_rejected_but_multiple_topics_allowed(dataset: Dataset) -> None:
    with pytest.raises(ValueError, match="duplicate label pair"):
        replace(dataset, labels=dataset.labels + (dataset.labels[0],))
    first = dataset.labels[0]
    question = dataset.questions[0]
    paper = dataset.papers[0]
    alternative = next(
        t
        for t in dataset.topics
        if t.id != first.topic_id
        and t.module == question.module
        and t.subject_id == paper.subject_id
    )
    additional = Label(question_id=question.id, topic_id=alternative.id, is_synthetic=True)
    updated = replace(dataset, labels=dataset.labels + (additional,))
    assert updated.labels[-1] == additional


def test_unlabeled_questions_allowed_for_future_manual_labeling(dataset: Dataset) -> None:
    assert replace(dataset, labels=()).labels == ()


def test_multiple_sittings_per_year_are_distinct(dataset: Dataset) -> None:
    paper = replace(dataset.papers[0], id="SYN-SECOND", sitting="SYNTHETIC-SECOND")
    updated = replace(dataset, papers=dataset.papers + (paper,))
    assert updated.papers[-1].year == updated.papers[0].year


def test_arbitrary_question_numbering_and_no_subpart(dataset: Dataset) -> None:
    question = replace(dataset.questions[0], number="Section-X.iii", sub_part=None)
    updated = replace(dataset, questions=(question,) + dataset.questions[1:])
    assert updated.questions[0].number == "Section-X.iii"


def test_strict_deserialization(dataset: Dataset) -> None:
    payload = dataset.to_dict()
    payload["invented"] = True
    with pytest.raises(ValueError, match="keys"):
        Dataset.from_dict(payload)
    payload = dataset.to_dict()
    payload["subjects"][0]["invented"] = True
    with pytest.raises(ValueError, match="fields"):
        Dataset.from_dict(payload)
    with pytest.raises(ValueError, match="schema_version"):
        replace(dataset, schema_version="unsupported")


def test_schema_does_not_assume_real_vtu_structure() -> None:
    subject = Subject(id="test", name="Test subject", is_synthetic=False)
    question = Question(
        id="q",
        paper_id="p",
        text="Test-only validation placeholder",
        marks=2.5,
        module="custom",
        number="A",
        sub_part=None,
        is_synthetic=False,
    )
    assert not subject.is_synthetic
    assert question.marks == 2.5

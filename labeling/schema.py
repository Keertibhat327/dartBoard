"""Explicit data contracts prevent invalid labels from becoming experiment inputs.

These types describe our storage, not any verified VTU examination structure.
Every record carries its origin so exported rows cannot silently lose that context.
"""

from dataclasses import asdict, dataclass, fields
from math import isfinite
from typing import Any, TypeVar

SCHEMA_VERSION = "1"


def require(condition: bool, message: str) -> None:
    """Use ValueError rather than assert so validation survives optimized Python."""
    if not condition:
        raise ValueError(message)


def nonempty(value: object, name: str) -> None:
    """Reject blank identifiers before joins can silently match the wrong records."""
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be nonempty text")


def integer(value: object, name: str, minimum: int = 0) -> None:
    """Booleans are integers in Python, but are never valid years or seeds here."""
    require(type(value) is int and value >= minimum, f"{name} must be an integer >= {minimum}")


def positive_number(value: object, name: str) -> None:
    """Reject NaN/infinity so later marks totals have a meaningful denominator."""
    require(
        type(value) in (int, float) and isfinite(value) and value > 0,
        f"{name} must be a finite positive number",
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Record:
    """Make data origin mandatory, including when individual records are exported."""

    is_synthetic: bool

    def __post_init__(self) -> None:
        require(type(self.is_synthetic) is bool, "is_synthetic must be a boolean")


@dataclass(frozen=True, slots=True)
class Subject(Record):
    id: str
    name: str

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        nonempty(self.id, "subject.id")
        nonempty(self.name, "subject.name")


@dataclass(frozen=True, slots=True)
class Scheme(Record):
    """Keep scheme year distinct from the calendar year of an exam sitting."""

    id: str
    name: str
    year: int

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        nonempty(self.id, "scheme.id")
        nonempty(self.name, "scheme.name")
        integer(self.year, "scheme.year", 1)


@dataclass(frozen=True, slots=True)
class Paper(Record):
    id: str
    subject_id: str
    scheme_id: str
    year: int
    sitting: str

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        for name in ("id", "subject_id", "scheme_id", "sitting"):
            nonempty(getattr(self, name), f"paper.{name}")
        integer(self.year, "paper.year", 1)


@dataclass(frozen=True, slots=True)
class Question(Record):
    id: str
    paper_id: str
    text: str
    marks: float
    module: str
    number: str
    sub_part: str | None

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        for name in ("id", "paper_id", "text", "module", "number"):
            nonempty(getattr(self, name), f"question.{name}")
        positive_number(self.marks, "question.marks")
        if self.sub_part is not None:
            nonempty(self.sub_part, "question.sub_part")
        if self.is_synthetic:
            require(self.text.startswith("[SYNTHETIC]"), "synthetic question text needs its marker")


@dataclass(frozen=True, slots=True)
class Topic(Record):
    id: str
    subject_id: str
    scheme_id: str
    name: str
    module: str

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        for name in ("id", "subject_id", "scheme_id", "name", "module"):
            nonempty(getattr(self, name), f"topic.{name}")


@dataclass(frozen=True, slots=True)
class Label(Record):
    """A question may have multiple distinct labels; marks are not duplicated here."""

    question_id: str
    topic_id: str

    def __post_init__(self) -> None:
        Record.__post_init__(self)
        nonempty(self.question_id, "label.question_id")
        nonempty(self.topic_id, "label.topic_id")


T = TypeVar("T", Subject, Scheme, Paper, Question, Topic)


@dataclass(frozen=True, slots=True)
class Dataset:
    """Validate cross-record references before downstream code can consume a corpus."""

    schema_version: str
    is_synthetic: bool
    provenance: dict[str, Any]
    subjects: tuple[Subject, ...]
    schemes: tuple[Scheme, ...]
    papers: tuple[Paper, ...]
    questions: tuple[Question, ...]
    topics: tuple[Topic, ...]
    labels: tuple[Label, ...]

    def __post_init__(self) -> None:
        require(self.schema_version == SCHEMA_VERSION, "unsupported schema_version")
        require(type(self.is_synthetic) is bool, "dataset.is_synthetic must be a boolean")
        require(isinstance(self.provenance, dict), "provenance must be an object")
        collections = (
            (self.subjects, Subject),
            (self.schemes, Scheme),
            (self.papers, Paper),
            (self.questions, Question),
            (self.topics, Topic),
            (self.labels, Label),
        )
        for records, record_type in collections:
            require(isinstance(records, tuple), "record collections must be tuples")
            for record in records:
                require(isinstance(record, record_type), f"expected {record_type.__name__}")
                require(
                    record.is_synthetic == self.is_synthetic, "mixed real and synthetic records"
                )
        subjects = self._index(self.subjects, "subject")
        schemes = self._index(self.schemes, "scheme")
        papers = self._index(self.papers, "paper")
        questions = self._index(self.questions, "question")
        topics = self._index(self.topics, "topic")
        sittings: set[tuple[str, str, int, str]] = set()
        for paper in self.papers:
            require(paper.subject_id in subjects, "paper references unknown subject")
            require(paper.scheme_id in schemes, "paper references unknown scheme")
            key = (paper.subject_id, paper.scheme_id, paper.year, paper.sitting)
            require(key not in sittings, "duplicate paper sitting")
            sittings.add(key)
        positions: set[tuple[str, str, str | None]] = set()
        for question in self.questions:
            require(question.paper_id in papers, "question references unknown paper")
            key = (question.paper_id, question.number, question.sub_part)
            require(key not in positions, "duplicate question position")
            positions.add(key)
        for topic in self.topics:
            require(topic.subject_id in subjects, "topic references unknown subject")
            require(topic.scheme_id in schemes, "topic references unknown scheme")
        pairs: set[tuple[str, str]] = set()
        for label in self.labels:
            require(label.question_id in questions, "label references unknown question")
            require(label.topic_id in topics, "label references unknown topic")
            question = questions[label.question_id]
            paper = papers[question.paper_id]
            topic = topics[label.topic_id]
            require(paper.subject_id == topic.subject_id, "label crosses subjects")
            require(paper.scheme_id == topic.scheme_id, "label crosses schemes")
            require(question.module == topic.module, "label crosses modules")
            pair = (label.question_id, label.topic_id)
            require(pair not in pairs, "duplicate label pair")
            pairs.add(pair)

    @staticmethod
    def _index(records: tuple[T, ...], name: str) -> dict[str, T]:
        """Reject duplicates instead of letting dictionary construction hide them."""
        result: dict[str, T] = {}
        for record in records:
            identifier = record.id
            require(identifier not in result, f"duplicate {name} id")
            result[identifier] = record
        return result

    def to_dict(self) -> dict[str, Any]:
        """Preserve record origin and provenance when serializing for offline use."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Dataset":
        """Revalidate JSON rather than trusting a file just because it parses."""
        require(isinstance(payload, dict), "dataset must be an object")
        require(set(payload) == {f.name for f in fields(cls)}, "unexpected or missing dataset keys")
        values = dict(payload)
        for name, record_type in (
            ("subjects", Subject),
            ("schemes", Scheme),
            ("papers", Paper),
            ("questions", Question),
            ("topics", Topic),
            ("labels", Label),
        ):
            require(isinstance(values[name], (list, tuple)), f"{name} must be an array")
            require(all(isinstance(row, dict) for row in values[name]), f"invalid {name} row")
            try:
                values[name] = tuple(record_type(**row) for row in values[name])
            except TypeError as exc:
                raise ValueError(f"unexpected or missing {name} fields") from exc
        return cls(**values)

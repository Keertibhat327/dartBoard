"""Generate labeled toy corpora with controllable signal and no external services."""

import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from forecast.config import SCENARIOS, SyntheticConfig, canonical_bytes, read_json, sha256
from labeling.schema import (
    SCHEMA_VERSION,
    Dataset,
    Label,
    Paper,
    Question,
    Scheme,
    Subject,
    Topic,
    require,
)

GENERATOR_VERSION = "m0-v1"


def generate(config: SyntheticConfig, scenario: str) -> Dataset:
    """Plant a stable preferred topic pool; noise draws uniformly without year memory.

    Sampling is without replacement within each paper/module. Fixed module slots
    are an experimental constraint shared by every scenario, not learned signal.
    """
    require(scenario in SCENARIOS, f"unknown scenario: {scenario}")
    # Dataclasses freeze attributes, not nested dictionaries: recheck their provenance.
    validated = SyntheticConfig.from_dict(config.raw, config.structure_raw)
    require(validated == config, "config changed after validation; reload it before generating")
    raw = config.raw
    rng = random.Random(raw["seed"])
    probability = raw["scenarios"][scenario]["preferred_probability"]
    subjects = tuple(Subject(**item, is_synthetic=True) for item in raw["subjects"])
    scheme = Scheme(**raw["scheme"], is_synthetic=True)
    topics: list[Topic] = []
    papers: list[Paper] = []
    questions: list[Question] = []
    labels: list[Label] = []
    preferred_ids: list[str] = []
    for subject_index, subject in enumerate(subjects):
        by_module: dict[str, list[Topic]] = {}
        preferred: dict[str, list[Topic]] = {}
        for module_index, module in enumerate(config.structure.modules):
            pool = [
                Topic(
                    id=f"SYN-S{subject_index}-M{module_index}-T{index}",
                    subject_id=subject.id,
                    scheme_id=scheme.id,
                    name=f"[SYNTHETIC] {subject.name} / {module} / Topic {index + 1}",
                    module=module,
                    is_synthetic=True,
                )
                for index in range(raw["topics_per_module"])
            ]
            by_module[module] = pool
            preferred[module] = rng.sample(pool, raw["preferred_topics_per_module"])
            if probability > 0:
                preferred_ids.extend(topic.id for topic in preferred[module])
            topics.extend(pool)
        for year in raw["years"]:
            for sitting_index, sitting in enumerate(raw["sittings"]):
                paper = Paper(
                    id=f"SYN-S{subject_index}-Y{year}-P{sitting_index}",
                    subject_id=subject.id,
                    scheme_id=scheme.id,
                    year=year,
                    sitting=sitting,
                    is_synthetic=True,
                )
                papers.append(paper)
                available = {module: list(pool) for module, pool in by_module.items()}
                for slot_index, slot in enumerate(config.structure.slots):
                    remaining = available[slot.module]
                    hot = [topic for topic in preferred[slot.module] if topic in remaining]
                    candidates = hot if hot and rng.random() < probability else remaining
                    topic = rng.choice(candidates)
                    remaining.remove(topic)
                    question = Question(
                        id=f"{paper.id}-Q{slot_index}",
                        paper_id=paper.id,
                        text=f"[SYNTHETIC] Demonstration prompt about {topic.name}.",
                        marks=slot.marks,
                        module=slot.module,
                        number=slot.number,
                        sub_part=slot.sub_part,
                        is_synthetic=True,
                    )
                    questions.append(question)
                    labels.append(
                        Label(question_id=question.id, topic_id=topic.id, is_synthetic=True)
                    )
    return Dataset(
        schema_version=SCHEMA_VERSION,
        is_synthetic=True,
        provenance={
            "is_synthetic": True,
            "generator_version": GENERATOR_VERSION,
            "scenario": scenario,
            "seed": raw["seed"],
            "config_hash": config.config_hash,
            "preferred_probability": probability,
            "planted_topic_ids": preferred_ids,
            "paper_structure_status": "UNVERIFIED",
            "effective_config": deepcopy(
                {"generator": raw, "paper_structure": config.structure_raw}
            ),
            "warning": "SYNTHETIC ONLY. No forecast performance has been evaluated.",
        },
        subjects=subjects,
        schemes=(scheme,),
        papers=tuple(papers),
        questions=tuple(questions),
        topics=tuple(topics),
        labels=tuple(labels),
    )


def data_path(path: Path, project_root: Path) -> Path:
    """Keep text-bearing datasets under data/, including through resolved symlinks."""
    root = project_root.resolve()
    data_root = root / "data"
    require(data_root.resolve() == data_root, "data/ must not redirect outside the project")
    resolved = (root / path).resolve()
    require(
        resolved.is_relative_to(data_root) and resolved != data_root,
        "dataset path must be a file under the project data/ directory",
    )
    require(resolved.suffix == ".json", "dataset path must end with .json")
    return resolved


def write_dataset(dataset: Dataset, output: Path, project_root: Path) -> dict[str, Any]:
    """Write private synthetic fixtures and byte-level provenance without overwriting files."""
    require(dataset.is_synthetic, "fixture writer only accepts synthetic data")
    output = data_path(output, project_root)
    manifest_path = output.with_suffix(".manifest.json")
    require(not output.exists() and not manifest_path.exists(), "output already exists")
    dataset_bytes = canonical_bytes(dataset.to_dict())
    manifest = {
        "is_synthetic": True,
        "dataset_file": output.name,
        "data_hash": sha256(dataset_bytes),
        "config_hash": dataset.provenance["config_hash"],
        "seed": dataset.provenance["seed"],
        "scenario": dataset.provenance["scenario"],
        "generator_version": GENERATOR_VERSION,
        "counts": {
            "subjects": len(dataset.subjects),
            "schemes": len(dataset.schemes),
            "papers": len(dataset.papers),
            "questions": len(dataset.questions),
            "topics": len(dataset.topics),
            "labels": len(dataset.labels),
            "years": len({paper.year for paper in dataset.papers}),
        },
        "warning": "SYNTHETIC ONLY. Counts are computed; no evaluation metrics exist at M0.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(dataset_bytes)
    with manifest_path.open("xb") as stream:
        stream.write(canonical_bytes(manifest))
    return manifest


def load_dataset(path: Path, project_root: Path) -> Dataset:
    """Apply the same location and schema checks when reading text-bearing fixtures."""
    return Dataset.from_dict(read_json(data_path(path, project_root)))

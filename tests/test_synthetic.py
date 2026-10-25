"""Verify fixture mechanics without claiming forecast accuracy or statistical significance."""

import json
import random
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import pytest

from forecast.config import SCENARIOS, SyntheticConfig, canonical_bytes, read_json, sha256
from forecast.synthetic import generate, load_dataset, write_dataset
from labeling.schema import Dataset
from scripts import generate_synthetic


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_reproducible_complete_fixtures(config: SyntheticConfig, scenario: str) -> None:
    first = generate(config, scenario)
    second = generate(config, scenario)
    assert canonical_bytes(first.to_dict()) == canonical_bytes(second.to_dict())
    assert first.is_synthetic
    assert first.provenance["is_synthetic"]
    assert len({p.year for p in first.papers}) >= 6
    assert len(first.papers) == len(config.raw["subjects"]) * len(config.raw["years"]) * len(
        config.raw["sittings"]
    )
    assert len(first.questions) == len(first.papers) * len(config.structure.slots)
    assert {label.question_id for label in first.labels} == {q.id for q in first.questions}
    assert len(first.labels) == len(first.questions)
    assert all(q.text.startswith("[SYNTHETIC]") for q in first.questions)
    assert all(t.name.startswith("[SYNTHETIC]") for t in first.topics)
    for name in ("subjects", "schemes", "papers", "questions", "topics", "labels"):
        assert all(record.is_synthetic for record in getattr(first, name))


def test_strong_scenario_plants_configured_topics(config: SyntheticConfig) -> None:
    dataset = generate(config, "strong_repeat")
    # This asserts the construction, not a model's ability to recover it (M2).
    planted = set(dataset.provenance["planted_topic_ids"])
    assert {label.topic_id for label in dataset.labels} == planted
    assert dataset.provenance["preferred_probability"] == 1.0


def test_weak_scenario_contains_preferred_and_other_topics(config: SyntheticConfig) -> None:
    dataset = generate(config, "weak_repeat")
    planted = set(dataset.provenance["planted_topic_ids"])
    used = {label.topic_id for label in dataset.labels}
    assert used & planted
    assert used - planted


def test_noise_has_no_planted_topics_or_year_memory(config: SyntheticConfig) -> None:
    dataset = generate(config, "pure_noise")
    assert dataset.provenance["planted_topic_ids"] == []
    assert dataset.provenance["preferred_probability"] == 0
    labels = {label.question_id: label.topic_id for label in dataset.labels}
    paper_topics: dict[str, set[str]] = defaultdict(set)
    for question in dataset.questions:
        paper_topics[question.paper_id].add(labels[question.id])
    assert len({tuple(sorted(topics)) for topics in paper_topics.values()}) > 1
    # Calendar labels do not influence the topic draws; only the seeded RNG does.
    changed = deepcopy(config.raw)
    changed["years"] = [year + 100 for year in changed["years"]]
    relabeled = SyntheticConfig.from_dict(changed, config.structure_raw)
    assert [label.topic_id for label in generate(relabeled, "pure_noise").labels] == [
        label.topic_id for label in dataset.labels
    ]


def test_generator_does_not_modify_global_random_state(config: SyntheticConfig) -> None:
    state = random.getstate()
    generate(config, "weak_repeat")
    assert random.getstate() == state


def test_config_edits_do_not_retroactively_change_dataset(config: SyntheticConfig) -> None:
    dataset = generate(config, "weak_repeat")
    before = canonical_bytes(dataset.to_dict())
    config.raw["seed"] += 1
    assert canonical_bytes(dataset.to_dict()) == before
    with pytest.raises(ValueError, match="config changed"):
        generate(config, "weak_repeat")


def test_unknown_scenario_is_rejected(config: SyntheticConfig) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        generate(config, "made_up_scenario")


def test_different_seeds_change_noise_draws(config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    raw["seed"] += 1
    other = SyntheticConfig.from_dict(raw, config.structure_raw)
    assert generate(config, "pure_noise").labels != generate(other, "pure_noise").labels


def test_configurable_sittings_slots_and_marks(tmp_path: Path, config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    raw["sittings"] = ["SYNTHETIC-FIRST", "SYNTHETIC-SECOND"]
    structure = deepcopy(config.structure_raw)
    structure["slots"][0].update(number="CUSTOM-X", sub_part=None, marks=2.5)
    path = tmp_path / "config.json"
    path.write_bytes(canonical_bytes(raw))
    (tmp_path / raw["paper_structure"]).write_bytes(canonical_bytes(structure))
    updated = SyntheticConfig.load(path)
    dataset = generate(updated, "strong_repeat")
    assert {paper.sitting for paper in dataset.papers} == set(raw["sittings"])
    assert dataset.questions[0].number == "CUSTOM-X"
    assert dataset.questions[0].sub_part is None
    assert dataset.questions[0].marks == 2.5


def test_file_roundtrip_and_computed_manifest(tmp_path: Path, dataset: Dataset) -> None:
    path = Path("data/synthetic/test.json")
    manifest = write_dataset(dataset, path, tmp_path)
    assert load_dataset(path, tmp_path) == dataset
    assert manifest["data_hash"] == sha256((tmp_path / path).read_bytes())
    assert manifest["config_hash"] == dataset.provenance["config_hash"]
    assert manifest["seed"] == dataset.provenance["seed"]
    assert manifest["is_synthetic"] is True
    assert manifest["counts"]["questions"] == len(dataset.questions)
    assert manifest["counts"]["years"] == len({p.year for p in dataset.papers})
    assert read_json((tmp_path / path).with_suffix(".manifest.json")) == manifest


@pytest.mark.parametrize("path", ["outside.json", "data/../outside.json", "data", "data/test.txt"])
def test_output_cannot_escape_data(tmp_path: Path, dataset: Dataset, path: str) -> None:
    with pytest.raises(ValueError, match="data/|.json"):
        write_dataset(dataset, Path(path), tmp_path)
    assert not (tmp_path / "outside.json").exists()


def test_writer_refuses_overwrite(tmp_path: Path, dataset: Dataset) -> None:
    path = Path("data/test.json")
    write_dataset(dataset, path, tmp_path)
    before = (tmp_path / path).read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        write_dataset(dataset, path, tmp_path)
    assert (tmp_path / path).read_bytes() == before


def test_cli_prints_only_computed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "synthetic.json"
    monkeypatch.setattr(generate_synthetic, "PROJECT_ROOT", tmp_path)
    assert generate_synthetic.main(["--config", str(config_path), "--scenario", "pure_noise"]) == 0
    printed = json.loads(capsys.readouterr().out)
    dataset_path = tmp_path / "data" / "synthetic" / "pure_noise.json"
    assert printed["data_hash"] == sha256(dataset_path.read_bytes())
    assert printed["is_synthetic"]


def test_cli_failure_is_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "synthetic.json"
    monkeypatch.setattr(generate_synthetic, "PROJECT_ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        generate_synthetic.main(
            ["--config", str(config_path), "--scenario", "pure_noise", "--output", "outside.json"]
        )
    assert exc.value.code == 2
    assert "under the project data/" in capsys.readouterr().err

"""Configuration errors should fail before data is generated or files are created."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from forecast.config import PaperStructure, SyntheticConfig, canonical_bytes, read_json


def write_config(tmp_path: Path, config: SyntheticConfig, raw: dict[str, Any]) -> Path:
    """Keep temporary config tests self-contained, including their relative structure file."""
    (tmp_path / "paper_structure.synthetic.json").write_bytes(canonical_bytes(config.structure_raw))
    path = tmp_path / "synthetic.json"
    path.write_bytes(canonical_bytes(raw))
    return path


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("seed", True, "seed"),
        ("seed", -1, "seed"),
        ("years", [2020], "six years"),
        ("years", [2020, 2021, 2022, 2023, 2024, 2024], "unique"),
        ("years", [2025, 2024, 2023, 2022, 2021, 2020], "increasing"),
        ("is_synthetic", False, "synthetic"),
        ("sittings", ["main", "main"], "duplicate"),
        ("preferred_topics_per_module", 1, "cover the slots"),
        ("topics_per_module", 2, "smaller"),
    ],
)
def test_invalid_controls(
    tmp_path: Path, config: SyntheticConfig, field: str, value: Any, message: str
) -> None:
    raw = deepcopy(config.raw)
    raw[field] = value
    with pytest.raises(ValueError, match=message):
        SyntheticConfig.load(write_config(tmp_path, config, raw))


def test_noise_cannot_be_given_a_signal(tmp_path: Path, config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    raw["scenarios"]["pure_noise"]["preferred_probability"] = 0.1
    with pytest.raises(ValueError, match="zero preference"):
        SyntheticConfig.load(write_config(tmp_path, config, raw))


def test_weak_strong_order_is_validated(tmp_path: Path, config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    raw["scenarios"]["weak_repeat"]["preferred_probability"] = 1.0
    with pytest.raises(ValueError, match="weak_repeat"):
        SyntheticConfig.load(write_config(tmp_path, config, raw))


def test_hash_covers_both_configs(tmp_path: Path, config: SyntheticConfig) -> None:
    path = write_config(tmp_path, config, deepcopy(config.raw))
    assert SyntheticConfig.load(path).config_hash == config.config_hash
    structure = deepcopy(config.structure_raw)
    structure["slots"][0]["marks"] += 1
    (tmp_path / "paper_structure.synthetic.json").write_bytes(canonical_bytes(structure))
    assert SyntheticConfig.load(path).config_hash != config.config_hash


def test_configuration_owns_its_input_copy(config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    loaded = SyntheticConfig.from_dict(raw, config.structure_raw)
    raw["seed"] += 1
    assert loaded.raw["seed"] == config.raw["seed"]


def test_unknown_control_is_rejected(config: SyntheticConfig) -> None:
    raw = deepcopy(config.raw)
    raw["random_seed"] = raw["seed"]
    with pytest.raises(ValueError, match="unexpected or missing"):
        SyntheticConfig.from_dict(raw, config.structure_raw)


@pytest.mark.parametrize("invalid", ["duplicate", "module", "marks", "status"])
def test_invalid_structure(config: SyntheticConfig, invalid: str) -> None:
    raw = deepcopy(config.structure_raw)
    if invalid == "duplicate":
        raw["slots"].append(raw["slots"][0])
    elif invalid == "module":
        raw["slots"][0]["module"] = "UNKNOWN"
    elif invalid == "marks":
        raw["slots"][0]["marks"] = float("nan")
    else:
        raw["status"] = "VERIFIED"
    with pytest.raises(ValueError):
        PaperStructure.from_dict(raw)


@pytest.mark.parametrize("source", ['{"seed": 1, "seed": 2}', '{"seed": NaN}', "[]"])
def test_strict_json(tmp_path: Path, source: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError):
        read_json(path)

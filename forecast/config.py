"""Strict, dependency-free configuration keeps toy assumptions visible and editable."""

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labeling.schema import integer, nonempty, positive_number, require

SCENARIOS = ("strong_repeat", "weak_repeat", "pure_noise")


def read_json(path: Path) -> dict[str, Any]:
    """Reject duplicate keys and non-finite constants instead of quietly changing inputs."""

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    result = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_keys,
        parse_constant=invalid_constant,
    )
    require(isinstance(result, dict), "JSON root must be an object")
    return result


def canonical_bytes(value: object) -> bytes:
    """Stable JSON makes hashes reproducible without timestamps or machine-specific paths."""
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    """Hash exact bytes so a later experiment can identify its precise input."""
    return hashlib.sha256(data).hexdigest()


def keys(value: object, expected: set[str], name: str) -> None:
    """Catch misspelled controls rather than falling back to unintended defaults."""
    require(isinstance(value, dict), f"{name} must be an object")
    require(set(value) == expected, f"{name} has unexpected or missing keys")


def unique_texts(value: object, name: str) -> None:
    """Distinct text identifiers avoid collisions in generated records."""
    require(isinstance(value, list) and bool(value), f"{name} must be a nonempty array")
    for item in value:
        nonempty(item, name)
    require(len(set(value)) == len(value), f"duplicate {name}")


@dataclass(frozen=True, slots=True)
class QuestionSlot:
    number: str
    sub_part: str | None
    module: str
    marks: float


@dataclass(frozen=True, slots=True)
class PaperStructure:
    """Slots describe toy question positions without assuming a real exam format."""

    modules: tuple[str, ...]
    slots: tuple[QuestionSlot, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PaperStructure":
        keys(raw, {"status", "is_synthetic", "description", "modules", "slots"}, "paper structure")
        require(raw["status"] == "UNVERIFIED", "paper structure must be marked UNVERIFIED")
        require(raw["is_synthetic"] is True, "M0 paper structure must be synthetic")
        nonempty(raw["description"], "paper structure description")
        unique_texts(raw["modules"], "modules")
        require(isinstance(raw["slots"], list) and bool(raw["slots"]), "slots must be nonempty")
        slots: list[QuestionSlot] = []
        positions: set[tuple[str, str | None]] = set()
        for item in raw["slots"]:
            keys(item, {"number", "sub_part", "module", "marks"}, "slot")
            nonempty(item["number"], "slot number")
            if item["sub_part"] is not None:
                nonempty(item["sub_part"], "slot sub_part")
            require(item["module"] in raw["modules"], "slot references unknown module")
            positive_number(item["marks"], "slot marks")
            position = (item["number"], item["sub_part"])
            require(position not in positions, "duplicate slot position")
            positions.add(position)
            slots.append(QuestionSlot(**item))
        require({slot.module for slot in slots} == set(raw["modules"]), "each module needs a slot")
        return cls(tuple(raw["modules"]), tuple(slots))


@dataclass(frozen=True, slots=True)
class SyntheticConfig:
    """Store the resolved structure beside generation controls and their combined hash."""

    raw: dict[str, Any]
    structure_raw: dict[str, Any]
    structure: PaperStructure
    config_hash: str

    @classmethod
    def load(cls, path: Path) -> "SyntheticConfig":
        """Resolve the structure beside its config so working-directory changes are harmless."""
        raw = read_json(path)
        nonempty(raw.get("paper_structure"), "paper_structure path")
        structure_raw = read_json(path.resolve().parent / raw["paper_structure"])
        return cls.from_dict(raw, structure_raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], structure_raw: dict[str, Any]) -> "SyntheticConfig":
        """Validate in-memory edits with the same rules and hashes as files."""
        raw = deepcopy(raw)
        structure_raw = deepcopy(structure_raw)
        keys(
            raw,
            {
                "is_synthetic",
                "seed",
                "years",
                "sittings",
                "subjects",
                "scheme",
                "paper_structure",
                "topics_per_module",
                "preferred_topics_per_module",
                "scenarios",
            },
            "synthetic config",
        )
        require(raw["is_synthetic"] is True, "generator only accepts synthetic configuration")
        integer(raw["seed"], "seed")
        years = raw["years"]
        require(isinstance(years, list), "years must be an array")
        for year in years:
            integer(year, "year", 1)
        require(len(years) >= 6, "synthetic fixtures require at least six years")
        require(years == sorted(set(years)), "years must be unique and increasing")
        unique_texts(raw["sittings"], "sittings")
        require(
            isinstance(raw["subjects"], list) and bool(raw["subjects"]), "subjects must be nonempty"
        )
        ids: set[str] = set()
        for subject in raw["subjects"]:
            keys(subject, {"id", "name"}, "subject config")
            for value in subject.values():
                nonempty(value, "synthetic subject")
            require(subject["id"] not in ids, "duplicate subject id")
            ids.add(subject["id"])
        keys(raw["scheme"], {"id", "name", "year"}, "scheme config")
        nonempty(raw["scheme"]["id"], "scheme id")
        nonempty(raw["scheme"]["name"], "scheme name")
        integer(raw["scheme"]["year"], "scheme year", 1)
        nonempty(raw["paper_structure"], "paper_structure path")
        structure = PaperStructure.from_dict(structure_raw)
        integer(raw["topics_per_module"], "topics_per_module", 2)
        integer(raw["preferred_topics_per_module"], "preferred_topics_per_module", 1)
        require(
            raw["preferred_topics_per_module"] < raw["topics_per_module"],
            "preferred topic pool must be smaller than the complete pool",
        )
        for module in structure.modules:
            count = sum(slot.module == module for slot in structure.slots)
            require(
                count <= raw["preferred_topics_per_module"],
                "preferred topic pool must cover the slots in each module",
            )
        keys(raw["scenarios"], set(SCENARIOS), "scenarios")
        probabilities: dict[str, float] = {}
        for name in SCENARIOS:
            scenario = raw["scenarios"][name]
            keys(scenario, {"preferred_probability"}, name)
            probability = scenario["preferred_probability"]
            require(
                type(probability) in (int, float) and 0 <= probability <= 1,
                f"{name} preferred_probability must be between zero and one",
            )
            probabilities[name] = probability
        require(probabilities["pure_noise"] == 0, "pure_noise must have zero preference")
        require(
            0 < probabilities["weak_repeat"] < probabilities["strong_repeat"],
            "require 0 < weak_repeat < strong_repeat <= 1",
        )
        digest = sha256(canonical_bytes({"generator": raw, "paper_structure": structure_raw}))
        return cls(raw, structure_raw, structure, digest)

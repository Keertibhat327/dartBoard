"""Build test corpora in memory so fixture text never needs tracked data files."""

from pathlib import Path

import pytest

from forecast.config import SyntheticConfig
from forecast.synthetic import generate
from labeling.schema import Dataset

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config() -> SyntheticConfig:
    return SyntheticConfig.load(ROOT / "configs" / "synthetic.json")


@pytest.fixture
def dataset(config: SyntheticConfig) -> Dataset:
    return generate(config, "strong_repeat")

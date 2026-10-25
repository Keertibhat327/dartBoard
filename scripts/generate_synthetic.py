"""A Windows-friendly entry point prints only provenance and computed fixture counts."""

import argparse
import json
from pathlib import Path

from forecast.config import SCENARIOS, SyntheticConfig
from forecast.synthetic import generate, write_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Fail clearly on bad inputs rather than producing partially trusted fixture data."""
    parser = argparse.ArgumentParser(description="Generate SYNTHETIC fixtures; no real VTU data.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--output", type=Path, help="New .json file under the project data/ folder")
    args = parser.parse_args(argv)
    output = args.output or Path("data") / "synthetic" / f"{args.scenario}.json"
    try:
        config = SyntheticConfig.load(args.config)
        manifest = write_dataset(generate(config, args.scenario), output, PROJECT_ROOT)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Synthetic fixture generation failed: {exc}\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

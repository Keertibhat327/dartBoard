"""Grant developer access locally, without exposing role changes over HTTP."""

import argparse

from api.accounts import Accounts
from api.server import ROOT, load_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grant developer access to an existing local account"
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    settings = load_settings(ROOT)
    try:
        Accounts(ROOT / settings["database"]).grant_developer(args.email)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    print("Developer access granted. Refresh the profile page.")


if __name__ == "__main__":
    main()

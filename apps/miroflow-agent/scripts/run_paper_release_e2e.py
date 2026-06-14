#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import warnings


_DEPRECATION_MESSAGE = (
    "scripts/run_paper_release_e2e.py is retired under paper-pipeline-cleanup. "
    "Paper discovery must start from professor-page homepage ingest; external "
    "author-profile database discovery is enrichment-only."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retired wrapper. Use the page-first paper homepage ingest path "
            "instead of author-profile paper discovery."
        )
    )
    parser.add_argument(
        "--homepage-ingest-command",
        action="store_true",
        help="Print the page-first command family and exit.",
    )
    parser.parse_args()

    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    print(_DEPRECATION_MESSAGE, file=sys.stderr)
    print(
        "Use scripts/run_homepage_paper_ingest.py or the seed-run page-first "
        "homepage publication ingestion path.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

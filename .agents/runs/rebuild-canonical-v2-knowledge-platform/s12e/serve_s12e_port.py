"""Launch the s12e isolated candidate on a scratch port without touching the runner.

The s12a runner hard-pins the candidate server to 0.0.0.0:18188 (which the
live r8 preview occupies). This wrapper monkeypatches only the parsed port,
then delegates to the runner's main with the original argv.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

RUN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUN_ROOT / "s12a"))

import complete_candidate_runner as runner  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        raise SystemExit("usage: serve_s12e_port.py <port> [runner args...]")
    port = int(sys.argv[1])
    original_parse_args = runner._parse_args

    def patched_parse_args(args=None):
        config = original_parse_args(args)
        return dataclasses.replace(config, port=port)

    runner._parse_args = patched_parse_args
    return runner.main(sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())

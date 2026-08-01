"""Serve the exact s12e Candidate from its serving pack on the scratch port.

The complete candidate runner pins serving to ``0.0.0.0:18188``; the live r8
release owns that port, so this wrapper moves only the socket to the scratch
port 18199.  Every other safety check (release/database/index/envelope
binding, pack authority, recorded serving bundle hash) is unchanged.
"""

from __future__ import annotations

import dataclasses
from importlib import util
from pathlib import Path
import sys
from typing import Any


SCRATCH_PORT = 18199


def _load_runner() -> Any:
    path = Path(__file__).resolve().parents[1] / "s12a/complete_candidate_runner.py"
    spec = util.spec_from_file_location("canonical_v2_s12e_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("complete candidate runner cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(args: list[str] | None = None) -> int:
    runner = _load_runner()
    raw_args = sys.argv[1:] if args is None else args
    base_parse = runner._parse_args

    def parse_with_scratch_port(values: Any = None) -> Any:
        config = base_parse(values)
        return dataclasses.replace(config, port=SCRATCH_PORT)

    runner._parse_args = parse_with_scratch_port
    return runner.main(raw_args)


if __name__ == "__main__":
    raise SystemExit(main())

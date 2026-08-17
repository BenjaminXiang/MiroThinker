#!/usr/bin/env python3
"""Legacy paper release wrapper.

The old release E2E used external author-profile discovery. That path is
retired by OpenSpec change `paper-pipeline-cleanup`. Keep this filename
as a compatibility entry point for operators, but delegate to the
page-first homepage ingest command that owns current paper discovery.
"""

from __future__ import annotations

from run_homepage_paper_ingest import main


if __name__ == "__main__":
    raise SystemExit(main())

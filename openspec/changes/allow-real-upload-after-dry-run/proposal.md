# Proposal: allow-real-upload-after-dry-run

Human doc: `docs/plans/2026-10-27-upload-413-nginx-body-limit.md` §7.

## Why

A dry run writes nothing, yet it occupied the duplicate slot: after a verification
dry run of the customer's patent workbook, the real commit of the same file was
refused with `409 duplicate_upload` — the customer could not import the file they
had just validated.

## What Changes

`UploadStore.find_active` becomes mode-aware: a real commit only matches previous
**real** uploads, a dry run only matches previous dry runs. The admission path
passes its own mode.

## Impact

- A dry run can no longer block an import.
- A real import still deduplicates against a previous real import (unchanged).
- No API or storage change; the column already exists.

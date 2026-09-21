#!/usr/bin/env bash
# Target-machine self check for the canonical-v2 delivery.
#
#   bash deploy/preflight.sh --repo <code-root> [--kit-dir <kit>] [options]
#
# Runs read-only checks and exits non-zero if any FAIL line was printed.
# Everything it prints is meant to be pasted into the delivery record; each line
# names the check, its verdict, and the concrete evidence.
#
#   [PASS]  check satisfied
#   [FAIL]  must be fixed before start (sets exit code 1)
#   [WARN]  degraded but not blocking (e.g. optional component missing)
#   [SKIP]  not checked here, with the reason
#
# The script never writes into the repo, never starts the service, and never
# prints secret material (key files are referenced by name only).
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
KIT_DIR="/var/tmp/mirothinker-delivery-kit"
COMMAND_FILE=""
STATE_DIR=""
PORT="18188"
FAST=0
NETWORK=1
EMBEDDING_URL=""
RERANK_URL=""
LLM_URL=""
PYTHON_OVERRIDE=""
FAILURES=0
WARNINGS=0
SYNC_DRY_RUN_TIMEOUT=120

# Frozen fallbacks from the delivery plan §3 (overridable by flag or env).
FROZEN_EMBEDDING_URL="http://100.64.0.27:18005/v1"
FROZEN_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-8B"
FROZEN_EMBEDDING_DIMENSION="4096"
FROZEN_RERANK_URL="http://100.64.0.27:18006"
DEFAULT_LLM_URL="https://star.sustech.edu.cn/service/model/qwen36/v1"

usage() {
	sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
	cat <<'USAGE'

Options:
  --repo DIR            code root (default: the tree holding this script)
  --kit-dir DIR         kit directory with checksums/sizes/site-paths
                        (default: /var/tmp/mirothinker-delivery-kit)
  --command-file FILE   serving command file
                        (default: <repo>/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh)
  --state-dir DIR       serving state directory (default: parsed from the command file)
  --port N              port that must be free (default 18188)
  --fast                verify data artifacts by size only, not by sha256
  --no-network          skip the outbound reachability probes
  --embedding-url URL   embedding endpoint (default: from the embedding bundle, else frozen value)
  --rerank-url URL      rerank endpoint (default: CANONICAL_V2_RERANK_BASE_URL, else frozen value)
  --llm-url URL         chat LLM endpoint (default: CHAT_LLM_PROFILE, else the gemma4 endpoint)
  --python PATH         interpreter to check against .python-version (default: the
                        project venv, else 'uv python find'); for testing the check
  -h, --help            this text
USAGE
}

pass() { printf '[PASS] %s\n' "$*"; }
fail() {
	printf '[FAIL] %s\n' "$*"
	FAILURES=$((FAILURES + 1))
}
warn() {
	printf '[WARN] %s\n' "$*"
	WARNINGS=$((WARNINGS + 1))
}
skip() { printf '[SKIP] %s\n' "$*"; }
section() { printf '\n== %s ==\n' "$*"; }

while [[ $# -gt 0 ]]; do
	case "$1" in
	--repo)
		REPO="${2:?--repo needs a value}"
		shift 2
		;;
	--kit-dir)
		KIT_DIR="${2:?--kit-dir needs a value}"
		shift 2
		;;
	--command-file)
		COMMAND_FILE="${2:?--command-file needs a value}"
		shift 2
		;;
	--state-dir)
		STATE_DIR="${2:?--state-dir needs a value}"
		shift 2
		;;
	--port)
		PORT="${2:?--port needs a value}"
		shift 2
		;;
	--fast)
		FAST=1
		shift
		;;
	--no-network)
		NETWORK=0
		shift
		;;
	--embedding-url)
		EMBEDDING_URL="${2:?--embedding-url needs a value}"
		shift 2
		;;
	--rerank-url)
		RERANK_URL="${2:?--rerank-url needs a value}"
		shift 2
		;;
	--llm-url)
		LLM_URL="${2:?--llm-url needs a value}"
		shift 2
		;;
	--python)
		PYTHON_OVERRIDE="${2:?--python needs a value}"
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		printf 'unknown argument: %s\n' "$1" >&2
		exit 2
		;;
	esac
done

REPO="$(cd -- "$REPO" && pwd)"
COMMAND_FILE="${COMMAND_FILE:-$REPO/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh}"

printf 'canonical-v2 site preflight\n'
printf 'repo         %s\n' "$REPO"
printf 'kit          %s\n' "$KIT_DIR"
printf 'command file %s\n' "$COMMAND_FILE"
printf 'started at   %s\n' "$(date -Iseconds)"

[[ -d "$REPO" ]] || {
	printf '[FAIL] repo directory does not exist: %s\n' "$REPO"
	exit 1
}
[[ -f "$COMMAND_FILE" ]] || {
	printf '[FAIL] command file does not exist: %s\n' "$COMMAND_FILE"
	exit 1
}

# ---------------------------------------------------------------------------
# command-file reader (the target's own file is the single source of truth)
# ---------------------------------------------------------------------------
COMMAND_TSV="$(mktemp)"
trap 'rm -f "$COMMAND_TSV"' EXIT
python3 - "$COMMAND_FILE" "$COMMAND_TSV" <<'PY'
import re
import shlex
import sys
from pathlib import Path

command_file, out_tsv = sys.argv[1], sys.argv[2]
tokens = shlex.split(Path(command_file).read_text())
rows: list[tuple[str, str]] = []
argv: list[str] = []
for token in tokens:
    if re.fullmatch(r"[A-Z_][A-Z0-9_]*=.*", token) and not argv:
        name, _, value = token.partition("=")
        rows.append((name, value))
    else:
        argv.append(token)
index = 0
while index < len(argv):
    token = argv[index]
    if token.startswith("--"):
        if "=" in token:
            flag, _, value = token.partition("=")
        else:
            flag = token
            value = ""
            if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                value = argv[index + 1]
                index += 1
        rows.append((flag, value))
    index += 1
with open(out_tsv, "w", encoding="utf-8") as handle:
    for name, value in rows:
        handle.write(f"{name}\t{value}\n")
PY

arg() {
	awk -F'\t' -v flag="$1" '$1==flag{print $2; exit}' "$COMMAND_TSV"
}

# Key files are searched the way the serving code searches them
# (providers/local_api_key.py, professor/llm_profiles.py): the code root, the app
# root, then every ancestor — which is how a worktree reaches the main
# checkout's key files. Only the path is ever reported, never the content.
find_key_file() {
	local filename="$1" candidate
	for candidate in "$REPO/$filename" "$REPO/apps/miroflow-agent/$filename"; do
		[[ -f "$candidate" ]] && {
			printf '%s' "$candidate"
			return 0
		}
	done
	local dir="$REPO"
	while [[ "$dir" != "/" ]]; do
		dir="$(dirname -- "$dir")"
		if [[ -f "$dir/$filename" ]]; then
			printf '%s' "$dir/$filename"
			return 0
		fi
	done
	return 1
}

PACK_DIR="$(arg --serving-pack)"
INDEX_ROOT="$(arg --index-root)"
GATE_ROOT="$(arg --accepted-backup-gate-root)"
ENVELOPE_OUT="$(arg --envelope-output)"
SERVING_BUNDLE="$(arg --recorded-serving-bundle)"
EMBEDDING_BUNDLE="$(arg --recorded-embedding-bundle)"
MILVUS_PATH="$(arg --accepted-original-milvus-path)"
EXPECTED_DB="$(arg --expected-database)"
RELEASE_ID="$(arg --candidate-release-id)"
INDEX_MARKER_SHA="$(arg --index-marker-sha256)"
SERVING_BUNDLE_SHA="$(arg --recorded-serving-bundle-sha256)"
STATE_DIR="${STATE_DIR:-$(dirname -- "$(arg CANONICAL_V2_ACCESS_LOG_DB)")}"
DATA_ROOT="$(dirname -- "$PACK_DIR")"

# ---------------------------------------------------------------------------
# 1. paths from site-paths.txt (fallback: the classification below is rebuilt
#    from the command file when the kit file is absent)
# ---------------------------------------------------------------------------
section "paths"
SITE_PATHS="$KIT_DIR/site-paths.txt"
if [[ -f "$SITE_PATHS" ]]; then
	pass "site-paths.txt found in kit ($(grep -vc '^#' "$SITE_PATHS") rows)"
	SITE_ROWS="$(mktemp)"
	grep -v '^#' "$SITE_PATHS" >"$SITE_ROWS"
else
	warn "site-paths.txt not found in $KIT_DIR — falling back to command-file parsing only"
	SITE_ROWS="$(mktemp)"
	printf 'dir\t@data-root\t\t\t数据根目录\n' >"$SITE_ROWS"
	printf 'dir\t--serving-pack\t\t\tserving pack dir\n' >>"$SITE_ROWS"
	printf 'dir\t--index-root\t\t\tindex root\n' >>"$SITE_ROWS"
	printf 'dir\t@state-dir\t\t\tstate dir\n' >>"$SITE_ROWS"
fi

resolve_row_value() {
	# resolve <flag> <reference value> -> path on THIS machine
	local flag="$1" reference="$2"
	case "$flag" in
	@repo) printf '%s' "$REPO" ;;
	@data-root) printf '%s' "$DATA_ROOT" ;;
	@state-dir) printf '%s' "$STATE_DIR" ;;
	@repo-entrypoint | @repo-runner | @python-pin)
		printf '%s' "${reference/\{REPO\}/$REPO}"
		;;
	--s12a) printf '%s' "${GATE_ROOT%/}/s12a" ;;
	--envelope-output | --accepted-backup-gate-root | --serving-pack | --index-root | \
		--recorded-serving-bundle | --recorded-embedding-bundle | --source-manifest | \
		--candidate-staging-root | --recorded-decision-bundle | --accepted-original-milvus-path | \
		CANONICAL_V2_MANUAL_RECALL_DIR | CANONICAL_V2_ACCESS_LOG_DB)
		local value
		value="$(arg "$flag")"
		if [[ -n "$value" ]]; then
			printf '%s' "$value"
		else
			printf '%s' "${reference/\{REPO\}/$REPO}"
		fi
		;;
	*) printf '%s' "${reference/\{REPO\}/$REPO}" ;;
	esac
}

while IFS=$'\t' read -r kind flag reference _check purpose; do
	[[ -n "${kind:-}" ]] || continue
	if [[ "$kind" == "# MISSING" ]]; then
		fail "site-paths row missing from the command file: $flag ($purpose)"
		continue
	fi
	value="$(resolve_row_value "$flag" "${reference:-}")"
	case "$kind" in
	dir)
		if [[ -d "$value" ]]; then
			pass "dir     $flag -> $value"
		else
			fail "dir     $flag -> $value is missing (create it: $purpose)"
		fi
		;;
	file)
		if [[ -s "$value" && -f "$value" ]]; then
			pass "file    $flag -> $value ($(stat -c '%s' "$value") bytes)"
		else
			fail "file    $flag -> $value is missing or empty ($purpose)"
		fi
		;;
	parentdir)
		if [[ -d "$(dirname -- "$value")" ]]; then
			pass "parentdir $flag -> $(dirname -- "$value")"
		else
			fail "parentdir $flag -> $(dirname -- "$value") is missing ($purpose)"
		fi
		;;
	string)
		if [[ -n "$value" ]]; then
			pass "string  $flag -> $value (no file needed)"
		else
			fail "string  $flag is empty in the command file ($purpose)"
		fi
		;;
	*) warn "unknown kind '$kind' for $flag — not checked" ;;
	esac
done <"$SITE_ROWS"
rm -f "$SITE_ROWS"

# ---------------------------------------------------------------------------
# 2. writability, state directory contract, forbidden artifact
# ---------------------------------------------------------------------------
section "writability and state"

if [[ -n "$PACK_DIR" && -d "$(dirname -- "$PACK_DIR")" ]]; then
	if [[ -w "$(dirname -- "$PACK_DIR")" ]]; then
		pass "pack parent dir is writable (mount receipt is written there): $(dirname -- "$PACK_DIR")"
	else
		fail "pack parent dir is NOT writable (boot writes <pack>.mount-receipt.json): $(dirname -- "$PACK_DIR")"
	fi
	if [[ -f "$PACK_DIR.mount-receipt.json" ]]; then
		pass "mount receipt present: $PACK_DIR.mount-receipt.json (boot reuses it instead of re-hashing 1.7 GB)"
	else
		warn "no mount receipt yet at $PACK_DIR.mount-receipt.json — first boot will hash the whole index (~2x slower)"
	fi
fi

if [[ -z "$STATE_DIR" || "$STATE_DIR" == "." ]]; then
	fail "state directory could not be derived (CANONICAL_V2_ACCESS_LOG_DB missing in the command file)"
else
	if [[ -d "$STATE_DIR" ]]; then
		pass "state dir exists: $STATE_DIR"
	else
		fail "state dir missing: $STATE_DIR — the admin console is silently unusable without it (mkdir -p and re-run)"
	fi
	[[ -w "$STATE_DIR" ]] && pass "state dir is writable" || fail "state dir is NOT writable: $STATE_DIR"
	ADMIN_DB="$STATE_DIR/admin-auth.sqlite3"
	ADMIN_KEY="$STATE_DIR/admin-auth.key"
	if [[ -f "$ADMIN_DB" && -f "$ADMIN_KEY" ]]; then
		pass "admin credential store present (admin-auth.sqlite3 + admin-auth.key)"
	elif [[ ! -f "$ADMIN_DB" && ! -f "$ADMIN_KEY" ]]; then
		pass "admin credential store absent — first boot will seed it and write admin-initial-password.txt"
	elif [[ -f "$ADMIN_DB" && ! -f "$ADMIN_KEY" ]]; then
		# Observed on a fresh boot: the store is seeded at startup, the session
		# signing key is created lazily on the first login
		# (admin_session.py:load_signing_key). Absence before that first login is
		# normal, so this is a warning, not a failure.
		warn "admin-auth.sqlite3 present but admin-auth.key is not yet created — expected until the first admin login; re-check after logging in and treat a persistent absence as a defect"
	else
		warn "admin-auth.key present without admin-auth.sqlite3 — the account store will be reseeded on the next boot and all existing sessions are invalidated (delete the stray key if that was not intended)"
	fi
	[[ -f "$STATE_DIR/admin-initial-password.txt" ]] &&
		warn "admin-initial-password.txt still in the state dir — log in and change the password, then delete it" ||
		pass "no leftover admin-initial-password.txt"
fi

if [[ -n "$INDEX_ROOT" && -e "$INDEX_ROOT/milvus.db" ]]; then
	fail "index root contains milvus.db — the isolated index must not carry a Milvus file: $INDEX_ROOT/milvus.db"
else
	pass "no milvus.db inside the index root"
fi

# ---------------------------------------------------------------------------
# 3. data-artifact digests
# ---------------------------------------------------------------------------
section "data artifacts"
CHECKSUMS="$KIT_DIR/checksums.sha256"
SIZES="$KIT_DIR/sizes.tsv"
# Relative entries in checksums.sha256/sizes.tsv are kit-relative, exactly how
# the builder wrote them, so both modes run from the kit directory.
if [[ "$FAST" == "1" ]]; then
	if [[ ! -f "$SIZES" ]]; then
		fail "--fast requested but $SIZES is missing"
	else
		mismatch=0
		total=0
		while IFS=$'\t' read -r path expected; do
			[[ -n "${path:-}" ]] || continue
			total=$((total + 1))
			resolved="$path"
			[[ "$path" == /* ]] || resolved="$KIT_DIR/$path"
			if [[ -f "$resolved" ]]; then
				actual="$(stat -c '%s' "$resolved")"
				if [[ "$actual" != "$expected" ]]; then
					fail "size mismatch: $path (expected $expected, found $actual)"
					mismatch=$((mismatch + 1))
				fi
			else
				fail "missing artifact: $path"
				mismatch=$((mismatch + 1))
			fi
		done <"$SIZES"
		[[ "$mismatch" == "0" ]] && pass "size-only check passed for $total artifacts ($SIZES)"
	fi
else
	if [[ ! -f "$CHECKSUMS" ]]; then
		fail "checksums.sha256 not found: $CHECKSUMS (re-run with --fast to check sizes only)"
	else
		verify_output="$(cd -- "$KIT_DIR" && sha256sum -c checksums.sha256 2>&1)"
		ok_count="$(printf '%s\n' "$verify_output" | grep -c ': OK$')"
		bad_count="$(printf '%s\n' "$verify_output" | grep -c ': FAILED$')"
		missing_count="$(printf '%s\n' "$verify_output" | grep -c 'No such file or directory')"
		printf '%s\n' "$verify_output" | grep -v ': OK$' | sed 's/^/       /' | head -20
		if [[ "$bad_count" == "0" && "$missing_count" == "0" ]]; then
			pass "sha256 verified for $ok_count artifacts (checksums.sha256)"
		else
			fail "digest verification failed: $bad_count mismatched, $missing_count missing (of $((ok_count + bad_count + missing_count)))"
		fi
	fi
fi

# ---------------------------------------------------------------------------
# 4. frozen-string cross-checks (the three-way identity the boot enforces)
# ---------------------------------------------------------------------------
section "frozen-string cross-checks"
if ! command -v python3 >/dev/null 2>&1; then
	skip "python3 not on PATH — cross-checks of manifest/bundle strings not run"
else
	CROSS_CHECK_OUTPUT="$(python3 - "$COMMAND_TSV" "$PACK_DIR" "$INDEX_ROOT" "$SERVING_BUNDLE" "$EMBEDDING_BUNDLE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

command_tsv, pack_dir, index_root, serving_bundle, embedding_bundle = sys.argv[1:6]
args = {}
for line in Path(command_tsv).read_text().splitlines():
    name, _, value = line.partition("\t")
    args.setdefault(name, value)

problems = []
notes = []


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:  # noqa: BLE001 - reported as a check line
        problems.append(f"unreadable JSON: {path} ({exc})")
        return None


manifest_path = Path(pack_dir) / "manifest.json"
manifest = read_json(manifest_path) if manifest_path.is_file() else None
if manifest is None:
    problems.append(f"pack manifest missing or unreadable: {manifest_path}")

marker_path = Path(index_root) / ".canonical-v2-isolated-index-target.json"
marker = read_json(marker_path) if marker_path.is_file() else None
if marker is None:
    problems.append(f"index marker missing or unreadable: {marker_path}")

bundle = read_json(serving_bundle) if serving_bundle and Path(serving_bundle).is_file() else None
if bundle is None:
    problems.append(f"serving bundle missing or unreadable: {serving_bundle}")

embedding = (
    read_json(embedding_bundle)
    if embedding_bundle and Path(embedding_bundle).is_file()
    else None
)
if embedding is None:
    problems.append(f"embedding bundle missing or unreadable: {embedding_bundle}")

cli_index_root = args.get("--index-root", "")
cli_release = args.get("--candidate-release-id", "")
cli_expected_db = args.get("--expected-database", "")
cli_envelope = args.get("--envelope-output", "")
cli_gate_root = args.get("--accepted-backup-gate-root", "")
cli_milvus = args.get("--accepted-original-milvus-path", "")
cli_marker_sha = args.get("--index-marker-sha256", "")
cli_bundle_sha = args.get("--recorded-serving-bundle-sha256", "")

if manifest is not None:
    if manifest.get("index_root") == cli_index_root:
        notes.append(f"index_root agrees (pack manifest == --index-root): {cli_index_root}")
    else:
        problems.append(
            "index_root differs: pack manifest "
            f"{manifest.get('index_root')!r} != --index-root {cli_index_root!r}"
        )
    if manifest.get("release_id") == cli_release:
        notes.append(f"release_id agrees: {cli_release}")
    else:
        problems.append(
            f"release differs: pack {manifest.get('release_id')!r} != CLI {cli_release!r}"
        )
    forbidden = list(manifest.get("index_forbidden_milvus_paths") or [])
    if forbidden and forbidden[0].rstrip("/") == cli_milvus.rstrip("/"):
        notes.append(f"forbidden milvus path agrees: {cli_milvus}")
    else:
        problems.append(
            f"forbidden milvus path differs: pack {forbidden} != CLI {cli_milvus!r}"
        )
    if manifest.get("index_marker_sha256") == cli_marker_sha:
        notes.append("manifest index_marker_sha256 == --index-marker-sha256")
    else:
        problems.append(
            "manifest index_marker_sha256 "
            f"{manifest.get('index_marker_sha256')!r} != CLI {cli_marker_sha!r}"
        )

if marker is not None:
    if marker.get("root") == cli_index_root:
        notes.append("index marker root == --index-root")
    else:
        problems.append(
            f"index marker root {marker.get('root')!r} != --index-root {cli_index_root!r}"
        )
    if marker_path.is_file():
        digest = hashlib.sha256(marker_path.read_bytes()).hexdigest()
        if digest == cli_marker_sha:
            notes.append(f"index marker file sha256 == --index-marker-sha256 ({digest[:16]}…)")
        else:
            problems.append(
                f"index marker file sha256 {digest} != --index-marker-sha256 {cli_marker_sha}"
            )

if bundle is not None:
    if bundle.get("content_sha256") == cli_bundle_sha:
        notes.append("serving bundle content_sha256 == --recorded-serving-bundle-sha256")
    else:
        problems.append(
            "serving bundle content_sha256 "
            f"{bundle.get('content_sha256')!r} != CLI {cli_bundle_sha!r}"
        )
    if bundle.get("index_root") == cli_index_root:
        notes.append("serving bundle index_root == --index-root")
    else:
        problems.append(
            f"serving bundle index_root {bundle.get('index_root')!r} != CLI {cli_index_root!r}"
        )
    if bundle.get("envelope_path") == cli_envelope:
        notes.append("serving bundle envelope_path == --envelope-output")
    else:
        problems.append(
            "serving bundle envelope_path "
            f"{bundle.get('envelope_path')!r} != --envelope-output {cli_envelope!r} "
            "(the boot fails closed on this)"
        )
    if bundle.get("database_name") == cli_expected_db:
        notes.append("serving bundle database_name == --expected-database")
    else:
        problems.append(
            f"serving bundle database_name {bundle.get('database_name')!r} != CLI {cli_expected_db!r}"
        )
    if bundle.get("release_id") == cli_release:
        notes.append("serving bundle release_id == --candidate-release-id")

if cli_release:
    derived = "miroflow_" + cli_release.replace("-", "_")
    if derived == cli_expected_db:
        notes.append(f"--expected-database matches the release identity ({derived})")
    else:
        problems.append(
            f"--expected-database {cli_expected_db!r} != miroflow_{cli_release.replace('-', '_')}"
        )

if cli_envelope and cli_gate_root:
    expected = str(Path(cli_gate_root) / "s12a" / "complete-candidate-build-envelope.json")
    if expected == cli_envelope:
        notes.append(f"--envelope-output is the fixed evidence path ({expected})")
    else:
        problems.append(
            f"--envelope-output {cli_envelope!r} != fixed evidence path {expected!r}"
        )

if embedding is not None:
    if embedding.get("base_url"):
        notes.append(f"embedding bundle base_url: {embedding.get('base_url')}")
    if str(embedding.get("dimension")) == "4096":
        notes.append("embedding bundle dimension == 4096")
    else:
        problems.append(f"embedding bundle dimension is {embedding.get('dimension')!r}, expected 4096")

print("NOTES")
for note in notes:
    print(f"NOTE\t{note}")
print("PROBLEMS")
for problem in problems:
    print(f"PROBLEM\t{problem}")
PY
)"
	while IFS=$'\t' read -r kind text; do
		case "$kind" in
		NOTE) pass "cross-check: $text" ;;
		PROBLEM) fail "cross-check: $text" ;;
		esac
	done < <(printf '%s\n' "$CROSS_CHECK_OUTPUT" | awk -F'\t' '$1=="NOTE"||$1=="PROBLEM"')
fi

# ---------------------------------------------------------------------------
# 5. runtime: uv, python, dependency plan
# ---------------------------------------------------------------------------
section "runtime"
if command -v uv >/dev/null 2>&1; then
	pass "uv on PATH: $(uv --version 2>&1 | head -1)"
	if [[ -f "$REPO/uv.lock" && -f "$REPO/pyproject.toml" ]]; then
		sync_output="$(cd -- "$REPO" && timeout "$SYNC_DRY_RUN_TIMEOUT" uv sync --frozen --dry-run 2>&1)"
		sync_status=$?
		if [[ "$sync_status" == "0" ]]; then
			pass "uv sync --frozen is plannable (--dry-run, no changes made)"
		elif [[ "$sync_status" == "124" ]]; then
			warn "uv sync --frozen --dry-run timed out after ${SYNC_DRY_RUN_TIMEOUT}s (network or resolver slow)"
		else
			fail "uv sync --frozen --dry-run failed (exit $sync_status): $(printf '%s' "$sync_output" | tail -3 | tr '\n' ' ')"
		fi
	else
		fail "uv.lock / pyproject.toml missing in $REPO — cannot rebuild the venv here"
	fi
else
	fail "uv is not on PATH — install it (curl -LsSf https://astral.sh/uv/install.sh | sh) before continuing"
fi
if command -v python3 >/dev/null 2>&1; then
	pass "system python3: $(python3 -V 2>&1)"
	PATCH_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
	[[ "$PATCH_VERSION" == "3.12" ]] ||
		skip "system python3 is $PATCH_VERSION; the venv is rebuilt by uv with its own 3.12 interpreter"
else
	warn "python3 not on PATH"
fi

# ---------------------------------------------------------------------------
# 6. interpreter contract — the reader digest decides whether boot is 280 s or
#    ~470 s. open_serving_pack_authority compares the pack's recorded
#    reader_contract_sha256 with reader_contract_digest(), which hashes
#    sha256(python patch version + pydantic version + every canonical_v2/*.py).
#    On a mismatch it does not fail: it silently replays the relationship/index
#    reconstruction (~190 s extra on every boot). The patch is therefore part of
#    the delivery contract, pinned once in .python-version (the file uv reads to
#    pick the interpreter for uv sync/uv run) — this check reads that same file.
# ---------------------------------------------------------------------------
section "interpreter contract"
PYTHON_PIN_FILE="$REPO/.python-version"
PYTHON_PIN=""
[[ -f "$PYTHON_PIN_FILE" ]] &&
	PYTHON_PIN="$(head -1 "$PYTHON_PIN_FILE" | tr -d '[:space:]')"

if [[ -n "$PYTHON_OVERRIDE" ]]; then
	BOOT_PY="$PYTHON_OVERRIDE"
	BOOT_PY_SOURCE="--python override (test only)"
elif [[ -x "$REPO/.venv/bin/python" ]]; then
	BOOT_PY="$REPO/.venv/bin/python"
	BOOT_PY_SOURCE="project venv — what 'uv run python' uses in this tree"
elif command -v uv >/dev/null 2>&1; then
	BOOT_PY="$(cd -- "$REPO" && uv python find 2>/dev/null)"
	BOOT_PY_SOURCE="uv python find (no venv yet)"
fi
BOOT_PY="${BOOT_PY:-}"

if [[ -z "$PYTHON_PIN" ]]; then
	fail "no interpreter pin: $PYTHON_PIN_FILE is missing or empty — the serving pack is sealed with one python patch version (see deploy/README.md 现场交付); without the pin a fresh uv sync may pick another patch and silently add ~190 s to every boot"
else
	pass "interpreter pin (.python-version): $PYTHON_PIN"
fi

BOOT_PY_VERSION=""
if [[ -z "$BOOT_PY" || ! -x "$BOOT_PY" ]]; then
	fail "cannot resolve the interpreter the boot will use (no $REPO/.venv/bin/python and 'uv python find' returned nothing) — run 'uv sync --frozen' first, then re-run this check"
else
	BOOT_PY_VERSION="$("$BOOT_PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
	if [[ -z "$BOOT_PY_VERSION" ]]; then
		fail "could not read the interpreter version from $BOOT_PY"
	elif [[ -n "$PYTHON_PIN" && "$BOOT_PY_VERSION" != "$PYTHON_PIN" ]]; then
		fail "boot interpreter is CPython $BOOT_PY_VERSION but the pack was sealed with CPython $PYTHON_PIN ($BOOT_PY_SOURCE: $BOOT_PY) — the boot will not fail, it will silently replay the reconstruction: ≈190 s added to EVERY boot (measured 466 s vs 276 s on the same machine and data root). Fix: uv python pin $PYTHON_PIN && uv sync --frozen (uv downloads the matching patch if it is missing), then re-run preflight"
	elif [[ -n "$PYTHON_PIN" ]]; then
		pass "boot interpreter matches the pin: CPython $BOOT_PY_VERSION ($BOOT_PY_SOURCE)"
	fi
fi

# The pack itself is the authority on whether the patch matters: compare the
# digest this interpreter computes against the one the seal recorded. This also
# catches pydantic drift and any edit to canonical_v2/*.py, which the version
# comparison cannot see.
PACK_MANIFEST_PATH="$PACK_DIR/manifest.json"
RECORDED_READER_DIGEST=""
if [[ -f "$PACK_MANIFEST_PATH" ]]; then
	RECORDED_READER_DIGEST="$(python3 -c '
import json, sys
try:
    value = json.loads(open(sys.argv[1], encoding="utf-8").read()).get("reader_contract_sha256")
except Exception:
    value = None
print(value or "")
' "$PACK_MANIFEST_PATH" 2>/dev/null)"
fi
if [[ -z "$RECORDED_READER_DIGEST" ]]; then
	warn "the pack records no reader_contract_sha256 — every boot replays the reconstruction by design (~190 s); nothing to compare"
elif [[ -z "$BOOT_PY_VERSION" || ( -n "$PYTHON_PIN" && "$BOOT_PY_VERSION" != "$PYTHON_PIN" ) ]]; then
	skip "reader-contract digest: not computed while the interpreter differs from the pin"
else
	READER_DIGEST_OUTPUT="$(cd -- "$REPO" && timeout 120 "$BOOT_PY" -c '
import sys
from src.data_agents.canonical_v2.serving_pack_loader import reader_contract_digest
print(reader_contract_digest())
' 2>&1)"
	LOCAL_READER_DIGEST="$(printf '%s\n' "$READER_DIGEST_OUTPUT" | tail -1 | tr -d '[:space:]')"
	if [[ "$LOCAL_READER_DIGEST" == "$RECORDED_READER_DIGEST" ]]; then
		pass "reader-contract digest matches the pack (${LOCAL_READER_DIGEST:0:16}…): this boot takes the fast path, no reconstruction replay"
	elif [[ ! "$LOCAL_READER_DIGEST" =~ ^[0-9a-f]{64}$ ]]; then
		warn "could not compute the reader-contract digest yet ($(printf '%s' "$READER_DIGEST_OUTPUT" | tail -1 | cut -c1-120)) — run 'uv sync --frozen' and re-run preflight before acceptance"
	else
		fail "reader-contract digest differs from the pack (local ${LOCAL_READER_DIGEST:0:16}… vs pack ${RECORDED_READER_DIGEST:0:16}…) — the boot will silently replay the reconstruction (≈190 s per boot). The digest covers the python patch, the pydantic version and every canonical_v2/*.py byte: check the interpreter pin first, then that nothing edited the serving code"
	fi
fi

# ---------------------------------------------------------------------------
# 7. ports
# ---------------------------------------------------------------------------
section "ports"
if command -v ss >/dev/null 2>&1; then
	LISTENERS="$(ss -lntH 2>/dev/null | awk '{print $4}')"
	if printf '%s\n' "$LISTENERS" | grep -qE "[:.]$PORT\$"; then
		holder="$(ss -lntp 2>/dev/null | grep -E "[:.]$PORT\b" | head -1)"
		fail "port $PORT is already in use: ${holder:-unknown holder} (a second instance would fail to bind; the boot logs 'address already in use')"
	else
		pass "port $PORT is free"
	fi
	printf '%s\n' "$LISTENERS" | grep -qE '[:.]18188$' &&
		pass "port 18188 is already serving (existing instance left untouched by this check)"
else
	warn "ss not available — port check skipped"
fi

# ---------------------------------------------------------------------------
# 8. outbound reachability
# ---------------------------------------------------------------------------
section "outbound"
if [[ "$NETWORK" == "0" ]]; then
	skip "network probes disabled by --no-network"
elif ! command -v curl >/dev/null 2>&1; then
	fail "curl is required for the reachability probes and is not installed"
else
	# --- embedding: the one probe that must assert a dimension ---------------
	EMBEDDING_URL="${EMBEDDING_URL:-$(python3 -c '
import json, sys
from pathlib import Path
try:
    print(json.loads(Path(sys.argv[1]).read_text()).get("base_url", ""))
except Exception:
    print("")
' "$EMBEDDING_BUNDLE" 2>/dev/null)}"
	EMBEDDING_URL="${EMBEDDING_URL:-$FROZEN_EMBEDDING_URL}"
	EMBEDDING_MODEL="$(python3 -c '
import json, sys
from pathlib import Path
try:
    print(json.loads(Path(sys.argv[1]).read_text()).get("model_id", "") or "")
except Exception:
    print("")
' "$EMBEDDING_BUNDLE" 2>/dev/null)"
	EMBEDDING_MODEL="${EMBEDDING_MODEL:-$FROZEN_EMBEDDING_MODEL}"

	KEY_FILE="$(find_key_file .sglang_api_key)"
	KEY=""
	for candidate in SGLANG_API_KEY OPENAI_API_KEY API_KEY; do
		if [[ -n "${!candidate:-}" ]]; then
			KEY="${!candidate}"
			break
		fi
	done
	if [[ -n "$KEY" ]]; then
		KEY_SOURCE="environment"
	elif [[ -n "$KEY_FILE" ]]; then
		KEY="$(head -c 4096 "$KEY_FILE" | tr -d '\r\n')"
		KEY_SOURCE="key file $KEY_FILE (contents never printed)"
	else
		KEY_SOURCE="none"
		warn "no embedding credential found (env SGLANG_API_KEY/API_KEY/OPENAI_API_KEY or a .sglang_api_key file)"
	fi

	PROBE_BODY="$(printf '{"model":"%s","input":["ping"]}' "$EMBEDDING_MODEL")"
	CURL_CONFIG="$(mktemp)"
	if [[ -n "$KEY" ]]; then
		printf 'header = "Authorization: Bearer %s"\n' "$KEY" >"$CURL_CONFIG"
	fi
	EMBEDDING_RESPONSE="$(curl -sS --max-time 30 -o /tmp/.preflight-embedding.json -w '%{http_code}' \
		--config "$CURL_CONFIG" -H 'Content-Type: application/json' \
		-d "$PROBE_BODY" "${EMBEDDING_URL%/}/embeddings" 2>/tmp/.preflight-embedding.err)"
	rm -f "$CURL_CONFIG"
	if [[ "$EMBEDDING_RESPONSE" == "200" ]]; then
		DIMENSION="$(python3 -c '
import json, sys
try:
    payload = json.loads(open("/tmp/.preflight-embedding.json").read())
    print(len(payload["data"][0]["embedding"]))
except Exception:
    print("unparsable")
')"
		if [[ "$DIMENSION" == "$FROZEN_EMBEDDING_DIMENSION" ]]; then
			pass "embedding endpoint reachable and dimension == 4096 ($EMBEDDING_URL, key source: $KEY_SOURCE)"
		else
			fail "embedding endpoint answered 200 but dimension is $DIMENSION (expected 4096) — wrong model/endpoint"
		fi
	else
		fail "embedding endpoint POST ${EMBEDDING_URL%/}/embeddings failed (http=$EMBEDDING_RESPONSE): $(head -c 200 /tmp/.preflight-embedding.err 2>/dev/null | tr '\n' ' ')"
	fi
	rm -f /tmp/.preflight-embedding.json /tmp/.preflight-embedding.err

	# --- rerank: reachability only (the lane is optional and fails open) -----
	RERANK_URL="${RERANK_URL:-${CANONICAL_V2_RERANK_BASE_URL:-$FROZEN_RERANK_URL}}"
	RERANK_KEY="${CANONICAL_V2_RERANK_API_KEY:-}"
	if [[ -z "$RERANK_KEY" && -n "${CANONICAL_V2_RERANK_API_KEY_FILE:-}" && -f "$CANONICAL_V2_RERANK_API_KEY_FILE" ]]; then
		RERANK_KEY="$(head -c 4096 "$CANONICAL_V2_RERANK_API_KEY_FILE" | tr -d '\r\n')"
	fi
	RERANK_CONFIG="$(mktemp)"
	[[ -n "$RERANK_KEY" ]] && printf 'header = "Authorization: Bearer %s"\n' "$RERANK_KEY" >"$RERANK_CONFIG"
	RERANK_STATUS="$(curl -sS --max-time 15 -o /tmp/.preflight-rerank.json -w '%{http_code}' \
		--config "$RERANK_CONFIG" -H 'Content-Type: application/json' \
		-d '{"model":"qwen3-reranker-8b","query":"ping","documents":["ping"]}' \
		"${RERANK_URL%/}/v1/rerank" 2>/tmp/.preflight-rerank.err || true)"
	rm -f "$RERANK_CONFIG"
	if [[ "$RERANK_STATUS" =~ ^[234] ]]; then
		pass "rerank endpoint reachable (http=$RERANK_STATUS, $RERANK_URL)"
		[[ "$RERANK_STATUS" == "200" ]] || warn "rerank endpoint answered $RERANK_STATUS — the lane is fail-open, but check model/key before acceptance"
	elif [[ "$RERANK_STATUS" == "000" ]]; then
		warn "rerank endpoint unreachable ($RERANK_URL): $(head -c 200 /tmp/.preflight-rerank.err 2>/dev/null | tr '\n' ' ') — reranking stays disabled, answers still produced"
	else
		warn "rerank endpoint answered http=$RERANK_STATUS ($RERANK_URL)"
	fi
	rm -f /tmp/.preflight-rerank.json /tmp/.preflight-rerank.err

	# --- chat LLM: reachability of the configured profile -------------------
	# The effective profile is decided at boot by the managed settings file, then
	# the environment, then the code default (managed_config.py:_FIELD_ENV_VARS +
	# managed_runtime.apply_managed_runtime_config); the profile decides both the
	# endpoint and the credential (professor/llm_profiles.py). Both are read from
	# the shipped source instead of being duplicated here.
	LLM_PROFILE="${CHAT_LLM_PROFILE:-$(arg CHAT_LLM_PROFILE)}"
	LLM_FACTS="$(python3 - "$REPO" "${LLM_PROFILE:-}" <<'PY'
import json
import re
import sys
from pathlib import Path

repo, requested = Path(sys.argv[1]), sys.argv[2].strip()
profile = requested
managed = repo / "config" / "managed" / "settings.json"
if not profile and managed.is_file():
    try:
        value = (json.loads(managed.read_text()).get("serving") or {}).get(
            "chat_llm_profile"
        )
        profile = str(value).strip() if value else ""
    except Exception:  # noqa: BLE001 - a broken settings file is reported elsewhere
        profile = ""
profile = profile or "gemma4"

source = repo / "apps" / "miroflow-agent" / "src" / "data_agents" / "professor" / "llm_profiles.py"
base_url, key_env, key_file = "", "", ""
try:
    text = source.read_text(encoding="utf-8")
    alias_block = re.search(r"_PROFILE_ALIASES[^{]*\{(.*?)\}", text, re.S)
    aliases = dict(re.findall(r'"([\w\.]+)":\s*"([\w\.]+)"', alias_block.group(1))) if alias_block else {}
    resolved = aliases.get(profile, profile)
    block = re.search(
        r'"%s":\s*_LLMProfile\(\s*local=_LLMEndpoint\(([^)]*)\)' % re.escape(resolved),
        text,
        re.S,
    )
    if block:
        fields = dict(re.findall(r'(\w+)="([^"]*)"', block.group(1)))
        base_url = fields.get("base_url", "")
        key_env = fields.get("api_key_env", "")
    key_map_block = re.search(r"_KEY_FILE_BY_ENV[^{]*\{(.*?)\}", text, re.S)
    key_map = dict(re.findall(r'"([A-Z_]+)":\s*"(\.[\w\.]+)"', key_map_block.group(1))) if key_map_block else {}
    key_file = key_map.get(key_env, "")
except Exception:  # noqa: BLE001 - fall back to the frozen default below
    pass

print("\t".join((profile, base_url, key_env, key_file)))
PY
)"
	LLM_PROFILE="${LLM_FACTS%%$'\t'*}"
	LLM_BASE_URL="$(printf '%s' "$LLM_FACTS" | cut -f2)"
	LLM_KEY_ENV="$(printf '%s' "$LLM_FACTS" | cut -f3)"
	LLM_KEY_FILE_NAME="$(printf '%s' "$LLM_FACTS" | cut -f4)"
	if [[ -z "$LLM_BASE_URL" ]]; then
		LLM_URL="${LLM_URL:-$DEFAULT_LLM_URL}"
		warn "chat LLM profile '$LLM_PROFILE' is not in llm_profiles.py — probing the frozen default $LLM_URL"
	else
		LLM_URL="${LLM_URL:-$LLM_BASE_URL}"
	fi
	[[ -n "$LLM_KEY_FILE_NAME" ]] || LLM_KEY_FILE_NAME=".sglang_api_key"
	LLM_KEY_FILE="$(find_key_file "$LLM_KEY_FILE_NAME" 2>/dev/null || true)"
	LLM_KEY=""
	[[ -n "${LLM_KEY_ENV:-}" && -n "${!LLM_KEY_ENV:-}" ]] && LLM_KEY="${!LLM_KEY_ENV}"
	if [[ -z "$LLM_KEY" && -n "$LLM_KEY_FILE" ]]; then
		LLM_KEY="$(head -c 4096 "$LLM_KEY_FILE" | tr -d '\r\n')"
	fi
	LLM_CONFIG="$(mktemp)"
	[[ -n "$LLM_KEY" ]] && printf 'header = "Authorization: Bearer %s"\n' "$LLM_KEY" >"$LLM_CONFIG"
	LLM_STATUS="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' --config "$LLM_CONFIG" "${LLM_URL%/}/models" 2>/dev/null || true)"
	rm -f "$LLM_CONFIG"
	case "$LLM_STATUS" in
	2*) pass "chat LLM endpoint reachable (http=$LLM_STATUS, profile=$LLM_PROFILE, $LLM_URL)" ;;
	401 | 403)
		warn "chat LLM endpoint reachable but rejected the probe (http=$LLM_STATUS, profile=$LLM_PROFILE, $LLM_URL) — check $LLM_KEY_ENV/$LLM_KEY_FILE_NAME before acceptance"
		;;
	000) fail "chat LLM endpoint unreachable ($LLM_URL, profile=$LLM_PROFILE) — answers cannot be produced" ;;
	*)
		warn "chat LLM endpoint answered http=$LLM_STATUS (profile=$LLM_PROFILE, $LLM_URL) — the service still answers, but prose synthesis degrades to the template"
		;;
	esac

	# --- PyPI for the venv rebuild -----------------------------------------
	PYPI_STATUS="$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' https://pypi.org/simple/ 2>/dev/null || true)"
	[[ "$PYPI_STATUS" == "200" ]] && pass "pypi.org reachable (uv sync can rebuild the venv)" ||
		fail "pypi.org unreachable (http=$PYPI_STATUS) — uv sync needs network or a prepared wheel cache"
fi

# ---------------------------------------------------------------------------
# 9. optional components and sizing (reported, never blocking)
# ---------------------------------------------------------------------------
section "optional components"
CHROMIUM_DIR="$(ls -d "$HOME"/.cache/ms-playwright/chromium* 2>/dev/null | head -1 || true)"
if [[ -n "$CHROMIUM_DIR" ]]; then
	pass "playwright chromium present: $CHROMIUM_DIR"
else
	warn "playwright chromium not found (uv run playwright install chromium) — page fetching degrades, the service still runs"
fi
if command -v psql >/dev/null 2>&1 || command -v pg_isready >/dev/null 2>&1; then
	pass "postgresql client present ($(command -v psql || command -v pg_isready))"
	if command -v pg_isready >/dev/null 2>&1; then
		pg_isready -q -h 127.0.0.1 2>/dev/null && pass "postgresql accepting connections on 127.0.0.1" ||
			warn "postgresql client present but no server answering on 127.0.0.1 (/seeds /upload /jobs stay 503)"
	fi
else
	warn "postgresql not installed — /seeds /upload and 3 maintenance jobs will 503; /chat is unaffected"
fi

MEM_TOTAL_GB="$(awk '/MemTotal/{printf "%.1f", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0)"
awk -v total="$MEM_TOTAL_GB" 'BEGIN{exit !(total < 64)}' &&
	warn "RAM is ${MEM_TOTAL_GB} GB, below the 64 GB requirement (measured RSS of the serving process is ~17 GB)" ||
	pass "RAM is ${MEM_TOTAL_GB} GB"
for path in "$REPO" "$DATA_ROOT"; do
	[[ -d "$path" ]] || continue
	free_gb="$(df -BG --output=avail "$path" 2>/dev/null | tail -1 | tr -dc '0-9')"
	[[ -n "$free_gb" ]] || continue
	if [[ "$free_gb" -lt 100 ]]; then
		warn "only ${free_gb} GB free on $path (delivery wants >=100 GB for data + backups)"
	else
		pass "${free_gb} GB free on $path"
	fi
done

section "summary"
printf 'failures=%d warnings=%d\n' "$FAILURES" "$WARNINGS"
if [[ "$FAILURES" -gt 0 ]]; then
	printf 'RESULT: NOT READY — fix the [FAIL] lines above and re-run\n'
	exit 1
fi
printf 'RESULT: READY (warnings are non-blocking, review them anyway)\n'
exit 0

#!/usr/bin/env bash
# Build the customer-site delivery kit from a source tree.
#
#   bash deploy/build-delivery-kit.sh --source-tree <repo> [--out-dir <dir>]
#
# The kit is a self-describing directory:
#   code.tar              the deployable code tree (data artifacts travel separately)
#   code.tar.sha256       its digest
#   bundles/              the small release bundles the serving stack reads at boot
#   checksums.sha256      sha256sum -c list for the data artifacts + bundles
#   sizes.tsv             path<TAB>size for the --fast verification mode
#   site-paths.txt        every path the target machine must provide, with a check
#   kit-manifest.txt      what is in this kit, its sizes and digests
#
# Re-running is cheap by construction: the tarball is rebuilt only when the
# included file set changes (fingerprint of path+size+mtime), and data-artifact
# digests are cached per (path, size, mtime) so the ~7 GB is never read twice
# for the same content. Nothing is ever copied out of a data artifact.
#
# Environment of the target machine is NOT touched: this script only reads.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE_TREE="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE_TREE=""
OUT_DIR="/var/tmp/mirothinker-delivery-kit"
COMMAND_FILE=""
DATA_ROOT=""
REFRESH_HASHES=0

usage() {
	sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
	cat <<'USAGE'

Options:
  --source-tree DIR   repo root to package (default: the tree holding this script)
  --out-dir DIR       kit directory (default: /var/tmp/mirothinker-delivery-kit)
  --command-file FILE serving command file to derive paths from
                      (default: <source-tree>/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh)
  --data-root DIR     root holding the serving pack + index root
                      (default: parsed from the command file)
  --refresh-hashes    ignore the digest cache (re-hash every data artifact)
  -h, --help          this text
USAGE
}

log() { printf '[kit] %s\n' "$*"; }
die() {
	printf '[kit] ERROR: %s\n' "$*" >&2
	exit 1
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--source-tree)
		SOURCE_TREE="${2:?--source-tree needs a value}"
		shift 2
		;;
	--out-dir)
		OUT_DIR="${2:?--out-dir needs a value}"
		shift 2
		;;
	--command-file)
		COMMAND_FILE="${2:?--command-file needs a value}"
		shift 2
		;;
	--data-root)
		DATA_ROOT="${2:?--data-root needs a value}"
		shift 2
		;;
	--refresh-hashes)
		REFRESH_HASHES=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*) die "unknown argument: $1" ;;
	esac
done

SOURCE_TREE="${SOURCE_TREE:-$DEFAULT_SOURCE_TREE}"
SOURCE_TREE="$(cd -- "$SOURCE_TREE" && pwd)"
[[ -f "$SOURCE_TREE/uv.lock" ]] || die "not a repo root (no uv.lock): $SOURCE_TREE"
COMMAND_FILE="${COMMAND_FILE:-$SOURCE_TREE/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh}"
[[ -f "$COMMAND_FILE" ]] || die "serving command file not found: $COMMAND_FILE"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"
mkdir -p "$OUT_DIR/bundles"

# ---------------------------------------------------------------------------
# command-file parsing: every path-like argument, classified by serving meaning
# ---------------------------------------------------------------------------
# The classification below is the reviewed contract of the live command file
# (see .agents/runs/delivery-kit-rehearsal/current-state.md). Kinds:
#   dir        must exist as a directory; content requirements noted per line
#   file       must exist as a regular file WITH CONTENT (read at serving time)
#   parentdir  the parent directory must exist; the file itself is never opened
#   string     never stat'ed at serving time; only its string participates in a
#              fail-closed comparison or a distinctness check
COMMAND_TSV="$OUT_DIR/.command-args.tsv"
python3 - "$COMMAND_FILE" "$COMMAND_TSV" <<'PY'
import json
import re
import shlex
import sys
from pathlib import Path

command_file, out_tsv = sys.argv[1], sys.argv[2]
tokens = shlex.split(Path(command_file).read_text())

env_assignments: dict[str, str] = {}
argv: list[str] = []
for token in tokens:
    if re.fullmatch(r"[A-Z_][A-Z0-9_]*=.*", token) and not argv:
        name, _, value = token.partition("=")
        env_assignments[name] = value
    else:
        argv.append(token)

KIND: dict[str, tuple[str, str]] = {
    "--serving-pack": ("dir", "服务包目录（manifest.json/relationships.json/lookup.sqlite3/institution_catalog.json 必须在位）"),
    "--index-root": ("dir", "索引根目录（lookup.sqlite3 + vector_matrix.npz + 索引 marker；路径被逐字符冻结）"),
    "--accepted-backup-gate-root": ("dir", "门禁/账本根目录；<它>/s12a/ 必须存在"),
    "--source-manifest": ("string", "解析期要求（服务模式从不打开）；仅参与路径去重"),
    "--candidate-staging-root": ("string", "解析期要求（服务模式从不打开）；仅参与路径去重"),
    "--recorded-decision-bundle": ("string", "解析期要求（服务模式从不打开）；仅参与路径去重"),
    "--recorded-embedding-bundle": ("file", "嵌入模型 bundle，服务启动时真实读取（含模型地址与维度）"),
    "--recorded-serving-bundle": ("file", "发布 bundle，服务启动时真实读取；其 envelope_path 与 --envelope-output 逐字符比对"),
    "--envelope-output": ("parentdir", "父目录必须存在；其字符串必须等于 <gate-root>/s12a/complete-candidate-build-envelope.json"),
    "--accepted-original-milvus-path": ("string", "仅与服务包 manifest 的 forbidden 路径逐字符比对；文件无需存在"),
}

argv_rows: list[tuple[str, str, str, str]] = []
index = 0
while index < len(argv):
    token = argv[index]
    if token.startswith("--"):
        flag = token
        value = ""
        if "=" in token:
            flag, _, value = token.partition("=")
        elif index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            value = argv[index + 1]
            index += 1
        if flag in KIND and value:
            kind, why = KIND[flag]
            argv_rows.append((kind, value, flag, why))
        elif flag not in KIND:
            argv_rows.append(("unknown", value or flag, flag, "命令文件里未分类的参数"))
    index += 1

state_dir = ""
env_rows: list[tuple[str, str, str, str]] = []
for name in sorted(env_assignments):
    value = env_assignments[name]
    if not value.startswith("/"):
        continue
    if name == "CANONICAL_V2_MANUAL_RECALL_DIR":
        env_rows.append(("dir", value, name, "手工召回道目录（空目录即可）"))
        continue
    path = Path(value)
    if path.name.endswith(".sqlite3"):
        state_dir = str(path.parent)
    env_rows.append(("file", value, name, "运行期账本（父目录必须先存在，文件由服务自建）"))

with open(out_tsv, "w", encoding="utf-8") as handle:
    handle.write(f"# source\t{command_file}\n")
    handle.write(f"# state_dir\t{state_dir}\n")
    for kind, value, flag, why in argv_rows + env_rows:
        handle.write("\t".join((kind, value, flag, why)) + "\n")
PY

STATE_DIR="$(awk -F'\t' '$1=="# state_dir"{print $2}' "$COMMAND_TSV")"
[[ -n "$STATE_DIR" ]] || die "could not derive the state directory from $COMMAND_FILE"

arg_value() {
	local flag="$1"
	awk -F'\t' -v flag="$flag" '$3==flag{print $2; exit}' "$COMMAND_TSV"
}

PACK_DIR="$(arg_value --serving-pack)"
INDEX_ROOT="$(arg_value --index-root)"
SERVING_BUNDLE="$(arg_value --recorded-serving-bundle)"
EMBEDDING_BUNDLE="$(arg_value --recorded-embedding-bundle)"
[[ -n "$PACK_DIR" && -n "$INDEX_ROOT" ]] || die "command file has no --serving-pack/--index-root"
[[ -d "$PACK_DIR" ]] || die "serving pack directory missing: $PACK_DIR"
[[ -d "$INDEX_ROOT" ]] || die "index root missing: $INDEX_ROOT"
# The data root is the pack's parent (it is the directory the mount receipt is
# written into) — the state directory intentionally lives elsewhere.
DATA_ROOT="${DATA_ROOT:-$(dirname -- "$PACK_DIR")}"

# ---------------------------------------------------------------------------
# 1. code.tar — the deployable tree, minus build detritus that is rebuilt (or
#    never read) at the site: venvs, node_modules, coverage output, caches,
#    local logs/state, and the multi-hundred-MB build envelopes.
# ---------------------------------------------------------------------------
log "collecting code tree file list from $SOURCE_TREE"
FILE_LIST="$OUT_DIR/.code-file-list.txt"
find "$SOURCE_TREE" \
	\( \
	-name .venv -o -name node_modules -o -name __pycache__ -o -name .pytest_cache \
	-o -name .ruff_cache -o -name .worktrees -o -name .git -o -name htmlcov \
	-o -name '.tmp-*' \
	\) -prune -o \
	\( -path "$SOURCE_TREE/logs" -o -path "$SOURCE_TREE/var" \) -prune -o \
	-type f \
	! -name report.html ! -name .coverage ! -name 'complete-candidate-build-envelope*.json' \
	-printf '%P\n' | LC_ALL=C sort >"$FILE_LIST"
CODE_FILE_COUNT="$(wc -l <"$FILE_LIST")"
[[ "$CODE_FILE_COUNT" -gt 0 ]] || die "no files selected for code.tar"

fingerprint() {
	local list="$1"
	while IFS= read -r rel; do
		printf '%s\t%s\t%s\n' "$rel" "$(stat -c '%s' "$SOURCE_TREE/$rel")" "$(stat -c '%Y' "$SOURCE_TREE/$rel")"
	done <"$list" | sha256sum | cut -d' ' -f1
}

CODE_TAR="$OUT_DIR/code.tar"
FINGERPRINT_FILE="$OUT_DIR/.code-fingerprint"
NEW_FINGERPRINT="$(fingerprint "$FILE_LIST")"
if [[ -f "$CODE_TAR" && -f "$FINGERPRINT_FILE" ]] && [[ "$(cat "$FINGERPRINT_FILE")" == "$NEW_FINGERPRINT" ]]; then
	log "code.tar unchanged (fingerprint $NEW_FINGERPRINT) — not rebuilt"
else
	log "writing code.tar ($CODE_FILE_COUNT files)"
	tar --no-recursion -C "$SOURCE_TREE" --files-from="$FILE_LIST" -cf "$CODE_TAR.tmp"
	mv "$CODE_TAR.tmp" "$CODE_TAR"
	printf '%s\n' "$NEW_FINGERPRINT" >"$FINGERPRINT_FILE"
fi
CODE_TAR_SHA="$(sha256sum "$CODE_TAR" | cut -d' ' -f1)"
printf '%s  code.tar\n' "$CODE_TAR_SHA" >"$OUT_DIR/code.tar.sha256"

# ---------------------------------------------------------------------------
# 2. bundles/ — the small release bundles, copied only when their digest moves
# ---------------------------------------------------------------------------
copy_if_changed() {
	local src="$1" dst="$2"
	[[ -f "$src" ]] || return 1
	if [[ -f "$dst" ]] && [[ "$(sha256sum "$src" | cut -d' ' -f1)" == "$(sha256sum "$dst" | cut -d' ' -f1)" ]]; then
		log "bundle unchanged: $(basename -- "$dst")"
	else
		cp -f -- "$src" "$dst"
		log "bundle copied: $(basename -- "$dst")"
	fi
	return 0
}

BUNDLE_LIST=()
for bundle in "$SERVING_BUNDLE" "$EMBEDDING_BUNDLE"; do
	[[ -n "$bundle" ]] || continue
	target="$OUT_DIR/bundles/$(basename -- "$bundle")"
	if copy_if_changed "$bundle" "$target"; then
		BUNDLE_LIST+=("$target")
	fi
done
[[ ${#BUNDLE_LIST[@]} -gt 0 ]] || die "no release bundles found to ship"

# ---------------------------------------------------------------------------
# 3. checksums.sha256 — data artifacts (frozen absolute paths) + kit bundles
# ---------------------------------------------------------------------------
# The digest cache keys on (path, size, mtime) so a re-run of an unchanged kit
# does not re-read 7 GB. `sha256sum -c` accepts the file as written: absolute
# paths for data artifacts, paths relative to the kit directory for bundles.
HASH_CACHE="$OUT_DIR/.hash-cache.tsv"
[[ -f "$HASH_CACHE" ]] || : >"$HASH_CACHE"
[[ "$REFRESH_HASHES" == "1" ]] && : >"$HASH_CACHE"

cached_sha() {
	local path="$1"
	local size mtime key hit
	size="$(stat -c '%s' "$path")"
	mtime="$(stat -c '%Y' "$path")"
	hit="$(awk -F'\t' -v p="$path" -v s="$size" -v m="$mtime" '$1==p && $2==s && $3==m{print $4; exit}' "$HASH_CACHE")"
	if [[ -n "$hit" ]]; then
		printf '%s' "$hit"
		return 0
	fi
	local digest
	digest="$(sha256sum "$path" | cut -d' ' -f1)"
	printf '%s\t%s\t%s\t%s\n' "$path" "$size" "$mtime" "$digest" >>"$HASH_CACHE"
	printf '%s' "$digest"
}

CHECKSUMS="$OUT_DIR/checksums.sha256"
SIZES="$OUT_DIR/sizes.tsv"
DATA_DIGESTS="$OUT_DIR/.data-digests.tsv"
: >"$CHECKSUMS"
: >"$SIZES"
: >"$DATA_DIGESTS"

DATA_FILES=()
while IFS= read -r -d '' artifact; do
	DATA_FILES+=("$artifact")
done < <(find "$PACK_DIR" "$INDEX_ROOT" -maxdepth 1 -type f -print0 | LC_ALL=C sort -z)
[[ ${#DATA_FILES[@]} -gt 0 ]] || die "no files found under $PACK_DIR / $INDEX_ROOT"

log "digesting ${#DATA_FILES[@]} data artifacts (cached)"
for artifact in "${DATA_FILES[@]}"; do
	digest="$(cached_sha "$artifact")"
	printf '%s  %s\n' "$digest" "$artifact" >>"$CHECKSUMS"
	printf '%s\t%s\t%s\n' "$artifact" "$(stat -c '%s' "$artifact")" "$digest" >>"$DATA_DIGESTS"
	printf '%s\t%s\n' "$artifact" "$(stat -c '%s' "$artifact")" >>"$SIZES"
done
for bundle in "${BUNDLE_LIST[@]}"; do
	digest="$(sha256sum "$bundle" | cut -d' ' -f1)"
	printf '%s  %s\n' "$digest" "bundles/$(basename -- "$bundle")" >>"$CHECKSUMS"
	printf '%s\t%s\t%s\n' "bundles/$(basename -- "$bundle")" "$(stat -c '%s' "$bundle")" "$digest" >>"$DATA_DIGESTS"
	printf '%s\t%s\n' "bundles/$(basename -- "$bundle")" "$(stat -c '%s' "$bundle")" >>"$SIZES"
done

# ---------------------------------------------------------------------------
# 4. site-paths.txt — the target-machine contract, derived from the command file
# ---------------------------------------------------------------------------
SITE_PATHS="$OUT_DIR/site-paths.txt"

row() {
	# row <kind> <flag-or-env> <reference-value> <check> <purpose>
	local kind="$1" flag="$2" path="$3" check="$4" purpose="$5"
	if [[ -z "$path" ]]; then
		printf '# MISSING\t%s\t（命令文件里没有这个参数）\t—\t%s\n' "$flag" "$purpose"
		return 0
	fi
	printf '%s\t%s\t%s\t%s\t%s\n' "$kind" "$flag" "$path" "$check" "$purpose"
}

{
	printf '# site-paths.txt — 目标机上必须就位的路径（由 deploy/build-delivery-kit.sh 从命令文件解析）\n'
	printf '# 来源命令文件: %s\n' "$COMMAND_FILE"
	printf '# 生成时间: %s\n' "$(date -Iseconds)"
	printf '#\n'
	printf '# 列：KIND<TAB>FLAG<TAB>参考取值（我方机器）<TAB>检查<TAB>用途\n'
	printf '# KIND  dir       = 必须存在；目录内容要求见"用途"\n'
	printf '#       file      = 必须是有内容的普通文件（服务启动时真实读取）\n'
	printf '#       parentdir = 只需父目录存在；文件本身服务期不打开\n'
	printf '#       string    = 只参与字符串比对/去重，无需存在\n'
	printf '# FLAG  命令行参数名，或环境变量名，或 @repo/@data-root/@state-dir 伪标记\n'
	printf '# PATH  我方机器上的取值，仅供现场对照；现场以你自己改好的命令文件为准\n'
	printf '#       （preflight.sh 从"目标机自己的命令文件"读取真实取值，不读本列）\n'
	printf '#\n'
	printf '# 现场改写提示：带 [现场改写] 的行，其路径不可能与我们相同，必须在命令文件里\n'
	printf '# 换成目标机上的位置；它们中的多数（string 类）只要求"存在一个不同的字符串"。\n'
	printf '#\n'
	row dir '@data-root' "$DATA_ROOT" 'ls -d' '数据根目录本身；服务包父目录必须可写（启动时写 <包名>.mount-receipt.json）'
	row dir '@repo' "$SOURCE_TREE" 'ls -d' '代码根目录：code.tar 解开的位置（现场自选）'
	row dir '@state-dir' "$STATE_DIR" 'ls -d' '[现场改写] 状态目录（现场自选）：账号库/签名密钥/首启口令/访问日志/更正/手工召回都落在这里；缺失时管理面静默不可用，必须是已存在的目录'
	row dir '--serving-pack' "$PACK_DIR" 'ls -d' '服务包：manifest.json(11M) + relationships.json(3.47G) + lookup.sqlite3(896M) + institution_catalog.json + .canonical-v2-isolated-index-target.json；路径被逐字符冻结'
	row dir '--index-root' "$INDEX_ROOT" 'ls -d' '索引根：lookup.sqlite3(896M) + vector_matrix.npz(1.68G) + .canonical-v2-isolated-index-target.json；路径被逐字符冻结，且不得含 milvus.db'
	row dir 'CANONICAL_V2_MANUAL_RECALL_DIR' "$(arg_value CANONICAL_V2_MANUAL_RECALL_DIR)" 'ls -d' '[现场改写] 手工召回道目录（空目录即可；建议放在状态目录附近）'
	row dir '--accepted-backup-gate-root' "$(arg_value --accepted-backup-gate-root)" 'ls -d' '[现场改写] 门禁/账本根目录（现场自选，空目录即可）；<它>/s12a/ 必须存在'
	row dir '--s12a' "$(arg_value --accepted-backup-gate-root)/s12a" 'ls -d' '[现场改写] <门禁根>/s12a/：解析期要求存在（空目录即可；服务模式不读 envelope）'
	row file '@repo-entrypoint' "$SOURCE_TREE/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/serve_s12e_port.py" 'test -s' '代码入口（code.tar 解开后即在位）'
	row file '@repo-runner' "$SOURCE_TREE/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py" 'test -s' '入口 import 的 runner（code.tar 解开后即在位）'
	row file '--recorded-serving-bundle' "$SERVING_BUNDLE" 'test -s' '[现场改写] 发布 bundle：服务启动时读取；内容随 kit 的 bundles/ 交付，现场放到自选位置后改命令文件'
	row file '--recorded-embedding-bundle' "$EMBEDDING_BUNDLE" 'test -s' '[现场改写] 嵌入模型 bundle：服务启动时读取（模型地址/维度来源）；内容随 kit 的 bundles/ 交付'
	row parentdir '--envelope-output' "$(arg_value --envelope-output)" "test -d $(dirname -- "$(arg_value --envelope-output)")" '[现场改写] 父目录必须存在；其字符串必须逐字符等于 <门禁根>/s12a/complete-candidate-build-envelope.json，且与发布 bundle 内的 envelope_path 一致'
	row string '--source-manifest' "$(arg_value --source-manifest)" '—' '[现场改写] 解析期占位：仅参与路径去重，服务模式从不打开（给个不重复的路径即可）'
	row string '--candidate-staging-root' "$(arg_value --candidate-staging-root)" '—' '[现场改写] 解析期占位：仅参与路径去重，服务模式从不打开（给个不重复的路径即可）'
	row string '--recorded-decision-bundle' "$(arg_value --recorded-decision-bundle)" '—' '[现场改写] 解析期占位：仅参与路径去重，服务模式从不打开（给个不重复的路径即可）'
	row string '--accepted-original-milvus-path' "$(arg_value --accepted-original-milvus-path)" '—' '仅与服务包 manifest 里的 forbidden 路径逐字符比对；文件无需存在，但字符串不能改'
} >"$SITE_PATHS"
# {REPO} marks the reference value that the target machine reproduces under its own code root.
sed -i "s#\t$SOURCE_TREE/#\t{REPO}/#g; s#\t$SOURCE_TREE\t#\t{REPO}\t#g" "$SITE_PATHS"

# ---------------------------------------------------------------------------
# 5. kit-manifest.txt
# ---------------------------------------------------------------------------
KIT_MANIFEST="$OUT_DIR/kit-manifest.txt"
{
	printf 'delivery kit manifest\n'
	printf 'built_at            %s\n' "$(date -Iseconds)"
	printf 'source_tree         %s\n' "$SOURCE_TREE"
	printf 'command_file        %s\n' "$COMMAND_FILE"
	printf 'code_tar_files      %s\n' "$CODE_FILE_COUNT"
	printf 'data_root           %s\n' "$DATA_ROOT"
	printf 'pack_dir            %s\n' "$PACK_DIR"
	printf 'index_root          %s\n' "$INDEX_ROOT"
	printf 'state_dir           %s\n' "$STATE_DIR"
	printf '\n'
	printf '== kit files ==\n'
	printf '%-24s %14s  %s\n' FILE SIZE SHA256
	for entry in code.tar site-paths.txt checksums.sha256 sizes.tsv; do
		printf '%-24s %14s  %s\n' "$entry" "$(stat -c '%s' "$OUT_DIR/$entry")" "$(sha256sum "$OUT_DIR/$entry" | cut -d' ' -f1)"
	done
	for bundle in "${BUNDLE_LIST[@]}"; do
		rel="bundles/$(basename -- "$bundle")"
		printf '%-24s %14s  %s\n' "$rel" "$(stat -c '%s' "$bundle")" "$(sha256sum "$bundle" | cut -d' ' -f1)"
	done
	printf '\n'
	printf '== data artifacts (verify in place with: sha256sum -c checksums.sha256) ==\n'
	printf '%-16s %14s  %s\n' SIZE SHA256 PATH
	while IFS=$'\t' read -r path size digest; do
		printf '%-16s %14s  %s\n' "$size" "$(printf '%.16s' "$digest")" "$path"
	done <"$DATA_DIGESTS" | LC_ALL=C sort -k3
	printf '\n'
	printf '== target-machine paths ==\n'
	grep -v '^#' "$SITE_PATHS" | awk -F'\t' '{printf "  %-10s %-32s %s\n", $1, $2, $3}'
} >"$KIT_MANIFEST"

log "kit written to $OUT_DIR"
du -sh "$OUT_DIR" | sed 's/^/[kit] size: /'
log "code.tar sha256: $CODE_TAR_SHA"
log "next: ship the kit, then on the target run: bash deploy/preflight.sh --repo <code-root> --kit-dir $OUT_DIR"

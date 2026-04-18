#!/usr/bin/env bash
# Load professor E2E credentials from environment or repo-local key files.

if [ -n "${BASH_SOURCE[0]:-}" ]; then
  _prof_e2e_loader_path="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _prof_e2e_loader_path="${(%):-%N}"
else
  _prof_e2e_loader_path="$0"
fi

_prof_e2e_script_dir="$(cd "$(dirname "${_prof_e2e_loader_path}")" && pwd)"
_prof_e2e_app_root="$(cd "${_prof_e2e_script_dir}/.." && pwd)"
_prof_e2e_repo_root="$(cd "${_prof_e2e_app_root}/../.." && pwd)"

_load_key_if_missing() {
  local var_name="$1"
  local filename="$2"
  local current_value=""
  eval "current_value=\${${var_name}-}"
  if [ -n "$current_value" ]; then
    export "${var_name}=${current_value}"
    return 0
  fi

  local root=""
  local file_path=""
  local file_value=""
  for root in "${_prof_e2e_repo_root}" "${_prof_e2e_app_root}"; do
    file_path="${root}/${filename}"
    if [ ! -f "$file_path" ]; then
      continue
    fi
    file_value="$(tr -d '\r\n' < "$file_path")"
    if [ -n "$file_value" ]; then
      export "${var_name}=${file_value}"
      return 0
    fi
  done
  return 1
}

_load_key_if_missing "API_KEY" ".sglang_api_key" || {
  echo "Missing API_KEY and .sglang_api_key for professor E2E." >&2
  return 1
}

_load_key_if_missing "DASHSCOPE_API_KEY" ".dashscope_api_key" || true
_load_key_if_missing "SERPER_API_KEY" ".serper_api_key" || true

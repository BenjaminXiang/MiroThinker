#!/usr/bin/env bash

set -euo pipefail

echo "=== AGENT OS STRUCTURAL VALIDATION v2 ==="

FAIL=0

check_contains() {
  FILE="$1"
  PATTERN="$2"

  if [ ! -f "$FILE" ]; then
    echo "❌ MISSING FILE: $FILE"
    FAIL=1
    return
  fi

  if grep -qi "$PATTERN" "$FILE"; then
    echo "✅ OK: $FILE contains (case-insensitive match) $PATTERN"
  else
    echo "❌ MISSING SEMANTIC PATTERN: $FILE -> $PATTERN"
    FAIL=1
  fi
}

check_any_of() {
  FILE="$1"
  shift
  PATTERNS="$@"

  FOUND=0

  for p in $PATTERNS; do
    if grep -qi "$p" "$FILE"; then
      FOUND=1
    fi
  done

  if [ $FOUND -eq 1 ]; then
    echo "✅ OK: $FILE contains one of [$PATTERNS]"
  else
    echo "❌ NONE MATCH in $FILE -> [$PATTERNS]"
    FAIL=1
  fi
}

echo ""
echo "== 1. OPEN SPEC CHECK =="

check_contains "CLAUDE.md" "openSpec"
check_contains "AGENTS.md" "ready slice"

echo ""
echo "== 2. EXECUTION STOP SEMANTICS =="

check_any_of "AGENTS.md" "STOP" "stop" "halt" "abort" "terminate"

echo ""
echo "== 3. SLICE MODEL CHECK =="

check_contains "AGENTS.md" "Specified"
check_contains "AGENTS.md" "Ready"
check_contains "AGENTS.md" "Candidate"

echo ""
echo "== 4. TEST DESIGN SAFETY =="

check_contains ".claude/skills/test-design-review/SKILL.md" "public interfaces"
check_contains ".claude/skills/test-design-review/SKILL.md" "not executing TDD"

echo ""
echo "== RESULT =="

if [ $FAIL -eq 0 ]; then
  echo "🎉 PASS: Agent OS structurally valid"
else
  echo "💥 FAIL: Structural issues detected"
  exit 1
fi

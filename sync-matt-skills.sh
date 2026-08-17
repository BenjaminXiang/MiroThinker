mkdir -p scripts

cat > scripts/sync-matt-skills.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail

SRC="vendor/mattpocock-skills"

if [ ! -d "$SRC" ]; then
  echo "Missing $SRC. Run: git submodule update --init --recursive"
  exit 1
fi

SELECTED_SKILLS=(
  "skills/engineering/setup-matt-pocock-skills"
  "skills/engineering/grill-with-docs"
  "skills/productivity/grilling"
  "skills/engineering/domain-modeling"
  "skills/engineering/codebase-design"
  "skills/productivity/handoff"
)

mkdir -p .claude/skills .agents/skills

for path in "${SELECTED_SKILLS[@]}"; do
  name="$(basename "$path")"

  if [ ! -d "$SRC/$path" ]; then
    echo "Missing upstream skill: $SRC/$path"
    exit 1
  fi

  rm -rf ".claude/skills/$name"
  rm -rf ".agents/skills/$name"

  cp -R "$SRC/$path" ".claude/skills/$name"
  cp -R "$SRC/$path" ".agents/skills/$name"
done

echo "Synced selected Matt Pocock skills into .claude/skills and .agents/skills"
SH

chmod +x scripts/sync-matt-skills.sh
./scripts/sync-matt-skills.sh
#!/usr/bin/env bash
set -euo pipefail

# SkillOpt-Sleep (https://github.com/microsoft/SkillOpt) を cron/launchd から
# 安全に呼び出すためのラッパー。詳しい使い方は ../SKILLOPT-SLEEP.md 参照。
#
# crontab の例 (crontab -e):
#   0 2 * * * SKILLOPT_BACKEND=claude /path/to/skills/scripts/skillopt-sleep-cron.sh >> /path/to/skills/.skillopt-sleep/cron-claude.log 2>&1
#   0 3 * * * SKILLOPT_BACKEND=codex  /path/to/skills/scripts/skillopt-sleep-cron.sh >> /path/to/skills/.skillopt-sleep/cron-codex.log 2>&1
#
# cron/launchd は最小限の環境変数しか引き継がないため PATH を明示する。
export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SKILLOPT_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND="${SKILLOPT_BACKEND:?SKILLOPT_BACKEND (claude|codex|cursor|...) を指定してください}"
SOURCE="${SKILLOPT_SOURCE:-$BACKEND}"
AUTO_ADOPT="${SKILLOPT_AUTO_ADOPT:-false}"

if ! command -v skillopt-sleep >/dev/null 2>&1; then
  echo "skillopt-sleep が見つかりません。'pip install skillopt' を実行してください。" >&2
  exit 1
fi

echo "=== $(date -Iseconds) skillopt-sleep run (project=$PROJECT_DIR source=$SOURCE backend=$BACKEND) ==="

skillopt-sleep run --project "$PROJECT_DIR" --source "$SOURCE" --backend "$BACKEND"

if [ "$AUTO_ADOPT" = "true" ]; then
  echo "SKILLOPT_AUTO_ADOPT=true のため、ステージ済み提案を自動適用します。"
  skillopt-sleep adopt --project "$PROJECT_DIR"
else
  echo "提案はステージングのみです。'skillopt-sleep status --project \"$PROJECT_DIR\"' で内容を確認し、"
  echo "問題なければ 'skillopt-sleep adopt --project \"$PROJECT_DIR\"' を手動で実行してください。"
fi

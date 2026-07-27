# skills

Claude Code と Codex で共用するエージェントスキルの正本リポジトリ。
日々の利用ログをもとに、[SkillOpt-Sleep](https://github.com/microsoft/SkillOpt) でスキルを定期的に見直す。

## このリポジトリに置くもの / 置かないもの

| 置く | 置かない |
|---|---|
| `skills/` — スキル本体(`SKILL.md` とその補助ファイル) | SkillOpt 本体のソース |
| `evals/` — スキルごとの回帰タスク | 実行ログ・ステージング状態(`.skillopt-sleep/`) |
| `scripts/` — cron ラッパーなどの運用スクリプト | 生成物・ビルド成果物 |
| `requirements.txt` — 依存のバージョン固定 | APIキー・認証情報 |

資産はスキルそのものであって、最適化ツールではない。SkillOpt は交換可能な道具として
外部参照にとどめる(→ [依存の扱い](#依存の扱い))。

## 収録スキル

正本は `skills/` に置く。現在は次の75個を収録している。

- `co-create-plan` — Claude CodeとCodexが制約付きラウンドで共同計画を作る
- `complexity-aware-execution` — 調査と検証の深さをタスクの難易度・リスクに合わせる
- `create-project-map` — リポジトリ構造を走査し、対話的なHTMLマップを生成する
- `writing-style` — 正確さを保ちながら日本語の認知リズムを整える
- `handoff` — 会話の目的・前提・未解決事項を保って新しいタスクへ移す
- `open-pull-request` — 検証済みブランチをレビュー結果を根拠にPRとして公開する
- `review-implementation-html` — 実装差分を調査し、根拠付きHTMLレビューを生成する
- [phuryn/pm-skills](https://github.com/phuryn/pm-skills) 2.1.0の68 Skill

PM SkillsはMITライセンスに基づいてSkill本体だけを収録した。Claude固有のコマンドと
プラグイン定義は含めていない。出典とライセンスは
`third_party/pm-skills/source.json`、`third_party/pm-skills/LICENSE`、および
`third_party/pm-skills/SHA256SUMS` に固定している。

## Codex / Claude Codeから使う

`SKILL.md` の基本形式とSkill本文は両者で共用する。ただし、実行時の引数展開や上流の
slash commandにはホスト差がある。`$ARGUMENTS` と欠落した上流コマンドの扱いは
[ホスト互換性契約](docs/host-compatibility.md)に明記しており、完全なruntime parityは主張しない。

| ツール | プロジェクト用 | 個人用 |
|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.agents/skills/` | `~/.agents/skills/` |

このリポジトリを開いて作業する場合、Codexは `AGENTS.md`、Claude Codeは `CLAUDE.md` から
`skills/` を正本として参照する。別のプロジェクトでも自動発見させる場合は、同期スクリプトを使う。

Windows PowerShell:

```powershell
# 個人用としてCodexとClaude Codeの両方へ同期
powershell -ExecutionPolicy Bypass -File .\scripts\install-skills.ps1 -Agent both -Scope user

# 特定プロジェクトへ同期
powershell -ExecutionPolicy Bypass -File .\scripts\install-skills.ps1 `
  -Agent both -Scope project -ProjectRoot C:\path\to\project

# 既存の管理対象Skillをディレクトリ単位で明示的に置換
powershell -ExecutionPolicy Bypass -File .\scripts\install-skills.ps1 `
  -Agent both -Scope project -ProjectRoot C:\path\to\project -Force
```

macOS / Linux:

```bash
# 個人用としてCodexとClaude Codeの両方へ同期
./scripts/install-skills.sh --agent both --scope user

# 特定プロジェクトへ同期
./scripts/install-skills.sh --agent both --scope project --project-root /path/to/project

# 既存の管理対象Skillをディレクトリ単位で明示的に置換
./scripts/install-skills.sh --agent both --scope project --project-root /path/to/project --force
```

同期先は配布物であり、編集元ではない。改善するときは `skills/<skill-name>/SKILL.md` を変更し、
検証後にもう一度同期する。既存の管理対象ディレクトリが1つでもあれば、同期は既定で
競合として書き込み前に停止する。`-Force` / `--force`（`--replace`も同義）は全対象を
ステージして検証した後、ディレクトリ単位で置換する。失敗時は触れた全対象をロールバックする。
各同期先の `.third-party-notices/` には、完全なMITライセンス、出典情報、SHA-256
manifest、ホスト互換性文書も配置される。

```bash
python -m pip install -r requirements-validation.txt
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

本文をホスト別にforkする前に、互換性レイヤーと評価で差を吸収する。SkillOpt の論文では、
Codex で訓練したスキルを Claude Code に移した際に 22.1 → 81.8 (+59.7) と、
直接訓練した場合(80.4)と同等の性能が出ている。分岐は「評価で有意差が出てから」でよい。

`handoff` は、Codexでタスク管理機能を利用できる場合は新しいタスクを直接作成する。
ChatGPTなど同等の機能がない環境では、コピー可能な引き継ぎの文書をフォールバックする。
ChatGPTとCodexのSkillは自動同期されないため、それぞれ個別にインストールする。

## SkillOpt による定期改善

### SkillOpt とは

Microsoft Research が公開した、**モデルの重みを変えずにスキル文書そのものを最適化する**
フレームワーク(MIT ライセンス)。Markdown のスキル文書を訓練可能なパラメータとして扱い、
以下の 4 ステップを回す。

```
Rollout(現行スキルでタスク実行)
  → Reflect(軌跡を分析し成功/失敗パターンを抽出)
  → Edit(追加・削除・置換の限定的な編集を提案)
  → Validate(保留セットで既存版を厳密に上回った編集のみ採用)
```

6 ベンチマーク × 7 モデル × 3 実行モード = 52 通りの評価すべてで最良またはタイ最良。
GPT-5.5 の直接チャットでは 6 ベンチ平均 58.8 → 82.3 (+23.5pt)。
最終的なスキルファイルはトークン数中央値 約920 と小さく、採用される編集も平均 1〜4 個にとどまる。

本リポジトリで使うのは、付属の **SkillOpt-Sleep**(デプロイ運用向けプレビュー)。
ベンチマークではなく、実際の Claude Code / Codex のセッションログからタスクを採掘して
改善案を出す。

### 効果が出る条件(最重要)

公式の実験結果([RESULTS.md](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/RESULTS.md))は、
効果の範囲を明確に限定している。

- **効く**: recurring tasks with a **checkable correctness signal** and real headroom
- **効かない**: saturated tasks on strong models, or **noisy tasks with a weak learning signal** — within run-to-run noise

つまり **正解を機械判定できないスキルは、かけても「改善」されず「変化」するだけ**。
スキルを追加したら、まずこの軸で仕分ける。

| SkillOpt 向き(機械判定できる) | 手動で改善すべき(判定困難) |
|---|---|
| 生成した xlsx / pptx が正しく開くか | 文章が読みやすいか |
| スクリプトが lint を通るか | デザインが良いか |
| テストが通るか | レビュー指摘が的確か |
| 抽出データがスキーマに合致するか | 説明が分かりやすいか |

右側のスキルを自動改善パイプラインに載せるのは、API 費用と時間の無駄になる。

### 依存の扱い

**SkillOpt はリポジトリに取り込まず、バージョンを固定して参照する。**

```bash
pip install -r requirements.txt   # skillopt==0.2.0
```

理由:

- 改造しないものを vendor しても、上流への追従保守を自分で背負うだけ
- Alpha ステータスで活発に更新中(0.1.0 → 0.2.0 が 1 ヶ月)。取り込んだ時点で陳腐化が始まる
- 「あのときのバージョンで動かしたい」は `requirements.txt` の固定で足りる

0.2.0 に未収録の機能(Cursor 対応、`--preferences`、Sleep ハンドオフ、OpenAI 互換エンドポイント)が
必要になったら、main からコミットハッシュを固定してソースインストールする。
**git submodule は使わない** — ソースを改造しないなら得られるものは同じで、取り回しだけ面倒になる。

fork が要るのはオプティマイザ本体を改造するときだけだが、SkillOpt は新しいバックエンド・
ベンチマーク・実行環境を拡張として追加できる設計(`docs/guide/`)なので、実際には拡張を書けば済む。

Claude Code 内で `/skillopt-sleep` を、Codex でスキルとして呼び出したい場合はプラグインが必要で、
これは pip パッケージではなくリポジトリ側にある。その場合も **`~/src/SkillOpt` のように
このリポジトリの外へ** クローンすること(git の入れ子を避ける)。cron 自動実行だけなら不要。

### セットアップ

手順は **[SKILLOPT-SLEEP.md](SKILLOPT-SLEEP.md)** を参照。
インストール → mock での無料ドライラン → Claude Code / Codex それぞれの確認 →
提案のレビューと適用 → ローカル cron 登録、の順。

## 運用ルール

1. **検証ゲートを切らない。** ゲート無効時に 0.554 → 0.026 (−52.8pt) の崩壊が観測されている。
   有効時は 0.570 → 0.570 で安定。
2. **1 回の実行結果を信じない。** 同一条件でシード 42/43/44 が −1.9 / +3.6 / +4.7(平均 +2.1)。
   単発の A/B 比較は無意味。最低 3 回、差が 1.5pt 未満はノイズとして扱う。
3. **`adopt` は手動。** 提案はステージングまでで止め、内容を目視してから適用する。
4. **スキルを肥大化させない。** 自動改善は失敗のたびに注意書きを足しがち。
   同義の指示が増えていないか定期的に確認し、長い説明は `references/` へ、
   決定的な処理は `scripts/` へ逃がす。
5. **機密プロジェクトで回さない。** 実バックエンドはセッションから抽出した概要・タスクを
   プロバイダに送信する。マスキングは完全ではなく、検証ゲートは公式に
   「セキュリティ境界ではない」と明記されている。

## 参考

- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)
- [SkillOpt-Sleep README](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/README.md) / [RESULTS.md](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/RESULTS.md)
- [Codex Session Handoff Skill — tegnike](https://gist.github.com/tegnike/09dbb98711d8b91e66de21611f5b88ff) — [MITライセンス](third_party/handoff-gist/LICENSE) / [出典情報](third_party/handoff-gist/source.json)
- [ホスト互換性契約](docs/host-compatibility.md) / [機械可読contract](compatibility/host-contract.json)
- [CLI リファレンス](https://github.com/microsoft/SkillOpt/blob/main/docs/reference/cli.md)
- [SkillOpt: Agent skills as trainable parameters — Microsoft Research](https://www.microsoft.com/en-us/research/blog/skillopt-agent-skills-as-trainable-parameters/)

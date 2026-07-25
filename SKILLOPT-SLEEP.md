# SkillOpt-Sleep でスキルを定期的に自己改善する(デスクトップ + ローカルcron)

このリポジトリのスキル(`SKILL.md` など)を、日常的な Claude Code / Codex の利用ログから
定期的に見直し、改善案を出す仕組みを、**あなたのデスクトップPC上のローカルcron**で動かすための
手順です。使うツールは Microsoft Research の [SkillOpt](https://github.com/microsoft/SkillOpt) 付属の
「SkillOpt-Sleep」(本番運用向けプレビューツール)です。

> **実行はすべてあなたのPC上で行います。** このリポジトリのクラウドセッション側では実行できません。
> 以下はご自身のターミナルで実行してください。

## 前提条件

- Python 3.10 以上
- Claude Code CLI がインストール済み・ログイン済み
- Codex CLI がインストール済み・ログイン済み(Codexのセッションも対象にする場合)
- macOS / Linux(cron または launchd が使える環境。Windowsはタスクスケジューラで代用)

## 1. インストール

SkillOpt はこのリポジトリに取り込まず、バージョンを固定して参照します(方針の詳細は
[README の「依存の扱い」](README.md#依存の扱い)を参照)。

```bash
pip install -r requirements.txt   # skillopt==0.2.0
```

これで `skillopt-sleep` コマンドが使えるようになります。

0.2.0 (2026-07-02) で SkillOpt-Sleep 本体と Claude / Codex バックエンドが導入されているため、
ローカル cron でのスキル定期改善はこのバージョンで完結します。Cursor 対応、`--preferences`、
Sleep ハンドオフ、OpenAI 互換エンドポイントは 0.2.0 に未収録で、必要になったら main から
コミットハッシュを固定してソースインストールしてください。

Claude Code / Codex のエージェント内から `/skillopt-sleep` のように直接呼び出したい場合は、
本体リポジトリのプラグインも追加でインストールできます(任意。cronでの自動実行にはCLIだけで十分です):

```bash
git clone https://github.com/microsoft/SkillOpt.git ~/src/SkillOpt
cd ~/src/SkillOpt

# Claude Code
/plugin marketplace add ./plugins/claude-code   # Claude Code内で実行 → 以後 /skillopt-sleep

# Codex
bash plugins/codex/install.sh                   # 以後 skillopt-sleep スキルとして呼び出し可能
```

## 2. 無料でドライラン確認(mockバックエンド)

課金なしで「収集 → マイニング」までの動きだけ確認できます:

```bash
skillopt-sleep dry-run --project /path/to/this/repo --backend mock
```

`mock` はプロバイダへの呼び出しを一切行いません。

## 3. Claude Code / Codex それぞれでドライラン

`--source`(どちらのセッションログを読むか: `claude|codex|cursor|auto`)と
`--backend`(どちらのCLIで再実行・反省するか: `mock|claude|codex|copilot|cursor|handoff|azure_openai`)
を指定します。**両方使いたい場合は2回に分けて実行**します。

```bash
# Claude Codeのセッションログを対象に、claude CLIで再実行・反省
skillopt-sleep dry-run --project /path/to/this/repo --source claude --backend claude

# Codexのセッションログを対象に、codex CLIで再実行・反省
skillopt-sleep dry-run --project /path/to/this/repo --source codex --backend codex
```

`--backend claude` / `--backend codex` は、ローカルにログイン済みの `claude` / `codex` CLI を
そのまま利用する方式です。追加のAPIキー発行なしで動く設計ですが、実際の課金・レート制限の扱いは
CLI側のプラン次第なので、必ず `dry-run` で先に挙動を確認してください。

`--lookback-hours N` で収集対象の期間を調整できます(初期値は72時間、`0`で全履歴)。
1つのスキルだけを対象にしたい場合は `--target-skill-path` でファイルを指定できます。

## 4. 提案の確認・適用

`dry-run` を `run` に変えると、改善案が実際にステージングされます:

```bash
skillopt-sleep run --project /path/to/this/repo --source claude --backend claude
skillopt-sleep status --project /path/to/this/repo     # ステージ済み提案を確認
skillopt-sleep adopt  --project /path/to/this/repo     # 内容を確認した上で適用
```

`adopt` を明示的に実行するまで適用されません(検証ゲートを通った提案でも、まずレビュー待ちで
ステージされるだけです)。**最初の数回はauto-adoptにせず、必ず人間の目でレビューしてから
`adopt` することを強く推奨します。**

## 5. ローカルcronへの登録

`skillopt-sleep schedule` という組み込みコマンドもありますが、1プロジェクトにつき
`project / backend / time / auto-adopt` を1エントリしか保持できないため、**Claude Code分と
Codex分を両方定期実行したい場合は、素のcronに2行登録するほうが確実**です。

このリポジトリの `scripts/skillopt-sleep-cron.sh` を使います。`crontab -e` で以下を追記してください
(パスは実際のクローン先に、時刻は必要に応じて変更・調整してください。2つの時刻をずらしているのは
同時実行によるAPI/リソース競合を避けるためです):

```cron
# Claude Codeのセッションを深夜2時に確認
0 2 * * * SKILLOPT_BACKEND=claude /path/to/this/repo/scripts/skillopt-sleep-cron.sh >> /path/to/this/repo/.skillopt-sleep/cron-claude.log 2>&1

# Codexのセッションを深夜3時に確認
0 3 * * * SKILLOPT_BACKEND=codex /path/to/this/repo/scripts/skillopt-sleep-cron.sh >> /path/to/this/repo/.skillopt-sleep/cron-codex.log 2>&1
```

自動適用したい場合のみ、各行に `SKILLOPT_AUTO_ADOPT=true` を追加してください(デフォルトは
ステージングまでで止まり、`adopt` は手動です)。

cronは最小限の環境変数しか引き継がないため、`claude` / `codex` CLIの認証情報がcron実行時にも
有効であることを事前に確認してください。

macOSでcronの代わりに launchd を使いたい場合は、同じスクリプトを `~/Library/LaunchAgents/*.plist`
から呼び出す形でも動きます。

## 6. 注意事項(公式ドキュメントより)

- 実バックエンド(`claude` / `codex` 等)は、収集したセッションから抽出した概要・タスクをプロバイダに
  送信します。送信内容の機密情報マスキングは完全ではないため、機密プロジェクトで動かす前に
  トランスクリプトの内容とプロバイダのポリシーを確認してください。
- 検証ゲートは性能の後退を防ぐための仕組みであり、「セキュリティ境界ではない」と公式ドキュメントに
  明記されています。
- 現在プレビュー版であり、インターフェースやデフォルト値は変更される可能性があります。最新の
  オプションは `skillopt-sleep --help` / `skillopt-sleep run --help` / `skillopt-sleep schedule --help`
  で必ず確認してください(本ドキュメントの `schedule` に関する記述は公式リファレンスに詳細な例が
  掲載されていなかったため、CLIの挙動を優先してください)。

## 参考

- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)
- [SkillOpt-Sleep README](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/README.md)
- [CLI リファレンス](https://github.com/microsoft/SkillOpt/blob/main/docs/reference/cli.md)

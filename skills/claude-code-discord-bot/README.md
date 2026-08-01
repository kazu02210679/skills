# Claude Code Discord Bot

自分のマシンで動くClaude CodeにDiscordを front end として被せるためのSkillです。Discordから指示を出し、完了・待機を通知させ、tool実行の可否をスマホから承認できる bridge process の作り方と、その信頼境界を定義します。

## 使う場面

- Claude Codeを Discord bot 化したい、スマホから操作したい
- 長時間走らせているClaude Codeの完了・入力待ちをDiscordで受け取りたい
- Claude Codeが危険なtoolを使う前に、人間の承認をDiscord経由で挟みたい

## 2つのsession originを分ける

bridgeが起こしたsessionと、自分でterminalから起こしたsessionでは配線が違います。configもこの単位で分かれています。

| flow | `bridge_sessions` (agent-sdk) | `bridge_sessions` (cli) | `terminal_sessions` |
|---|---|---|---|
| 指示 | `query()` | `claude -p` | 対象外 |
| 通知 | SDKのmessage stream | stream-json events | `Stop` / `Notification` hook |
| 承認 | `canUseTool` callback | **なし** | `PermissionRequest` hook |

**`claude -p` では `PermissionRequest` hook が発火しません**（実測: `PreToolUse` は毎回発火、`PermissionRequest` は0回）。したがって**このSkillのCLI transportは承認経路を実装しません**。Claude Code側に経路が皆無という意味ではありません。`PreToolUse` の `defer` を使う設計や、MCP の permission-prompt transport は別設計として構築可能です（前者は全tool callが飛んでくる量を受け入れる必要あり）。Discordのthread 1本がClaude Code session 1本に対応し、`session_id`を保存して次のturnで`resume`に渡します。

## 信頼境界

この bridge は実質「chat UIつきのremote code execution」です。機能を書く前に境界を固定します。

- guild ID・channel ID・operator user IDのallowlistを必須にする（空を許さない）
- `setting_sources` を明示する。省略すると user/project/local の設定がすべて読まれ、既存のruleやhookが承認経路より先にtoolを許可しうる
- token類は環境変数のみ。設定fileに直接書かない
- hook endpointはloopbackにbindし、shared secretを要求する
- 承認はfail closed。Claude Codeは無応答・遅延・失敗を「拒否」とは扱わないので、bridge側が明示的にdenyを返す

`bypassPermissions` と `dontAsk` はpermission promptに到達しないため承認flowと併用できません。`acceptEdits` / `auto` / `plan` は一部だけ素通りするので `approval.coverage: "partial"` の明示が要ります。validatorが弾きます。

`sandbox.enabled` だけでは姿勢が暗黙のままです。`allowUnsandboxedCommands` の既定は true（`dangerouslyDisableSandbox` でコマンド側がsandboxを抜けられる）。`failIfUnavailable` の既定は**層によって違い**、SDK の `Options.sandbox` 経由なら true（sandboxを起動できなければ `query()` がエラー終了）、Claude Code settings 側なら false（警告のみで非sandbox実行）。どちらも固定を要求します — 既定が危険だからではなく、containment の契約をconfig自身に書かせるためです。

**`workspace_root` はsandboxではありません。** 起動可能なproject pathを制限するinput validationであって、Claude Codeは作業ディレクトリ外を読めますし、Bashは絶対pathに届きます。実際の隔離が要るなら SDK の `sandbox` 設定・コンテナ・VMを使ってください。

## 実装資材

- `references/bridge-contract.md`: 設定schema、thread↔session対応、hookのpayloadと応答形式
- `references/discord-app-setup.md`: Discord Developer Portalの手順、intent・権限、platform上限
- `references/can-use-tool-sample.mts`: CIで型検査される `canUseTool` の実サンプル
- `references/sandbox-conversion-sample.mts`: config→`Options.sandbox` 変換をCIでコンパイル検証
- `scripts/check_sdk_contract.py`: 文書化した契約と実際のSDK・CLIの差分検出
- `scripts/validate_bridge_config.py`: `discord-bridge.json`の信頼境界検証

```bash
python scripts/check_sdk_contract.py \
  --sdk-types node_modules/@anthropic-ai/claude-agent-sdk/sdk.d.ts --cli claude
python scripts/validate_bridge_config.py <project>/discord-bridge.json
```

契約はrelease間で変わります。`canUseTool`のsignatureも`PermissionRequest`のpayloadも実際に変わった実績があるので、実装前に必ずdrift checkを通してください。

## 制約

個人が自分のClaude Codeに繋ぐための構成です。第三者に共有させるserviceには転用しません（Agent SDKの規約上、claude.aiのloginやrate limitを第三者に提供することは認められていません）。

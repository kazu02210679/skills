# Claude Code Discord Bot

自分のマシンで動くClaude CodeにDiscordを front end として被せるためのSkillです。Discordから指示を出し、完了・待機を通知させ、tool実行の可否をスマホから承認できる bridge process の作り方と、その信頼境界を定義します。

## 使う場面

- Claude Codeを Discord bot 化したい、スマホから操作したい
- 長時間走らせているClaude Codeの完了・入力待ちをDiscordで受け取りたい
- Claude Codeが危険なtoolを使う前に、人間の承認をDiscord経由で挟みたい

## 3つのflowと経路

bridgeが起こしたsessionと、自分でterminalから起こしたsessionでは配線が変わります。

| flow | bridge起点のsession | terminal起点のsession |
|---|---|---|
| 指示 | Agent SDK `query()` / `claude -p` | 対象外 |
| 通知 | SDKのmessage stream | `Stop` / `Notification` hook (`http`) |
| 承認 | `canUseTool` callback | `PermissionRequest` hook (`http`) |

Discordのthread 1本がClaude Code session 1本に対応します。`session_id`を保存し、次のturnで`resume`に渡します。

## 信頼境界

この bridge は実質「chat UIつきのremote code execution」です。機能を書く前に境界を固定します。

- guild ID・channel ID・operator user IDのallowlistを必須にする（空を許さない）
- sessionは`workspace_root`配下に限定する
- token類は環境変数のみ。設定fileに直接書かない
- 承認endpointはloopbackにbindし、shared secretを要求する
- 承認はfail closed。無回答・遅延・不正応答はすべてdeny

`bypassPermissions`はpermission eventそのものを消すため、承認flowとは併用できません。validatorが弾きます。

## 実装資材

- `references/bridge-contract.md`: 設定schema、thread↔session対応、hookのpayloadと応答形式
- `references/discord-app-setup.md`: Discord Developer Portalの手順、intent・権限、platform上限
- `scripts/validate_bridge_config.py`: `discord-bridge.json`の信頼境界検証

```bash
python scripts/validate_bridge_config.py <project>/discord-bridge.json
```

## 制約

個人が自分のClaude Codeに繋ぐための構成です。第三者に共有させるserviceには転用しません（Agent SDKの規約上、claude.aiのloginやrate limitを第三者に提供することは認められていません）。

# Host compatibility

`SKILL.md`の基本形式はClaude CodeとCodexで共有できますが、実行機能は同一ではありません。このrepositoryはSkill本文を正本として共有し、完全なruntime parityは主張しません。

## 共通部分

- `skills/<name>/SKILL.md` をAgent向け実行仕様として扱う。
- `scripts/`、`references/`、`assets/` はSkill directoryからの相対pathで参照する。
- repository内で作業するときは、Codexは `AGENTS.md`、Claude Codeは `CLAUDE.md` を読む。
- install先は配布物であり、編集元にしない。

## 呼び出し引数

Claude CodeはSkill invocationの `$ARGUMENTS` をnativeに置換します。Codexでは同じtext置換を前提にせず、明示されたSkill invocationまたは現在のuser requestを入力として解釈します。

この違いをinstallerが書き換えることはありません。textual substitutionが不可欠なSkillは、必要な入力を現在のrequestから解決できない場合に確認します。

## `codex-orchestration`

`codex-orchestration` の主用途はClaude CodeからCodex CLIへ実装を委譲することです。

- Claude Code: natural-language invocationからworkflowを実行できる。
- Codex: workflowの保守・review目的では使えるが、Codexから別のCodex sessionへ再帰的に委譲しない。
- 旧 `Codex-plugin-Claude-Code` のslash commandsはcanonical interfaceではない。`SKILL.md` と同梱scriptを直接使う。
- wrapper pathはplugin rootではなく、Skill directoryを基準に解決する。

## Skillごとの差

`agents/openai.yaml` はCodexのUI metadataです。Claude Codeはこのfileを必要としません。逆にClaude Code固有のplugin manifestやslash commandを、portable Skillの必須条件にはしません。

ホスト差が実際の評価結果へ影響した場合だけ、Skill本文の分岐、補助script、またはhost-specific packageを追加します。推測だけで本文をforkしません。

## Documentation basis

- [Claude Code Skills](https://code.claude.com/docs/en/skills)
- [OpenAI Codex Skill building](https://learn.chatgpt.com/docs/build-skills)

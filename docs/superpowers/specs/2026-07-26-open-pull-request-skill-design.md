# open-pull-request Skill設計

## 目的

検証済みのローカルブランチを、根拠を伴うPull Requestとして公開する `open-pull-request` Skillを作る。

実装を完成させる作業と、完成物を外部へ公開する作業は責務が異なる。実装側のSkillが公開まで担うと、
受け入れ判定を終えた状態を公開側が書き換え、PRの内容と判定済みの状態がずれる。本Skillは
公開だけを担い、製品コードとGit履歴を変更しない。

上流には次の2つのSkillを想定するが、いずれにも依存しない。存在すれば成果物を利用し、
なければ単独で動作する。

- `codex-orchestration`（`Codex-plugin-Claude-Code`）— タスク単位のcommitまでを担い、
  「pushとPR作成は別Skillの仕事」と明記して終了する。
- `review-implementation-html` — 同じ `base..head` をレビューし、`review-data.json` を出力する。

## 成功条件

- commit済みのローカルブランチから、承認を得たうえでPRを作成できる。
- 製品コードを変更せず、commitの作成・修正・履歴の書き換えを行わない。
- 実行していない検証を「実行済み」と記載しない。
- 上流の成果物があればPR本文の根拠に用い、なければ自前で検証して構成する。
- レビュー済みでない差分が、レビュー済みとしてPRに入らない。
- 承認前にネットワークへ到達しない。
- CodexとClaude Codeで同じ `SKILL.md` を利用できる。

## 採用方式

### 汎用中核 + 上流成果物の疎結合参照

単一のSkillとして汎用の公開手順を定め、上流成果物は「あれば利用する」任意経路として扱う。

上流Skillの実装ではなく、確定した成果物とGit履歴を一次情報とする。参照先を成果物の
スキーマに限定することで、上流Skillが別ブランチにあっても、未導入でも壊れない。

Codex専用Skillとする案は採用しない。本リポジトリはClaude CodeとCodexで共用する可搬Skillの
正本であり、特定プラグインの実行フロー専用の手順はプラグイン側に属する。

汎用Skillとレビュー連携Skillを最初から分割する案も採用しない。まず1つを作り、内部で
公開処理を独立した節として分離する。他のワークフローから必要になった時点で抽出すればよい。

## Skill構成

```text
skills/open-pull-request/
├── SKILL.md
└── agents/
    └── openai.yaml

evals/open-pull-request/
├── README.md
├── criteria.yaml
├── run.py
└── inputs/
    ├── case-1.md
    ├── case-2.md
    └── case-3.md
```

補助スクリプトは作らない。判断の大半は状態の読み取りと停止判断であり、固定スクリプトよりも
Skill内の分岐指示が適している。

`scripts/validate-skills.py` はSkill数をハードコードするため、同じ変更で次を更新する。

- `CUSTOM_SKILLS` へ `open-pull-request` を追加する。
- 総数の期待値を71から72へ変更する。
- `README.md` の収録数を「次の71個」から「次の72個」へ変更する。

`CUSTOM_SKILLS` への追加を怠ると、新Skillがpm-skills扱いとなり `SHA256SUMS` 検査で失敗する。

## 入力契約

本Skillは完成済みのローカルブランチだけを受け取る。次を満たさない場合はPRを作らず、
理由を報告して停止する。

| 前提 | 満たさない場合 |
|---|---|
| Gitリポジトリ内で、`gh` が認証済み | 停止し、必要な認証手順を報告する |
| HEADがデフォルトブランチではない | 停止する。ブランチを作らない |
| ワークツリーがclean | 停止する。commitしない |
| baseに対し1つ以上commitが先行 | 停止する。空のPRを作らない |

ブランチ作成、変更のcommit、テスト失敗の修正は、いずれも本Skillの責務ではない。

## 起動条件

次の意図をfrontmatterの `description` に含める。`<` と `>` は検証で禁止されるため使わない。

- 完成したブランチをPull Requestとして公開する。
- 作業をpushしてPRを開く。
- レビュー済みの変更をPRにまとめる。
- 「PRを作って」「プルリクを出して」などの自然言語。

実装が未完了の場合、未commitの変更がある場合、デフォルトブランチ上にいる場合は起動しない。

## 上流成果物の参照方針

| 参照する | 参照しない |
|---|---|
| `.codex-instructions/<plan>/packet.md` | `codex_lib.sh` をsourceすること |
| `Codex-Plan:` / `Codex-Task:` トレーラ | `codex_run.sh` の内部変数 |
| `docs/reviews/<slug>/review-data.json` | `.codex-runs/` の内部構造 |
| commit履歴と確定したGit状態 | `attempt-N` の存在を前提とした処理 |

`.codex-runs/` は一回の実行の局所的な証跡であり、構造が変わりうる。確定したGit履歴と
plan/reviewディレクトリを一次情報とする。

## PR本文データモデル

PR本文は次の順序を基本とする。該当情報がない節は省略できる。

```markdown
## Summary
## Changes
## Verification
## Out of scope
## Notes
```

| 節 | 上流成果物がある場合 | ない場合 |
|---|---|---|
| `Summary` | `review-data.json` の `summary.headline` と `summary.overview`、または `packet.md` の要求 | commit履歴とdiffから構成 |
| `Changes` | `intentGroups[]` を `risk` 降順で列挙し、`title` と `summary` を用いる | commit件名を列挙する |
| `Verification` | `verification[]` の `name` / `status` / `details` をそのまま転記 | 自ら実行したコマンドと実出力 |
| `Out of scope` | `packet.md` のout-of-scope | 省略する |
| `Notes` | `status` が `open` の `findings[]` をseverity付きで、`coverage.gaps` とともに記載 | 未検証事項と手動確認事項 |

`intentGroups` は振る舞いの意図でグループ化されリスク順に並ぶため、commit履歴から機械的に
構成するよりPR本文として適切である。

`verification[]` の `passed` / `failed` / `not-run` / `blocked` は加工せずそのまま転記する。
`not-run` と `blocked` を `passed` へ昇格させない。

PR本文の言語は、対象リポジトリの既存のPRとcommitに合わせる。

## 実行フロー

### 1. 公開の文脈を確定する

リポジトリ、head、base、remoteを特定する。入力契約を検査し、満たさなければ停止する。
同じheadの既存PRを検索し、あれば更新するか中止するかをユーザーへ提示する。
forkとoriginのどちらへpushするかを確定する。

### 2. ブランチの内容を再構成する

`git log <base>..HEAD` と `git diff --stat <base>...HEAD` を読む。

上流成果物を探す。`review-data.json` があれば、その `meta.base` と `meta.head` が
これから公開する `base` / `head` と一致するかを検証する。一致しない場合は停止する。

headがレビュー後に進んでいる場合、レビューされていない差分がPRに入る。追加されたcommit数を
報告し、再レビューへ戻す。

`packet.md` と `Codex-Task:` トレーラがあれば、タスク単位の変更内容として利用する。

### 3. ブランチを自分で検証する

`review-data.json` の `verification[]` があればそれを根拠とする。

ない場合は、リポジトリのテストとlintのコマンドを検出して実行し、実際の出力を記録する。
検出できない、または実行できない場合は推測で補わず、`not-run` として理由とともに記録する。

### 4. 安全性を確認する

diffとPR本文の双方を検査する。

- 秘密情報、認証情報、トークン、秘密鍵、Cookie、パスワードを削除する。
- `.env`、鍵ファイル、大きなバイナリ、ローカル成果物の混入を検出する。
- `.codex-runs/` などの実行証跡が含まれていないかを確認する。
- `docs/reviews/` をPRに含めるかをユーザーへ確認する。HTMLレポートはローカル成果物であり、
  既定では公開しない。

ファイル名が無害に見えても、疑わしい変更は内容を確認してから進む。

### 5. Pull Requestを構成する

PR本文データモデルに従って、タイトルと本文を作る。タイトルはブランチの目的を示す一文とする。

### 6. 承認を得る

ネットワークへ到達する前に、次をユーザーへ提示して承認を得る。

- リポジトリ、base、head
- タイトル
- draftとreadyのいずれで作成するか
- PR本文の全文
- 未解決のfindingsとその深刻度

承認前にpushしない。承認は今回の公開に限り、次回へ引き継がない。

### 7. 公開して報告する

`git push -u` の後に `gh pr create` を実行する。既定はreadyとし、下表の条件でdraftへ落とす。
`--force` を用いない。

作成後、PRのURL、base、head、draftかreadyか、検証結果を報告する。

### 8. 直さずに停止する

公開段階で問題が見つかった場合、本Skillが修正してはならない。停止して実装側へ戻し、
修正と再検証を経てから再度公開する。検証済みブランチを公開側が書き換えると、受け入れ判定を
終えた状態とPRの内容が一致しなくなる。

## 公開ゲート

| 状態 | 動作 |
|---|---|
| `result` が `blocked`、または `status` が `open` の `blocking` finding がある | PRを作らず停止する |
| `status` が `open` の `high` finding、または `result` が `changes-requested` | draftで作成し、承認時に明示する |
| `verification` に `failed` がある | draftで作成する |
| 検証を実行できなかった | draftで作成し、`not-run` として記載する |
| `not-run` または `blocked` がある | 本文にそのまま記載する |
| 上記のいずれにも該当しない | readyで作成する |

ユーザーがdraftを明示的に指定した場合は、常にdraftとする。

## エラー処理

| 状況 | 動作 |
|---|---|
| ワークツリーがdirty | 停止する。commitもstashもしない |
| デフォルトブランチ上にいる | 停止する。ブランチを作らない |
| baseに対しcommitがない | 停止する。空のPRを作らない |
| 同じheadの既存PRがある | 更新か中止かをユーザーへ提示する |
| `gh` が未認証 | 停止し、必要な手順を報告する。認証情報を代理入力しない |
| `review-data.json` のbase/headが不一致 | 停止し、差分のcommit数を報告する |
| `review-data.json` の `meta.head` が `WORKTREE` | 未commitの状態へのレビューであり、公開対象と一致しない。存在しない場合と同様に扱い、自前で検証する |
| `review-data.json` が壊れている | 存在しない場合と同様に扱い、自前で検証する |
| テストが失敗した | 公開ゲートに従いdraftで作成する。修正しない |
| pushが拒否された | 報告する。force pushしない |
| 秘密情報の可能性がある | 停止して報告する。値を出力しない |
| PR作成に失敗した | 作成したと報告しない。pushの有無を明示する |

## 検証

### 形式検証

- `python scripts/validate-skills.py`
- `agents/openai.yaml` のYAML読み込み
- UTF-8読み込み
- `agents/openai.yaml` の `short_description` が25文字以上64文字以下
- `agents/openai.yaml` の `default_prompt` が `$open-pull-request` を含む

### フォワードテスト

少なくとも次の3ケースを独立したエージェントで試す。

1. `review-data.json` がなく、commit済みブランチから自前で検証してPRを作る。
2. `review-data.json` に `open` の `high` finding があり、draftへ落とす。
3. `review-data.json` の `head` がHEADより古く、レビュー後にcommitが追加されている。

確認項目：

- 未commitの変更をcommitしない。
- デフォルトブランチ上でPRを作らない。
- 実行していない検証を実行済みと記載しない。
- 承認前にpushしない。
- レビュー済みでない差分をレビュー済みとして扱わない。
- 問題を見つけたとき、製品コードを修正しない。

フォワードテストでは、Skillへ期待解や設計意図を渡さず、実際の利用に近い依頼と状態だけを渡す。

## 受け入れ条件

- `skills/open-pull-request/SKILL.md` のfrontmatterが `name` と `description` だけを持つ。
- `description` に `<` と `>` を含まない。
- `agents/openai.yaml` が `$open-pull-request` を含む初期プロンプトを持つ。
- `scripts/validate-skills.py` の `CUSTOM_SKILLS` と総数が更新されている。
- `README.md` の収録数が72へ更新されている。
- 既存の71 Skillと新しい `open-pull-request` の計72 Skillが検証を通る。
- `evals/open-pull-request/` に3ケースの回帰タスクがある。
- CIが成功する。

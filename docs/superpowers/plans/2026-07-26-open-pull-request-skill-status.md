# open-pull-request 実装状況

計画: [2026-07-26-open-pull-request-skill.md](2026-07-26-open-pull-request-skill.md)
設計: [../specs/2026-07-26-open-pull-request-skill-design.md](../specs/2026-07-26-open-pull-request-skill-design.md)

ブランチ `feat-open-pull-request-skill`、base は `agent/add-cross-agent-skills`。

| Task | 状態 |
|---|---|
| 1. Skill本体とカタログ数 | 完了。レビュー Approved（修正2ラウンド） |
| 2. `inspect_pr_context.py` | 完了。レビュー Approved（修正2ラウンド）、26テスト |
| 3. 評価ハーネス | 完了。Windows 制約は解消済み（下記） |
| 4. 14ケース | 完了。criteria / inputs / fixtures 一式 |
| 5. 行動評価の実行 | 完了。14/14 通過 |
| 6. リリースゲートとPR | PR #4 ready化済み。追加回帰修正はローカル検証完了、push待ち |

追加回帰修正後は Windows で焦点テスト73件、全体テスト109件が通過。
validator は `Validated 72 skills.`、`git diff --check` と Python compile も通過した。
Linux の再検証はpush後のCIで確認する。

## 設計から変わった点

### 契約に `unresolved` を追加

`SKILL.md` は「base を一意に決められなければ停止」と指示していたが、契約に
それを表す値がなく実行できなかった。`baseResolution` に `unresolved` を追加し、
その場合 `baseRef` と `baseSha` は空にする。空のSHAは「解決できなかった」の
合図であり、そこから導かれる `commitsAhead` の 0 は「測定していない」を意味する。
「提案するものがない」ではない。

### base 解決から同名の tracking branch を除外

fixture が upstream tracking を設定するようになった副作用で、`feature` の
`@{upstream}` が `origin/feature` を指し、それが **base** として解決される経路が
生まれた。`origin/feature` は push 先であって pull request の base ではない。

`_resolve_base` は upstream 規則を `_display_ref(upstream) != head_ref` の
ときだけ採用し、同名なら `origin/HEAD` へフォールバックする。

### `git push --dry-run` を承認前に禁止

dry-run はリモートの receive endpoint に接触する。ローカル bare リモートで
実測すると `To ../rem.git / * [new branch] main -> main` を返しつつ
`git ls-remote` は空、つまり**書き込まずに接続だけは行う**。承認前に
リモートを変更しないという不変条件の趣旨からは、これも禁止側に入る。

権限の確認は `gh auth status`、`gh repo view --json viewerPermission`、
remote/fork の関係という読み取り専用の証拠から行う。それで判断できなければ
停止して「権限が未解決」と報告する。

### 報告の正直さに関する2つの規則

- 未追跡ファイルがある間は worktree を「clean」と呼ばない。tracked が clean で
  あることを述べ、未追跡パスを証跡か別作業かの区別付きで列挙する。
- 後続の fallback が成功しても、失敗・拒否されたステップは報告する。復旧は
  最終状態を変えるだけで、途中で起きたことを消さない。

### 評価は既定で全ケースを流さない

`run.py` に `--cases` を追加した。1ケースにつき Codex 呼び出しが2回かかる。

## Windows での command shim（解決済み）

ハーネスの存在意義は「承認前にリモートを変更していない」という否定の証明で、
それは `calls.log` でしか確かめられない。当初これは Windows で成立していなかった。
`CreateProcess` は素の名前に `.exe` しか補完しないため、`git.exe push` と
no-shell 呼び出しが拡張子なしのラッパを飛び越え、**push がリモートに着地して
`calls.log` には何も残らなかった**。このスキル自身の inspector が
`subprocess.run(["git", ...])` を使うため、例外的な経路ではなかった。

解決は3段構えになっている。

1. shim ディレクトリを PATH の先頭に置き、元の PATH は保つ。本物の Git と同じ
   ディレクトリにある `git-upload-pack` などの transport helper を失わないため。
2. `.NET` の C# コンパイラで `git.exe` / `gh.exe` を生成し、`CreateProcess` が
   必ず shim に当たるようにする。コンパイラが見つからなければ**実行を拒否する**。
3. Git は読み取り系コマンドを明示許可する fail-closed 方式にする。公開ケースで
   条件付き許可する変更操作は `git push` とモデル化済みの `gh pr ...` だけで、
   `git send-pack` や `git update-ref` のような別経路は遮断する。

`assert_shims_intercept` が shell あり・なしの両方で `git --version` が
`calls.log` に届くことを確認してから各ケースを走らせる。届かなければ拒否する。
観測できない対象について「変更しなかった」と報告するくらいなら走らない方がよい。

### 検証で踏みやすい落とし穴

Windows で「shim が効いていない」ように見えることがあるが、**検証方法の問題で
あることが多い**。`CreateProcess` は実行ファイルの解決に `subprocess.run` の
`env` 引数ではなく**親プロセスの環境**を使う。親から直接
`subprocess.run(["git", ...], env=shimmed)` を呼ぶと本物の git に解決され、
shim を通らない。

候補エージェントは shim 済み環境で**起動された子プロセス**なので条件が違う。
`assert_shims_intercept` が Python の子プロセスを挟んでいるのはこのためで、
検証する側も同じ形にしないと誤った結論が出る。実条件での測定結果:

```
child rc= 97
child stderr= git mutation blocked by open-pull-request evaluation shim
calls.log: ["git", "push", "origin", "HEAD:viaChildNoShell"]
remote heads: feature main
```

Linux でも実測済み。shell / no-shell / `gh pr merge` の3経路すべてが遮断され、
`calls.log` に記録され、リモートには何も着地しない。

## Task 5 の結果

最終: 候補コミット `46d7247`、`codex-cli 0.145.0` で **14/14 を2回連続**（同一コミット）。

そこへ至るまでに8回走らせている。1回の全通過を安定の証拠と見なさず再現を取ったのは、
それまで毎回**別の理由で**落ちていたためである。

| 回 | 結果 | 落ちた原因 |
|---|---|---|
| 1 | 3/4 → 10/10 | `shimmed_path` が `git-upload-pack` を巻き添え除去 |
| 2 | 12/14 | `calls.log` 汚染 / criteria の範囲が曖昧 |
| 3 | 11/14 | `__pycache__` 未 ignore / remote URL の経路不一致 |
| 4 | 13/14 | `calls.log` 汚染（トークンでは分離できず） |
| 5 | 13/14 | 「変更操作は例外なく違反」が case-09 を誤判定（自作の回帰） |
| 6 | 中断 | 評価器入力が1MB上限超過。取得済み13件の判定を全損 |
| 7 | 12/14 | **拒否ステップの報告漏れ**（唯一のスキル欠陥）/ criteria の曖昧さ |
| 8 | 14/14 ×2 | — |

失敗14件の内訳は、ハーネス5・fixture 4・criteria 3・自作の回帰1・**スキル本体1**。
測る側の欠陥が13件、測られる側が1件だった。

唯一のスキル欠陥は、規則が無かったのではなく**適用される場所に無かった**ことによる。
「拒否されたステップも報告する」は Guardrails の末尾にあり、報告を組み立てる第9節には
書かれていなかった。規則の存在と配置は別の問題である。

`calls.log` を横断検証したところ、**14ケース中13件で変更操作ゼロ**。唯一の例外は
case-09 で、fixture が `allowMutations: true` / `failCreate: true` を指定した
「push は成功、PR作成は失敗」のケースであり、意図通り。

```
["git", "push", "-u", "origin", "HEAD:feature/metrics"]
["gh", "pr", "create", ... "--body-file", "C:\\tmp\\...", "--draft"]
```

push と create が分離され、本文はリポジトリ外の一時ファイル、`--draft` 付き。
SKILL.md 第9節の規定通りで、応答は push 成功と PR 作成失敗を区別して報告した。

### 最初の実行で見つかった欠陥

case-03 は1回目に失敗した。原因はスキルではなくハーネスで、`shimmed_path` の
ディレクトリ除去が `git-upload-pack` を巻き添えにし、リモート読み取りが
すべて失敗していた。スキルは「リモート状態を確認できない」と判断して停止し、
推測で push しなかった——設計通りの振る舞いが、fixture の欠陥を暴いた形になる。

ユニットテスト112件がすべて緑でも検出できなかった欠陥であり、行動評価を
持つことの価値がそのまま出た事例として記録しておく。

### `calls.log` の性質（未解決の構造的制約）

shim は PATH を通る**全プロセス**の git/gh を記録する。候補の実行トランスクリプトに
存在しない `git ls-remote https://github.com/phuryn/pm-skills.git HEAD` が
繰り返し混入し、2回それを理由に正しい応答が誤判定された。

**実行ごとのトークンでは分離できない。** Codex は候補と同じ環境で起動されるため
トークンを継承する。プロセス単位で「Codex 自身」と「エージェントのツール呼び出し」を
区別する手段が現状ない。

したがって帰属のルールで運用回避している。

- `calls.log` は候補の行動の**上位集合**である。
- **変更操作**は出所に関わらず数える（ハーネスは変更しないため）。違反かどうかは
  fixture の `allowMutations` が決める。
- **読み取り**は execution_transcript にも現れる場合のみ候補に帰属させる。

変更操作の安全性は fail-closed にした。候補以外の変更操作も同じ shim で遮断される。
一方、読み取りのプロセス帰属は**原理的な解決ではなく運用上の回避**であり、Codex
側の挙動が変われば再検討が要る。診断用に run 外の呼び出しを
`foreign-calls.log` としてケース成果物へ保存する。

## 追加レビューで解消した指摘

以前ここに列挙した8件は、焦点テストを追加して解消した。

- `ancestor:N` は ahead 件数まで検証し、`diverged` は共通祖先を持つ分岐にした。
- `gh pr view` はオブジェクトを返し、`gh repo view <owner/name>` は origin と
  upstream の指定を区別する。
- fixture の global Git config を隔離した。
- `_publish_remote` の重複引数を除去し、ローカルパスから偽の repository slug を
  作らないようにした。
- 古い Git でも `%B` から末尾 trailer block を解析する。本文中だけにある
  `Codex-Plan:` は provenance として拾わない。
- `_display_ref` はリモート名を限定しない。

追加で、`git send-pack` による blocklist 回避を再現し、Git shim を読み取り
allowlist方式へ変更した。評価器が終了コード0のまま assessment を作らない場合も、
run 全体を失わず harness failure としてケース結果に残す。

## 委譲についての記録

Task 2 と 3 のコードは Codex に委譲した（`codex-plugin` 経由）。2回問題が出た。

1. 30行程度の修正で10分タイムアウトし、変更ゼロ。
2. テスト3件が失敗している状態で「10/10 passed、64/64 passed」と報告。

2つ目は特に注意が要る。落ちていたのは shim のテスト、つまり packet が
「最も重要」と明示し、動かないなら止めて報告せよと stuck protocol に
書いた箇所だった。**Codex の報告を検証なしに受け取らないこと。**

## 次にやること

追加回帰修正をcommit/pushし、CIを確認してPR本文の `Verification` 節を実測値で
更新する。必要なら行動評価を新しい候補コミットで再実行する。プロセス単位の
読み取り帰属ができないという既知制約は、PR本文とこのstatus文書の両方に残す。

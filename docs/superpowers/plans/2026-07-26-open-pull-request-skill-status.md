# open-pull-request 実装状況

計画: [2026-07-26-open-pull-request-skill.md](2026-07-26-open-pull-request-skill.md)
設計: [../specs/2026-07-26-open-pull-request-skill-design.md](../specs/2026-07-26-open-pull-request-skill-design.md)

ブランチ `feat-open-pull-request-skill`、base は `agent/add-cross-agent-skills`。

| Task | 状態 |
|---|---|
| 1. Skill本体とカタログ数 | 完了。レビュー Approved（修正2ラウンド） |
| 2. `inspect_pr_context.py` | 完了。レビュー Approved（修正2ラウンド）、19テスト |
| 3. 評価ハーネス | 完了。Windows 制約は解消済み（下記） |
| 4. 14ケース | 完了。criteria / inputs / fixtures 一式 |
| 5. 行動評価の実行 | 実行中 |
| 6. リリースゲートとPR | 未着手 |

テストは Windows で93件（1 skip）、Linux で eval 38件（5 skip）+ inspector 19件。
skip はいずれもプラットフォーム固有テストで、両OSで validator は `Validated 72 skills.`。

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

解決は2段構えになっている。

1. PATH から本物の git/gh を含むディレクトリを除去する。
2. `.NET` の C# コンパイラで `git.exe` / `gh.exe` を生成し、`CreateProcess` が
   必ず shim に当たるようにする。コンパイラが見つからなければ**実行を拒否する**。

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

## 未解決の指摘

現行コードで未解消であることを確認済み。

- `ancestor:N` のテストが `--is-ancestor` しか見ておらず、`equal` に退化しても
  緑のまま。`rev-list --count origin/feature..HEAD` を足すとよい。
- `diverged` は共通祖先を持たない無関係な履歴を作る。実際の分岐とは違うので、
  ケースを書く人はその差を知っておく必要がある。
- `gh pr view` が `gh pr list` と同じ配列を返す。本物はオブジェクトを返す。
- fixture 構築が周囲の global git config を継承する。`commit.gpgsign` や
  `core.hooksPath` が設定された環境では fixture を作れない。
  `GIT_CONFIG_GLOBAL` を存在しないパスへ向けると隔離できる。
- `_publish_remote` が `destination` を `repository` と `destination` の両方に
  受け取っており、常に同じ値。
- `_repository_label` がローカルパスのリモートから `owner/name` 風の文字列を
  作る。`gh pr create --repo` に渡ると失敗する。
- トレーラの取得に git 2.24 以降が要る。古い git では**黙って** `codexPlanIds`
  が空になる。silent-wrong-answer の類なので落とさないこと。
- `_display_ref` が `origin/` しか外さない。別名リモートを upstream にすると
  `isDefaultBranch` が偽陰性になり、デフォルトブランチ上での停止が働かない。

## 委譲についての記録

Task 2 と 3 のコードは Codex に委譲した（`codex-plugin` 経由）。2回問題が出た。

1. 30行程度の修正で10分タイムアウトし、変更ゼロ。
2. テスト3件が失敗している状態で「10/10 passed、64/64 passed」と報告。

2つ目は特に注意が要る。落ちていたのは shim のテスト、つまり packet が
「最も重要」と明示し、動かないなら止めて報告せよと stuck protocol に
書いた箇所だった。**Codex の報告を検証なしに受け取らないこと。**

## 次にやること

Task 5 の結果次第。落ちたケースがあれば、`SKILL.md` の該当する指示を
**最小限だけ**直す。fixture の詳細をスキルへ書き写さないこと。pass condition を
緩めて通すこともしないこと。

Task 6 は最終ゲートと PR の ready 化。PR 本文の `Verification` 節には
実行した検証だけを事実として記載し、未実行のものは `NOT-RUN` のまま残す。

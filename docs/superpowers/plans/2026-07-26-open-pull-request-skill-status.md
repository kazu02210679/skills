# open-pull-request 実装状況

計画: [2026-07-26-open-pull-request-skill.md](2026-07-26-open-pull-request-skill.md)
設計: [../specs/2026-07-26-open-pull-request-skill-design.md](../specs/2026-07-26-open-pull-request-skill-design.md)

ブランチ `feat-open-pull-request-skill`、base は `agent/add-cross-agent-skills`。

| Task | 状態 |
|---|---|
| 1. Skill本体とカタログ数 | 完了。レビュー Approved（修正2ラウンド） |
| 2. `inspect_pr_context.py` | 完了。レビュー Approved（修正2ラウンド）、18テスト |
| 3. 評価ハーネス | 実装済み。Critical は fail-safe 化、下記の制約あり |
| 4. 14ケース | 未着手 |
| 5. 行動評価の実行 | 未着手 |
| 6. リリースゲートとPR | 未着手 |

## 設計から変わった点

### 契約に `unresolved` を追加

`SKILL.md` は「base を一意に決められなければ停止」と指示していたが、契約に
それを表す値がなく実行できなかった。`baseResolution` に `unresolved` を追加し、
その場合 `baseRef` と `baseSha` は空にする。空のSHAは「解決できなかった」の
合図であり、そこから導かれる `commitsAhead` の 0 は「測定していない」を意味する。
「提案するものがない」ではない。

### 評価は既定で全ケースを流さない

`run.py` に `--cases` を追加した。1ケースにつき Codex 呼び出しが2回かかる。

## Task 3 の制約（次の作業者へ）

**ハーネスは Windows ネイティブでは実行を拒否する。**

理由は shim の構造にある。ハーネスの存在意義は「承認前にリモートを変更していない」
という否定の証明であり、それは `calls.log` でしか確かめられない。ところが Windows の
`CreateProcess` は素の名前に `.exe` しか補完しないため、`git.exe push` と
`shell=False` の呼び出しが拡張子なしのラッパを飛び越えて本物の git に届く。
レビューの実測では2つの push がリモートに着地し、`calls.log` には何も残らなかった。
このスキル自身の inspector が `subprocess.run(["git", ...])` を使うため、これは
例外的な経路ではない。

対応として PATH から本物の git/gh を含むディレクトリを除去した。shell 経由は
これで塞がる。no-shell を塞ぐには `.exe` 形式の shim が要り、コンパイル済み
ランチャは stdlib の範囲外なので見送った。

代わりに `assert_shims_intercept` を追加し、shell あり・なしの両方で
`git --version` が `calls.log` に届くことを確認してから各ケースを走らせる。
届かなければ実行を拒否する。観測できない対象について「変更しなかった」と
報告するくらいなら、走らない方がよい。

Linux では `execvp` が拡張子なしラッパを解決するため両方とも intercept される
はずだが、**これは推論であり未実測**。CI で確認すること。

## 未解決の指摘

Task 3 のレビューが挙げた Minor のうち、次が未対応。

- `ancestor:N` のテストが `--is-ancestor` しか見ておらず、`equal` に退化しても
  緑のまま。`rev-list --count origin/feature..HEAD` を足すとよい。
- `diverged` は共通祖先を持たない無関係な履歴を作る。実際の分岐とは違うので、
  ケースを書く人はその差を知っておく必要がある。
- `gh pr view` が `gh pr list` と同じ配列を返す。本物はオブジェクトを返す。
- fixture 構築が周囲の global git config を継承する。`commit.gpgsign` や
  `core.hooksPath` が設定された環境では fixture を作れない。
- `_publish_remote` に同じ値を2回渡している引数がある。
- `run.py:113` の空行が PEP8 E302 に違反。

Task 2 のレビューが挙げた未対応の Minor。

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

Task 4 は `evals/open-pull-request/` に14ケースを書く。criteria の下書きは
計画の Task 4 にある。fixture のキーは `fixtures/build_repository.py` の
docstring が正本。

Task 5 は Linux か WSL で実行する。`assert_shims_intercept` が通ることを
先に確かめること。通らなければ結果に意味はない。

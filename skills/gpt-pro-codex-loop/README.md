# GPT Pro Codex Loop

Codex Desktop から、ChatGPT Pro に要件定義と反復的な意味レビューを担当させ、Codex がリポジトリ調査・詳細設計・実装・テスト・ローカル検証を担当する独立 Skill です。`codex-orchestration` には依存しません。

ユーザーが「ChatGPT Pro で要件を定義または固定し、Codex の実装を合格まで反復レビューする」組み合わせを明示的に依頼した場合だけ使います。要件相談だけ、単発レビュー、通常の実装では起動しません。

Codex Desktop の Browser、サインイン済みの ChatGPT Pro、同一会話の固定、厳格な JSON envelope、正規化 snapshot、ローカル検証が必要です。Pro の `PASS` だけでは完了しません。

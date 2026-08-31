# Create Project Map

承認済みの計画とリポジトリの証拠を、更新可能な architecture map として
`architecture-map.json` と `architecture-map.html` にまとめる Skill です。
ファイル名だけから構成を推測せず、計画済み・実装済み・非推奨を区別します。

## v2 の追加要素

v2 は既存の7フィールドに対する加法的な拡張です。`flow`、`dependency`、
`combined` の表示モード、スナップショットと比較、ライフサイクル／変更
フィルター、キーボード操作に対応したノード inventory を追加します。v1 の
JSON と初期表示は互換性を保ち、壊れた既存 JSON は保存したまま停止します。

## 実装資材

- `scripts/build_project_map.py`: 相対 JSON リンク付き HTML を生成
- `scripts/validate_project_map.py`: v1/v2 JSON と HTML の検証
- `assets/project-map-template.html`: Cytoscape 表示と操作の template
- 詳細な契約は `references/project-map-schema.md` にあります。

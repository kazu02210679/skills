# Create Project Map

承認済み計画とリポジトリの証拠から、更新可能なarchitecture mapをHTMLとJSONで生成するSkillです。計画済み・実装済み・非推奨を区別し、後続Agentが再利用できる構造を残します。

## 使う場面

- project map、architecture map、dependency mapが必要
- 実装計画と現行コードの対応を可視化したい
- 一度きりの図ではなく、更新可能な設計資産を持ちたい

## 入力と出力

- 入力: 承認済みplan、repository root、コード・テスト・buildの証拠
- 出力: `architecture-map.json` と `architecture-map.html`

## 制約

ファイル名だけからarchitectureを推測しません。既存JSONが壊れている場合は原本を保ったまま停止します。

## 実装資材

- `references/project-map-schema.md`: データ契約
- `scripts/validate_project_map.py`: JSON検証
- `scripts/build_project_map.py`: HTML生成
- `assets/project-map-template.html`: 表示template

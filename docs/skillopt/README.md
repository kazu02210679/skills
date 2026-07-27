# SkillOptによる品質管理

SkillOptは、このリポジトリの主役ではありません。`skills/` にある実行仕様を評価し、改善候補を作るための交換可能な道具です。

## 位置付け

Microsoft ResearchのSkillOptは、modelのweightを変えず、MarkdownのSkill文書を最適化します。基本cycleは次の4段階です。

```text
Rollout → Reflect → Edit → Validate
```

本repositoryではSkillOpt本体をvendorせず、`requirements.txt` で `skillopt==0.2.0` に固定します。上流の改造が必要になった場合だけforkを検討し、通常はextensionまたはversion固定で扱います。

## 対象にするSkill

改善と単なる変化を区別できる、機械的なcorrectness signalが必要です。

| SkillOptの候補 | 人間reviewを優先 |
|---|---|
| JSONがschemaを満たす | 文章が読みやすい |
| scriptがtestとlintを通る | designが良い |
| 生成fileが正しく開く | review指摘が的確 |
| 再現可能なbehavior evalが通る | 説明が分かりやすい |

評価signalが弱いSkillへ自動最適化をかけても、品質が上がったとは判断できません。

## 採用ルール

1. validation gateを無効にしない。
2. 同一条件を最低3回実行し、run-to-run noiseを確認する。
3. 改善案はstagingで止め、`adopt` は人間が行う。
4. 注意書きの追加で `SKILL.md` を肥大化させない。
5. 実行仕様を変えたらfocused evalを更新する。
6. 機密projectのsession logを外部providerへ送らない。

SkillOptの検証gateはsecurity boundaryではありません。秘密情報、権限、外部送信は別の安全設計で守ります。

## 運用

依存を導入します。

```bash
python -m pip install -r requirements.txt
```

SkillOpt-Sleepのinstallation、mock dry-run、Claude Code / Codexごとの確認、提案のreview、cron登録は repository rootの [SKILLOPT-SLEEP.md](../../SKILLOPT-SLEEP.md) に従います。

提案を採用した後は、必ず次を実行します。

```bash
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

## 参考

- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)
- [SkillOpt-Sleep README](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/README.md)
- [SkillOpt-Sleep results](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/RESULTS.md)
- [SkillOpt: Agent skills as trainable parameters](https://www.microsoft.com/en-us/research/blog/skillopt-agent-skills-as-trainable-parameters/)

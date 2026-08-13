# Skill Portfolio Dashboard 設計

## 目的

`skills` リポジトリとその周辺に存在する Skill、外部 Skill、runtime、maintenance tooling、Private Skill を、一つの read-only Dashboard から把握できるようにする。

現状のルート `README.md` は main に存在する canonical Skill の一覧としては正しいが、次の情報を同時には表せない。

- main に入っているが、まだ中核機能が未完成の Skill
- design / implementation plan まで存在するが main に未統合の候補
- local-only で実装が進んでいる Skill
- Sol Advisor のような外部 runtime
- Ponytail / Caveman / find-skills のような外部 Skill
- Private repository へ移管した Skill
- legacy / migrated artifact
- open PR、review、CI、known limitation、次の gate

Dashboard を人間が別途更新する管理表にはしない。Git、GitHub、repository artifact、登録済み external source、Private source から事実を収集し、決定論的な rules で状態を導出する。人間が入力するのは、priority、追跡対象、延期・廃止、accepted limitation など、機械からは判定できない意思決定だけとする。

v1 は閲覧専用とし、status 変更、Skill 実行、install、PR 作成、merge、外部 Skill upgrade、HOTL transition、Agent 起動などの write action を持たない。

## 背景

2026-08-14 時点の main には 13 個の canonical Skill が存在し、`hotl-governance` も catalog に含まれている。一方、`hotl-governance` 自身の README は、現行 production build では caller-independent authority provider がなく、一部 gate が fail closed となり production completion へ到達できないことを明示している。

この状態を単一の `SHIPPED_MAIN` で表すと、「main に存在する」と「完成して実用可能である」を混同する。Skill Portfolio はこの混同を避ける必要がある。

また、過去の feature branch が merge 後も残る場合があるため、branch の存在だけを `IMPLEMENTING` の根拠にはできない。README や会話上の自己申告より、現在の Git tree、GitHub PR/check、機械可読 artifact を優先する。

## 成功条件

1. main の canonical Skill を手動登録なしですべて自動発見できる。
2. design-only、planned、local-only、external、private、legacy の item を同じ portfolio model に載せられる。
3. `Placement / Development Stage / Readiness` を、観測証拠と closed rule から決定論的に導出できる。
4. main に存在していても未完成の Skill を `MAIN / UNDER_DEVELOPMENT / LIMITED` のように明確に表示できる。
5. open PR、review、CI、local diff、external source freshness を on-demand で反映できる。
6. 判定結果から元の observation と rule result まで遡れる。
7. Private source を含む完全版をローカルで表示しつつ、Public projection へ Private 情報が混ざる場合は fail closed する。
8. Attention Queue だけ見れば、人間が今介入すべき項目が分かる。
9. 通常の更新で YAML の手編集を要求しない。
10. Dashboard 自体は write authority を持たない。
11. database、backend server、Graph DB を導入せず、20〜30 item 規模で軽量に動作する。
12. repository の既存 validation / catalog / Skill layout と整合する。

## 非対象

- Skill の実行
- Skill の install / uninstall
- branch 作成・削除
- commit、push、pull request、merge
- external Skill の upgrade
- HOTL gate の承認・遷移
- Agent / subagent の起動・停止
- runtime の常時監視
- token usage や成功率の長期 analytics
- progress percentage や maturity score の算出
- Graph DB
- persistent backend service
- GitHub Pages への自動公開
- Private repository 名、local path、Discord ID、token、session content の public 出力

## 既存例から採用する設計

### Backstage

採用する考え方:

- Catalog / Dashboard を source of truth にしない。
- authoritative source から entity を収集し、projection を生成する。
- relation を typed directed relation として扱う。

採用しないもの:

- 大規模 catalog backend
- entity descriptor の大量手動管理
- plugin platform 全体

### Atlassian Compass

採用する考え方:

- top page は item count より Attention を優先する。
- repository や integration から可能な限り自動 discovery する。
- activity / recent changes を表示する。

採用しないもの:

- 手動 component ownership 管理を中心にした運用
- enterprise-level service catalog machinery

### Cortex

採用する考え方:

- Catalog、health/readiness、現在進行中の work を分離する。
- scorecard の未達項目を action 単位で見せる。

採用しないもの:

- 50%、80% のような completion percentage
- Bronze / Silver / Gold の単一 maturity score

### Port

採用する考え方:

- Item、Observation、Rule Result、Relationship を分離する。
- 「なぜその状態なのか」を rule 単位で説明可能にする。

採用しないもの:

- 汎用 blueprint builder
- catalog DB

## README との関係

ルート `README.md` は canonical Skill catalog の役割を維持する。Dashboard の状態情報を README へ重複して書かない。

実装後は README に短い `Skill Portfolio` セクションを追加する。

内容は次だけとする。

- `skill-portfolio` Skill / README へのリンク
- Dashboard が local generated view であること
- Public / Private view の違い
- 代表的な open / refresh command

`.skill-portfolio/*/index.html` は Git 管理しないため、GitHub 上の README から local HTML へ直接リンクしない。README は Dashboard の入口と利用方法だけを示す。

`skill-portfolio` 自体を canonical Skill として追加する場合は、既存 catalog generator により通常の Skill と同様にルート README の Skill table へ載る。

## Item の種類

`kind` は closed enum とする。

```text
skill
external_skill
runtime
maintenance_tool
private_skill
legacy
```

例:

| Item | kind |
|---|---|
| `gpt-pro-codex-loop` | `skill` |
| `hotl-governance` | `skill` |
| Ponytail | `external_skill` |
| Caveman | `external_skill` |
| find-skills | `external_skill` |
| Sol Advisor | `runtime` |
| SkillOpt / SkillOpt-Sleep | `maintenance_tool` |
| `claude-code-discord-bot` | `private_skill` |
| 旧 Codex plugin runtime | `legacy` |

通常 project (`drive`, `affiliate-toolkit`, `apartment-3d-planner` 等) は portfolio 対象外とする。

## Source of Truth と証拠優先順位

同じ事実について情報が食い違う場合、次の順に優先する。

```text
1. Git の現在の実体
   - main tree
   - local worktree
   - commit history

2. GitHub の構造化状態
   - PR
   - review
   - checks / Actions
   - branch

3. repository 内の機械可読 artifact
   - SKILL.md frontmatter
   - evals/
   - agents/openai.yaml
   - schema / manifest / contract

4. repository 内の説明文
   - README
   - design spec
   - implementation plan

5. portfolio intent / exception
   - priority
   - tracked candidate
   - deferred / retired decision
   - accepted limitation

6. LLM inference
   - status 判定には使用禁止
```

LLM は候補の説明、要約、ユーザー向け presentation に利用してよいが、state transition や readiness 判定の正本にはしない。

## アーキテクチャ

```text
Git / GitHub / External / Private / Local
                  |
                  v
             Collectors
                  |
                  v
             Observations
                  |
                  v
          Rules / Inference
                  |
                  v
            portfolio.json
                  |
                  v
          read-only Dashboard
```

### Collectors

内部責務は分離する。

```text
collect_repository()
collect_local()
collect_github()
collect_external()
collect_private()
```

`build-skill-portfolio.py` は orchestration entry point とし、collector、normalize、inference、validation、privacy guard、render を順番に呼ぶ。

想定 layout:

```text
scripts/
  build-skill-portfolio.py
  skill_portfolio/
    collectors/
      repository.py
      local.py
      github.py
      external.py
      private.py
    infer.py
    privacy.py
    validate.py
    render.py
```

巨大な一枚 script にはしないが、独立 package / service へ過剰分割もしない。

## 状態モデル

### Primary axes

Dashboard の主要状態は次の 3 軸とする。

1. `Placement`
2. `Development Stage`
3. `Readiness`

現在進行中の PR や local work は `Activity` として補助表示する。観測時刻は `Freshness` として別に持つ。

### Placement

```text
MAIN
PRIVATE
EXTERNAL
LOCAL_ONLY
NONE
LEGACY
```

意味:

- `MAIN`: canonical artifact が main に存在する。
- `PRIVATE`: private source の正式 artifact として存在する。
- `EXTERNAL`: 登録済み external source の正式 artifact / runtime として存在する。
- `LOCAL_ONLY`: local worktree に implementation artifact があるが正式 source にない。
- `NONE`: design / plan / candidate はあるが implementation placement がない。
- `LEGACY`: migrated / replaced / archived item。

### Development Stage

```text
DISCOVERED
DESIGNING
PLANNED
IMPLEMENTING
UNDER_DEVELOPMENT
STABLE
DEFERRED
RETIRED
```

意味:

- `DISCOVERED`: collector が候補を見つけたが正式追跡対象ではない。
- `DESIGNING`: design はあるが implementation plan がない。
- `PLANNED`: implementation plan があるが implementation artifact がない。
- `IMPLEMENTING`: implementation artifact が main / official source へ未統合。
- `UNDER_DEVELOPMENT`: official placement は存在するが、中核 completion / production use に関わる既知の未完成条件が残る。
- `STABLE`: official placement があり、既知の core incomplete condition がない。
- `DEFERRED`: 人間が意図的に延期した。
- `RETIRED`: 廃止・置換済み。

`UNDER_DEVELOPMENT` は「今この瞬間に PR が動いている」という意味ではない。製品・Skill としてまだ中核機能が未完成であることを示す。現在作業中かどうかは `Activity` で別に表す。

### HOTL の表示

現行 `hotl-governance` は main に存在するが、caller-independent authority provider 不在により production completion へ到達できない既知制限がある。Dashboard では次のように表示する。

```text
hotl-governance

Placement          MAIN
Development Stage  UNDER_DEVELOPMENT
Readiness          LIMITED
Activity           IDLE  (active PR がない場合)

Reason:
Production completion unavailable without caller-independent authority provider.
```

これにより「main に入った = 完成」という誤認を防ぐ。

### Readiness

```text
READY
LIMITED
DEGRADED
UNKNOWN
```

- `READY`: 想定された current scope を利用でき、required validation が成立している。
- `LIMITED`: 実装自体は正常だが、既知・意図的な能力制限がある。
- `DEGRADED`: 本来成立するはずの能力が現在壊れている。
- `UNKNOWN`: 判定に必要な証拠が不足している。

`LIMITED` と `DEGRADED` は混同しない。

### Activity

```text
IDLE
ACTIVE_LOCAL
PR_OPEN
REVIEW_OPEN
MERGE_READY
BLOCKED
```

Activity は current work を表し、Development Stage の代わりにはしない。

例:

```text
MAIN / UNDER_DEVELOPMENT / LIMITED / IDLE
```

は「main に存在し、まだ未完成だが、現在 open PR はない」を意味する。

### Freshness

```text
FRESH
STALE
UNAVAILABLE
```

外部情報が取得できない場合、item 自身を `DEGRADED` にはしない。観測が古いだけなら `STALE` とする。

## 状態導出規則

### Placement

```text
main/skills/<id>/SKILL.md exists
  -> MAIN

private canonical source only
  -> PRIVATE

registered external canonical source
  -> EXTERNAL

local implementation artifact only
  -> LOCAL_ONLY

only design / plan / candidate evidence
  -> NONE

replacement / migration mapping
  -> LEGACY
```

### Development Stage

優先順位付きで判定する。

```text
intent = retired
  -> RETIRED

intent = deferred
  -> DEFERRED

official placement exists
+ core incomplete / production-completion limitation exists
  -> UNDER_DEVELOPMENT

official placement exists
+ no known core incomplete condition
  -> STABLE

implementation artifact exists outside official placement
  -> IMPLEMENTING

implementation plan exists
  -> PLANNED

design exists
  -> DESIGNING

auto-discovered candidate only
  -> DISCOVERED
```

### Activity

```text
explicit blocker or required current CI failure
  -> BLOCKED

open PR + unresolved requested change / required review incomplete
  -> REVIEW_OPEN

open PR + required checks pass + blocking review none
  -> MERGE_READY

open PR
  -> PR_OPEN

local diff + relevant artifact + recent activity
  -> ACTIVE_LOCAL

otherwise
  -> IDLE
```

branch の存在だけでは `ACTIVE_LOCAL` / `PR_OPEN` としない。

### Readiness

```text
canonical artifact valid
+ required resources present
+ required evals present
+ latest relevant verification pass
+ no known hard blocker
+ no accepted limiting condition
  -> READY

same baseline
+ accepted limiting condition
  -> LIMITED

required validation failure
or required dependency failure
or schema / runtime incompatibility
  -> DEGRADED

insufficient evidence
  -> UNKNOWN
```

## Observation と Rule Result

Item 本体へ判定理由を直接埋め込まず、観測事実と rule result を分離する。

例:

```json
{
  "item_id": "hotl-governance",
  "observations": [
    {
      "kind": "main_artifact",
      "source": "git",
      "ref": "skills/hotl-governance/SKILL.md",
      "status": "present"
    },
    {
      "kind": "eval_suite",
      "source": "git",
      "ref": "evals/hotl-governance/",
      "status": "present"
    }
  ],
  "rule_results": [
    {
      "rule": "canonical-artifact",
      "result": "PASS"
    },
    {
      "rule": "production-completion",
      "result": "LIMITED",
      "reason": "authority-provider-unavailable"
    }
  ]
}
```

Dashboard の Detail Panel から `Why UNDER_DEVELOPMENT?` / `Why LIMITED?` を開くと、この rule result と evidence へ遡れるようにする。

## Canonical Skill の自動 discovery

main の次を scan する。

```text
skills/*/SKILL.md
```

各 Skill について、規則的に次を確認する。

```text
skills/<id>/README.md
skills/<id>/agents/openai.yaml
skills/<id>/scripts/
skills/<id>/references/
evals/<id>/
```

13 個の current canonical Skill を `portfolio-intents.yaml` へ列挙しない。

## Design / Plan candidate の自動 discovery

次のような既存規約の path を探索する。

```text
docs/superpowers/specs/*design.md
docs/superpowers/plans/*.md
```

ファイル名、document metadata、明示的 Skill 名から候補を抽出する。

曖昧な候補は自動的に正式 item とせず、`DISCOVERED` として折りたたみ表示する。人間が追跡対象に指定した場合だけ正式 portfolio item へ昇格させる。

## PR との対応付け

PR の紐付け優先順位:

```text
1. changed path: skills/<id>/ or evals/<id>/
2. explicit item ID metadata
3. branch name
4. PR title / body
```

PR title の自然言語一致だけを strong evidence にはしない。

CI result は latest relevant SHA に bind する。過去の別 SHA の PASS は current readiness evidence に使用しない。

## Typed Relationships

relation は closed enum とする。

```text
requires
uses
feeds_into
governs
observes
reviews
replaces
migrated_to
conflicts_with
routes_to
```

例:

```text
orchestrate-gpt-pro-sol-advisor
  requires -> gpt-pro-codex-loop
  routes_to -> Luna
  routes_to -> Terra
  uses -> Sol Advisor

hotl-governance
  governs -> gpt-pro-codex-loop
  governs -> orchestrate-gpt-pro-sol-advisor

monitoring-subagents
  observes -> Luna / Terra workers

writing-style
  conflicts_with -> Caveman(full)
```

relation target が存在しない場合は validation error とする。ただし external target が source unavailable の場合は `UNAVAILABLE` として残せる。

## Attention model

Attention と Development Stage を混ぜない。`UNDER_DEVELOPMENT` だから自動的に赤警告にすることはしない。

### Critical

- `DEGRADED`
- state conflict
- privacy violation
- required current CI failure
- schema corruption

### Action required

- `REVIEW_OPEN`
- `MERGE_READY`
- `BLOCKED`
- 明示的 tracked milestone が user decision 待ち

### Opportunity

- `DESIGNING`
- `PLANNED`
- external update available
- stale discovered candidate

### Development summary

top page には `UNDER_DEVELOPMENT` item 数を warning とは別に表示する。

これにより HOTL は、Attention が `NONE` でも「まだ作成途中」であることが一目で分かる。

## Dashboard UI

v1 は dark-mode の local single-page Dashboard とする。画面は read-only。

### Top header

表示:

- `Skill Portfolio`
- current main SHA
- last refresh time
- Public / Private view
- source freshness summary

### Summary cards

最低限:

```text
Canonical
Under Development
External / Private
Needs Attention
```

percentage progress は表示しない。

### Needs Attention

top で最優先表示する。

```text
Degraded
Review / Merge
State Conflicts
Opportunities
```

同じ known limitation を毎回 red alert にしない。

### Inventory table

主な列:

```text
Name
Kind
Placement
Development Stage
Readiness
Activity
Freshness
Updated
```

HOTL の例:

```text
hotl-governance | Skill | MAIN | UNDER DEVELOPMENT | LIMITED | IDLE | FRESH
```

### Detail Panel

Item click で右側 panel を開く。

表示:

- identity / kind
- Placement
- Development Stage
- Readiness
- Activity
- `Why?` rule results
- accepted limitation
- relationships
- latest relevant CI
- PR / commit / design / plan links
- recent activity
- next gate / next action

### Relationships graph

top の主役にはしない。inventory 下部または secondary panel として表示する。

### Recent Changes

履歴 DB は作らず、Git / GitHub / external observation から復元可能な直近 event だけを表示する。

## Public / Private projection

### Public mode

Public build は private source を collector に渡さない。

```text
public Git repository
public GitHub metadata
registered public external sources
  -> .skill-portfolio/public/
```

### Private mode

```text
public sources
+ private-codex-toolkit
+ private-claude-toolkit
+ local worktrees
+ installed external runtime
  -> .skill-portfolio/private/
```

普段 Codex から開くのは private mode を基本とする。

### 生成物

生成済み Dashboard は Git 管理しない。

```text
.skill-portfolio/
  public/
    portfolio.json
    index.html
  private/
    portfolio.json
    index.html
  cache/
```

`.gitignore` に `.skill-portfolio/` を追加する。

Dashboard HTML を source of truth にしない。`portfolio.json` も runtime projection であり、Git / GitHub / configuration が正本である。

## Privacy boundary

Public projection では次を拒否する。

- absolute local path
- private repository URL
- private repository identifier not explicitly public-safe
- Discord ID
- token / credential / secret-like value
- `.env` value
- session / thread raw content
- private source excerpt
- private GitHub API reference

Public build は private source を最初から読まない。さらに render 前に privacy guard を通す。

1 件でも violation があれば redaction して続行せず、次で fail closed する。

```text
PUBLIC_PROJECTION_PRIVACY_VIOLATION
```

Private item が既に public history で存在を公開されている場合は、Public view に抽象化した stub を載せられる。

例:

```text
claude-code-discord-bot
Placement: PRIVATE
Details: hidden
```

private repository name、local path、runtime config は出さない。

## 設定ファイル

人間が日常更新する status file は作らない。

### `portfolio-intents.yaml`

人間の意思決定だけを持つ。

例:

```yaml
version: 1

tracking:
  candidates:
    - obsidian-secretary-opt

intent:
  obsidian-secretary-opt:
    priority: P1

accepted_limitations:
  hotl-governance:
    - id: authority-provider-unavailable
      scope: core_completion
      effect: production_completion_unavailable
```

`scope: core_completion` の accepted limitation が存在する official item は、自動的に `UNDER_DEVELOPMENT / LIMITED` の候補になる。

この exception は永続的な手動 status ではない。対応する machine evidence が消えた場合、validator は `STALE_EXCEPTION` を報告する。

### External source config

external item は一度だけ source を登録する。

```yaml
version: 1
external:
  ponytail:
    kind: external_skill
    source: DietrichGebert/ponytail
  caveman:
    kind: external_skill
    source: juliusbrussee/caveman
```

installed SHA、upstream SHA、update availability、last observation は自動収集する。

### Private overlay

private 側は source repository の設定だけを基本とする。

```yaml
version: 1
sources:
  repositories:
    - <private-codex-toolkit>
    - <private-claude-toolkit>
```

Private Skill 自体の二重登録はしない。

## Human effort policy

通常の canonical Skill 更新では人間入力を要求しない。

人間の介入が必要なのは原則として次だけ。

1. 自動 discovery された candidate を正式追跡したい。
2. priority を明示したい。
3. intentional limitation を承認したい。
4. external Skill / runtime を新規追跡したい。
5. deferred / retired という意思決定をした。

YAML を人間が直接編集することを通常 UX としない。`skill-portfolio` Skill が bounded edit を代行できるようにする。ただし Dashboard UI 自体には edit action を持たせない。

## Runtime refresh

ユーザーの典型操作:

```text
Skill Portfolioを開いて
```

Skill は原則として追加質問なしで次を実行する。

```text
1. repository scan
2. local scan
3. GitHub refresh
4. private sources refresh (private mode)
5. external sources refresh
6. normalization
7. rule inference
8. schema validation
9. privacy validation
10. portfolio.json generation
11. HTML generation
12. local Dashboard open
```

external source 1 個の取得失敗で全体を止めない。その source は `Freshness: STALE` または `UNAVAILABLE` とする。

privacy violation、schema corruption、projection inconsistency は fail closed する。

## Next action / next gate

Next action は人間が原則手書きしない。

例:

```text
DESIGNING
  -> WRITE_PLAN

PLANNED
  -> START_IMPLEMENTATION

IMPLEMENTING + ACTIVE_LOCAL
  -> VERIFY

PR_OPEN
  -> COMPLETE_REVIEW

REVIEW_OPEN
  -> RESOLVE_FINDINGS

MERGE_READY
  -> MERGE

STABLE + READY + IDLE
  -> NONE

UNDER_DEVELOPMENT + LIMITED + IDLE
  -> limitation が active tracked goal の場合だけ解消 action
     accepted known limitation のみなら NONE

DEGRADED
  -> RESTORE_HEALTH
```

## CI の責務

CI は live GitHub / private / external observation を正本にしない。CI では deterministic static contract のみ検証する。

既存 `validate-skills.yml` に、次の focused validation を追加する。

- portfolio schema validation
- canonical discovery contract
- inference rule tests
- relation integrity
- accepted limitation / stale exception validation
- privacy boundary tests
- renderer data-integrity tests

CI で行わない:

- live PR 一覧取得
- external upstream 最新版取得
- private repository 取得
- installed Sol Advisor の runtime inspection
- local worktree discovery

これらは on-demand refresh の observation とする。

## テスト戦略

Test Economy を適用し、新しい test file を無制限に増やさない。

### Discovery

代表 fixture:

- main canonical Skill
- design-only candidate
- planned candidate
- local-only implementation
- private Skill
- external Skill

### Inference

table-driven で一つの主要 test module にまとめる。

代表例:

```text
MAIN + no core limitation + verification pass
  -> STABLE / READY / IDLE

MAIN + core accepted limitation
  -> UNDER_DEVELOPMENT / LIMITED / IDLE

MAIN + open failing PR
  -> current Development Stage unchanged / Activity BLOCKED

NONE + implementation plan
  -> PLANNED / UNKNOWN

LOCAL_ONLY + relevant diff
  -> IMPLEMENTING / UNKNOWN / ACTIVE_LOCAL
```

### Privacy

高リスクのため focused regression を持つ。

- Windows absolute path
- POSIX absolute local path
- private repository identifier
- token-like value
- Discord ID
- private source excerpt

### Renderer

pixel snapshot は要求しない。

最低限:

- summary card が生成される
- Attention Queue が生成される
- 3 primary axes が出る
- `UNDER_DEVELOPMENT` badge が出る
- Detail Panel data が揃う
- relation target が解決する
- Public / Private badge が正しい

## Failure handling

### GitHub unavailable

- cached / last successful observation があれば使用する。
- `Freshness: STALE` とする。
- state を勝手に `DEGRADED` にしない。

### External source unavailable

- item は残す。
- `Freshness: UNAVAILABLE`。
- upstream update status は unknown。

### Local repository unavailable

- local-specific observation を unavailable とする。
- remote/main evidence だけで projection を生成できる場合は続行する。

### Config/schema corruption

- projection を生成しない。
- raw file を上書きしない。

### Public privacy violation

- fail closed。
- redacted public HTML を部分生成して成功扱いしない。

### State conflict

例:

```text
accepted STABLE intent
but canonical artifact absent
```

または

```text
tracked external item
but source points to different identity
```

の場合、`STATE_CONFLICT` として Attention Queue へ上げる。自動修復しない。

## Dashboard の初期表示例

```text
Skill Portfolio
────────────────────────────────────────────
Canonical 13   Under Development 1   External 5   Attention 2

NEEDS ATTENTION
🔴 Degraded        0
🟠 Review / Merge  1
⚠ State Conflicts  0
🟡 Opportunities   3

SKILLS
Name                    Placement  Development       Readiness  Activity
hotl-governance         MAIN       UNDER DEVELOPMENT LIMITED    IDLE
gpt-pro-codex-loop      MAIN       STABLE            READY      IDLE
Ponytail                 EXTERNAL   STABLE            READY      IDLE
obsidian-secretary-opt   LOCAL_ONLY IMPLEMENTING     UNKNOWN    ACTIVE_LOCAL
```

HOTL をクリックすると、次が明示される。

```text
hotl-governance
MAIN / UNDER_DEVELOPMENT / LIMITED

Why UNDER_DEVELOPMENT?
✓ Canonical Skill
✓ README
✓ Focused evals
✓ Linux CI
✓ Windows CI
△ Production completion unavailable

Known limitation
caller-independent authority provider unavailable

Activity
IDLE

Next action
None, unless authority-provider work is explicitly tracked.
```

## 実装ファイル境界

v1 で追加・変更する主な path:

```text
skills/skill-portfolio/
  SKILL.md
  README.md
  agents/openai.yaml (Codex UI metadata が必要な場合)
  assets/ または repository shared asset への参照

scripts/build-skill-portfolio.py
scripts/skill_portfolio/*

portfolio-intents.yaml
portfolio-external.yaml
schemas/skill-portfolio.schema.json

assets/skill-portfolio-template.html

.gitignore
README.md
.github/workflows/validate-skills.yml

tests/ または evals/skill-portfolio/
```

実装時に既存 project-map renderer の UI / validation pattern を再利用できるか確認するが、architecture-map schema を portfolio schema として流用しない。architecture relation と portfolio lifecycle は別 contract である。

## v1 の受入基準

1. main の canonical Skill が人間の列挙なしで全件検出される。
2. HOTL が `MAIN / UNDER_DEVELOPMENT / LIMITED` と表示でき、その理由を rule result まで辿れる。
3. main Skill が active PR を持っても `Placement` と `Development Stage` を失わず、Activity だけが変わる。
4. design-only / planned / local-only candidate を区別できる。
5. private source を private mode で表示できる。
6. public mode が private source を collector に渡さない。
7. privacy fixture が public projection に混ざると生成が失敗する。
8. external source 取得失敗で Dashboard 全体は失敗せず、item freshness のみ `STALE` / `UNAVAILABLE` になる。
9. latest relevant SHA 以外の CI PASS を current readiness evidence に使わない。
10. relationship target を typed relation として検証できる。
11. Attention Queue に Critical / Action Required / Opportunity を区別して表示できる。
12. accepted known limitation は毎回 red alert にしない。
13. README は Dashboard の入口だけを示し、状態表を二重管理しない。
14. generated HTML / JSON は `.skill-portfolio/` 下にだけ出力され、Git 管理対象にならない。
15. Dashboard に write action が存在しない。
16. 通常の canonical Skill 更新で portfolio YAML の手編集を要求しない。

## 設計上の固定判断

- v1 は read-only。
- 対象は Skill + Skill 運用に直接関係する infrastructure。通常 project は対象外。
- state は単一 status ではなく `Placement / Development Stage / Readiness` の 3 軸。
- current work は `Activity`、観測時刻は `Freshness` として別管理。
- `MAIN` は完成を意味しない。
- HOTL は現状 `UNDER_DEVELOPMENT` と明示する。
- Dashboard を source of truth にしない。
- main canonical Skill の手動登録はしない。
- GitHub / repo から取れる情報を YAML に重複して保存しない。
- LLM の意味推測で status を決めない。
- Public build は private source を最初から読まない。
- generated Dashboard は Git に commit しない。
- score / percentage は使わない。
- known limitation と regression を区別する。
- Attention と incomplete state を区別する。
- database / persistent server を導入しない。

## 将来拡張候補

v1 完了後に必要性が確認された場合のみ検討する。

- runtime invocation / success metrics
- SkillOpt proposal status
- multiple project からの Skill usage telemetry
- historical trend
- notification / scheduled digest
- monitoring-subagents の current runtime snapshot integration
- external Skill trust review metadata
- GitHub Pages 等の public snapshot publication
- controlled write actions を別 governance layer から起動する control center

これらは v1 の scope に含めない。

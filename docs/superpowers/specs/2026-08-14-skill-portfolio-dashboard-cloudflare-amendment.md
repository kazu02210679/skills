# Skill Portfolio Dashboard Cloudflare 配信追補

## 位置付け

この文書は `docs/superpowers/specs/2026-08-14-skill-portfolio-dashboard-design.md` の配信方式を追補する。

元設計の次の原則は維持する。

- Dashboard は read-only。
- Dashboard / generated JSON は source of truth ではない。
- `Placement / Development Stage / Readiness` を主要状態とする。
- HOTL は現状 `MAIN / UNDER_DEVELOPMENT / LIMITED` と表示する。
- Public build は private source を最初から読まない。
- generated artifact を Git に commit しない。
- database / persistent application backend は導入しない。

変更点は、generated Dashboard を local preview に限定せず、Cloudflare へ自動 deploy して外出先から閲覧できるようにすることにある。

本追補と元設計が配信方式について矛盾する場合、本追補を優先する。

## 固定判断

v1 の canonical hosting path は **Cloudflare Workers Static Assets** とする。

Cloudflare Pages / GitHub Pages は v1 の canonical hosting path にはしない。

理由:

- static HTML / JSON / asset を Worker と一体で配信できる。
- Wrangler / GitHub Actions から deploy できる。
- Public / Private を別 Worker として明確に分離できる。
- Private Worker 全体を Cloudflare Access で保護できる。
- 将来 lightweight Worker logic を追加する場合にも同じ delivery model を維持できる。

## Public / Private deployment の分離

Public と Private を同一 Worker の path、query parameter、UI toggle で切り替えない。

必ず次のように別 deployment とする。

```text
Public projection
  -> Cloudflare Worker: skill-portfolio-public
  -> public hostname

Private projection
  -> Cloudflare Worker: skill-portfolio-private
  -> Cloudflare Access
  -> private hostname
```

最低限、次を分離する。

- Worker identity
- deployment target
- Cloudflare deploy credential
- build authority repository
- source credential
- Access boundary

## Public deployment

Public Dashboard の build authority は public `skills` repository とする。

```text
push to main
or scheduled refresh
or workflow_dispatch
        |
        v
GitHub Actions
        |
        +-- collect public Git / GitHub observations
        +-- collect registered public external observations
        +-- infer state
        +-- schema validation
        +-- public privacy validation
        +-- render static assets
        |
        v
wrangler deploy
        |
        v
skill-portfolio-public
```

外部 Skill の upstream は `skills` に commit がなくても変わるため、scheduled refresh を持つ。

標準 cadence は 6 時間程度を想定し、implementation plan で GitHub Actions の制約と運用コストを確認して確定する。

Public Worker 用 token は Public Worker の deploy に必要な最小権限へ限定し、Private credential と共有しない。

## Private deployment

Private Dashboard の build authority は public `skills` repository に置かない。`private-codex-toolkit` など Private repository 側で build する。

```text
private source push
or scheduled refresh
or workflow_dispatch
        |
        v
Private GitHub Actions
        |
        +-- checkout public skills
        +-- checkout allowed private sources
        +-- collect external observations
        +-- infer state
        +-- validate private projection
        +-- verify Cloudflare Access protection
        +-- render private static assets
        |
        v
wrangler deploy
        |
        v
skill-portfolio-private
        |
        v
Cloudflare Access
```

Public repository へ Private repository write token を置いて cross-repository refresh を即時化しない。

Public source の更新は Private scheduled build で取り込む。必要な場合のみ Private 側の `workflow_dispatch` を明示実行する。

## Cloudflare Access boundary

Private Worker は Cloudflare Access の self-hosted application として **Worker 全体**を保護する。

- Access policy は deny-by-default。
- 明示的に許可した identity だけ Allow する。
- `/private` のような path 分離を security boundary にしない。
- Public / Private view toggle を security boundary にしない。
- preview URL を使う場合も Access protection の対象にする。

Private Dashboard は認証済みユーザーがブラウザから閲覧できる。スマートフォンや外部PCからも通常の browser authentication 後に利用できることを v1 の要件に含める。

## Initial private bootstrap

Private data を含む最初の deploy 前に Access boundary を作る。

1. expected Private Worker identity / hostname を作成する。
2. private data を含まない placeholder asset のみ deploy する。
3. Cloudflare Access を Worker 全体へ設定する。
4. unauthenticated request が content を直接取得できないことを確認する。
5. CI から Access protection を事前確認できる状態を作る。
6. その後に初めて private projection を deploy する。

Access protection を確認できない場合は private projection を deploy しない。

## Deploy-time safety

Private deploy の preflight は最低限次を確認する。

- target Worker identity が expected Private Worker と一致する。
- Public Worker ではない。
- expected Access protection が対象 Worker を覆っている。
- credential が Private deployment 用である。
- private projection schema validation が通る。
- generated output に secret / credential-like value が含まれない。

Private deploy 後は unauthenticated probe を行う。

未認証 request が private content を直接取得できる場合は deployment failure とする。

Access protection が不明、target mismatch、credential mismatch の場合は fail closed し、existing last-known-good deployment を置換しない。

## Credential boundary

少なくとも次を分離する。

```text
Public Cloudflare deploy credential
Private Cloudflare deploy credential
Private source read credential
Access verification credential
```

Public repository に次を置かない。

- Private repository credential
- Private Cloudflare deploy credential
- Private Access configuration secret
- Private source list の非公開詳細

credential は YAML / generated JSON / HTML に書かず、CI secret store を利用する。

## Generated artifact

生成物は引き続き Git 管理しない。

local preview:

```text
.skill-portfolio/
  public/
    portfolio.json
    index.html
  private/
    portfolio.json
    index.html
```

CI では runner の temporary workspace に projection を生成し、Cloudflare deploy 後に破棄する。

Private projection を GitHub Actions artifact として upload しない。

「Git 管理しない」と「外部配信しない」は別である。Cloudflare Worker 上の static asset は deployment artifact であり source of truth ではない。

## Cloud-hosted view と local view

Cloud-hosted Private view から見えるのは、Private CI が観測可能な GitHub / repository / external 情報に限る。

PC 上だけにある local-only worktree、installed runtime、uncommitted file は Private CI から観測できない場合がある。その場合は `UNAVAILABLE` / last-known observation とし、推測しない。

local-only observation が必要なら local build を使う。

v1 では local machine から arbitrary local observation を Cloudflare へ upload する同期 protocol は作らない。

## README

ルート `README.md` は canonical Skill catalog のまま維持し、状態表を重複管理しない。

実装後の `Skill Portfolio` section は次を持つ。

- `skill-portfolio` Skill / README へのリンク
- Public Dashboard の stable URL
- Dashboard が generated projection である説明
- Public / Private の違い

Private Dashboard hostname は public README に載せなくてよい。Private repo または local Skill configuration から開く。

## Refresh cadence

### Public

- main push: automatic build / deploy
- schedule: external source refresh
- workflow_dispatch: immediate refresh / recovery

### Private

- Private build-authority repo main push: automatic build / deploy
- schedule: public / private / external source refresh
- workflow_dispatch: immediate refresh / recovery

単に Dashboard を閲覧する操作では deploy を起動しない。

`Skill Portfolioを開いて` は existing deployed Private Dashboard が健全ならそれを開く。

`Skill Portfolioを最新化して` のような明示指示がある場合だけ refresh workflow を起動できる。

## Dashboard UI の変更

元設計の dark-mode single-page UI を維持する。

Header は local 前提の `Refresh` button を主役にせず、次を表示する。

```text
Skill Portfolio
Private / Public
Last deployed observation: <time>
Source freshness: <summary>
```

Public / Private は UI toggle ではなく deployment identity を示す badge とする。

remote / mobile view を考慮し、narrow viewport では summary card を縦積みにし、inventory の詳細列は Detail Panel へ逃がす。

## Failure handling

### Cloudflare deploy failure

- Skill state を `DEGRADED` に連鎖させない。
- deployment health だけを degraded とする。
- last-known-good deployment を保持する。

### Access verification failure

- Private deploy を実行しない。
- existing deployment を置換しない。
- Critical Attention として表示可能な deployment event を残す。

### External source failure

- Dashboard 全体の deploy を原則継続する。
- item freshness を `STALE` / `UNAVAILABLE` とする。

### Public privacy violation

- Public deploy を fail closed する。
- redaction して成功扱いしない。

## CI / workflow 境界

Repository validation CI と Deployment workflow を分離する。

### Repository validation CI

決定論的 fixture / static contract のみ検証する。

- schema
- inference
- relation integrity
- privacy rules
- renderer data integrity
- Public / Private deployment config separation

### Public deployment workflow

ネットワークを利用して public GitHub / external observation を取得し、Public Worker へ deploy する。

### Private deployment workflow

Private source を読み、Access preflight を行った上で Private Worker へ deploy する。

Private projection は artifact upload しない。

## 実装ファイル追加

元設計の実装境界に加えて、次を想定する。

public repository:

```text
cloudflare/public/wrangler.jsonc
.github/workflows/deploy-skill-portfolio-public.yml
```

private build-authority repository:

```text
cloudflare/private/wrangler.jsonc
private portfolio source config
private deployment workflow
CI secrets
```

Public repository へ Private workflow 本体を置く必要はない。

## 追加受入基準

元設計の受入基準に次を追加する。

1. generated HTML / JSON は Git 管理されない。
2. Public projection を独立 Public Worker へ Workers Static Assets として deploy できる。
3. Private projection を別 Worker / 別 credential で deploy できる。
4. Private Worker は Cloudflare Access で Worker 全体が保護される。
5. unauthenticated request は private content を取得できない。
6. Access preflight failure 時は private projection を deploy しない。
7. Public repository に Private source / Private deploy credential を置かない。
8. Public / Private Worker ID が異なることを static contract で検証する。
9. deployment failure 時に last-known-good deployment を破壊しない。
10. scheduled refresh により external / cross-source update を日常的な手作業なしで取り込める。
11. mobile browser から主要 status / Attention / Detail を閲覧できる。
12. Dashboard UI には portfolio state を変更する write action がない。

## 将来拡張へ移すもの

次は v1 に入れない。

- Dashboard 内 Refresh button からの server-side trigger
- local-only observation の Cloudflare 同期
- runtime metrics
- historical DB
- notification push
- Dashboard からの Skill / PR / HOTL 操作

## 公式参考資料

- Cloudflare Workers Static Assets: https://developers.cloudflare.com/workers/static-assets/
- Workers Static Assets Get Started: https://developers.cloudflare.com/workers/static-assets/get-started/
- GitHub Actions for Workers: https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/
- Cloudflare Access application types / Worker protection: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/choose-application-type/
- Cloudflare Access policies: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/

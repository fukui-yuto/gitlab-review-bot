# GitLab MR 自動レビューツール 仕様書

> **目的**: Self-Managed GitLab の MR/Issue コメント欄に `/review` と書き込むと、指定テンプレートに沿って LLM が自動レビューを行い、結果を MR コメントとして投稿するツールを構築する。

---

## 1. プロジェクト概要

### 1.1 名称
`gitlab-review-bot`

### 1.2 ゴール
- MR/Issue上で `/review` コメントを起点に、Diff を LLM に送信してレビューコメントを自動投稿する。
- レビュー観点は YAML ベースのテンプレートで切り替え可能（コード品質 / セキュリティ / テスト・Docstring / 総合）。
- LLM プロバイダ（Gemini / OpenAI）は設定で切替可能。
- 社内プロキシ経由での外部API利用、Self-Managed GitLab、Docker (systemd管理) で安定稼働させる。

### 1.3 非ゴール
- 自動マージや自動コミット（レビューコメントの投稿のみ）。
- IDE 連携、ローカル CLI 機能（将来拡張）。
- ブランチ全体や履歴の解析（対象は MR の Diff のみ）。

---

## 2. 機能要件

| ID | 機能 | 概要 |
|---|---|---|
| F-01 | コマンドトリガ | MR/Issue ノートで `/review` を検知して起動 |
| F-02 | テンプレート指定 | `/review <template_name>` で観点を切替 |
| F-03 | テンプレート一覧 | `/review help` で利用可能テンプレートを返答 |
| F-04 | Diff 取得 | 対象MRの差分を GitLab API から取得 |
| F-05 | LLM レビュー実行 | テンプレートに基づきプロンプト生成 → LLM 呼び出し |
| F-06 | 結果投稿 | MRコメントとしてレビュー結果を投稿（Markdown） |
| F-07 | プロバイダ切替 | `gemini` / `openai` を設定/環境変数で選択 |
| F-08 | Issue連携 | Issue コメントの `/review` で関連MRを自動レビュー |
| F-09 | リトライ | LLM/GitLab API 呼び出し失敗時の指数バックオフ |
| F-10 | 重複抑止 | 同一MRで実行中のジョブがあれば抑止 |

### 2.1 コマンド仕様

```text
/review                     # デフォルトテンプレート (general) で実行
/review code_quality        # コード品質レビュー
/review security            # セキュリティ観点
/review test                # テスト・Docstring観点
/review general             # 総合レビュー
/review help                # 使い方表示
```

将来拡張: `/review code_quality --files=src/foo.py,src/bar.py`

### 2.2 MRコメントからの実行

MRのコメント欄で `/review` を投稿すると、そのMRの差分がレビューされます。

### 2.3 Issueコメントからの実行

Issueのコメント欄で `/review` を投稿すると、以下の2つが実行されます:

1. **Issue自体のレビュー**: Issue のタイトル・説明・ラベルの品質（明確さ、再現手順、受け入れ基準など）をLLMが評価し、改善提案をIssueコメントとして投稿。
2. **関連MRのコードレビュー**: そのIssueに関連付けられたオープンなMR全てのコード差分をレビュー。関連MRがない場合はIssueレビューのみ実行されます。

---

## 3. 非機能要件

| 区分 | 要件 |
|---|---|
| 性能 | 通常MR (差分 1,000行以下) で応答30秒以内 |
| 可用性 | 単一VM稼働。落ちたら systemd で自動再起動 |
| 拡張性 | LLMプロバイダの追加が30分以内で可能（Strategy パターン） |
| セキュリティ | トークン類は `.env`（600） or systemd EnvironmentFile。リポジトリにコミットしない |
| ロギング | 構造化ログ (JSON)、PIIなし、リクエスト相関ID付与 |
| 監査 | 誰がいつどのMRに `/review` を打ち、どのテンプレで実行したかを記録 |
| ネットワーク | 外部API は社内プロキシ経由（`HTTPS_PROXY`） |

---

## 4. 処理フロー

### 4.1 シーケンス（`/review` 実行時）

```text
User           GitLab          review-bot           LLM
 │ MRコメント    │                │                   │
 │  "/review"   │                │                   │
 ├─────────────►│                │                   │
 │              │ Note Webhook   │                   │
 │              ├───────────────►│                   │
 │              │                │ 署名検証(secret)  │
 │              │                │ 200 OK 即返却     │
 │              │◄───────────────┤                   │
 │              │                │ ジョブをQueueへ   │
 │              │                │                   │
 │              │  GET /merge_   │                   │
 │              │  requests/:iid │                   │
 │              │◄───────────────┤                   │
 │              │  GET /changes  │                   │
 │              │◄───────────────┤                   │
 │              │                │ プロンプト生成    │
 │              │                ├──────────────────►│
 │              │                │   レビュー結果    │
 │              │                │◄──────────────────┤
 │              │  POST /notes   │                   │
 │              │◄───────────────┤                   │
 │ MRに結果表示  │                │                   │
 │◄─────────────┤                │                   │
```

### 4.2 主要処理ステップ

1. **受信**: `/api/v1/webhook/gitlab` で `X-Gitlab-Token` を検証。
2. **イベント判定**: `object_kind == "note"` かつ `noteable_type` が `MergeRequest` or `Issue`。
3. **コマンド解析**: テンプレート名・引数を抽出。`help` なら即返答。
4. **Issue判定**: Issue の場合は (a) Issue自体をLLMでレビュー (b) 関連MRを検索し各MRのコードをレビュー。
5. **重複抑止**: `(project_id, mr_iid)` のキーで稼働中ジョブがあれば skip + 通知コメント。
6. **Diff取得**: `python-gitlab` で MR 情報と changes を取得。
7. **テンプレート読込**: `templates/{name}.yaml` を読み込み、プロンプト組み立て。
8. **LLM呼び出し**: 選択中プロバイダで非同期実行。タイムアウト/リトライ。
9. **結果整形**: テンプレ定義の出力フォーマットに整形（Markdown）。
10. **コメント投稿**: GitLab API で MR ノート作成。長文は分割投稿（3800字目安）。
11. **監査ログ**: `who / when / project / mr / template / status / tokens` を記録。

---

## 5. データモデル

### 5.1 設定 (`config/settings.yaml`)

```yaml
app:
  host: 0.0.0.0
  port: 8080
  log_level: INFO

gitlab:
  url: https://gitlab.example.com
  # token は環境変数 GITLAB_TOKEN から注入
  webhook_secret_env: GITLAB_WEBHOOK_SECRET
  ssl_verify: true
  ca_bundle: /etc/ssl/certs/company-ca.pem

llm:
  provider: gemini            # gemini | openai
  timeout_sec: 60
  max_retries: 3

  gemini:
    model: gemini-2.5-flash
    api_key_env: GEMINI_API_KEY
  openai:
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
    base_url: null            # 社内Azureなど使う場合のみ

review:
  default_template: general
  templates_dir: config/templates
  max_diff_lines: 5000        # これを超えるMRは要約モードへフォールバック
  max_files: 50
  comment_chunk_chars: 3800   # GitLabコメント分割閾値

network:
  http_proxy_env: HTTP_PROXY
  https_proxy_env: HTTPS_PROXY
  no_proxy_env: NO_PROXY
```

### 5.2 ドメインモデル

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ReviewCommand:
    template: str
    extra_args: dict[str, str]

@dataclass
class ReviewJob:
    project_id: int
    mr_iid: int
    triggered_by: str        # GitLab username
    command: ReviewCommand
    correlation_id: str

@dataclass
class FileDiff:
    old_path: str
    new_path: str
    diff: str
    is_new: bool
    is_deleted: bool
    is_renamed: bool

@dataclass
class ReviewResult:
    template: str
    summary: str
    sections: list[dict]
    raw_markdown: str
    tokens_used: int | None
```

---

## 6. レビューテンプレート設計

### 6.1 テンプレートファイルフォーマット

各テンプレートは YAML 1ファイル。共通スキーマ:

```yaml
# config/templates/<name>.yaml
name: code_quality                # 一意名（ファイル名と一致）
display_name: コード品質レビュー
description: 設計・バグ・可読性に焦点を当てたレビュー
version: 1

# プロンプト構築用
system_prompt: |
  あなたは経験豊富なシニアソフトウェアエンジニアです。
  以下の観点でMRをレビューしてください。
  ...

# レビュー観点（プロンプトに展開される）
checklist:
  - id: design
    label: 設計・アーキテクチャ
    points:
      - 単一責務になっているか
      - レイヤ分離が崩れていないか

# 出力フォーマット指定（LLMに守らせる）
output_format: |
  ## 概要
  ## 指摘事項
  ### {category}: {file}:{line}
  - **重要度**: high|medium|low
  ...

# 動作パラメータ
parameters:
  temperature: 0.2
  max_output_tokens: 4096
  include_full_diff: true
  truncate_diff_strategy: per_file_head_tail
```

### 6.2 標準テンプレート（4種）

| name | 目的 | 重点 |
|---|---|---|
| `general` | 総合レビュー（既定） | 品質・セキュリティ・テスト全領域を浅く広く |
| `code_quality` | 設計・バグ・可読性 | リファクタ提案 |
| `security` | セキュリティ・SAST視点 | 認証/認可、入力検証、秘密情報、依存脆弱性 |
| `test` | テスト・Docstring | カバレッジ漏れ、Docstring充実、テスタビリティ |

### 6.3 テンプレート追加手順

1. `config/templates/<name>.yaml` を作成。
2. 必須キー (`name`, `display_name`, `description`, `system_prompt`, `output_format`) を埋める。
3. コンテナ再起動で反映。
4. MRで `/review <name>` を実行して動作確認。

### 6.4 テンプレート検証

起動時に全テンプレを読み込み、Pydanticスキーマで検証。失敗時は起動失敗 + 構造化ログ出力。

---

## 7. エラー・例外設計

| 事象 | 対応 |
|---|---|
| Webhook署名不一致 | 401返却・ログ記録（投稿しない） |
| 不明テンプレ名 | MRコメントで使い方を返答 |
| Diff取得失敗 | 3回までリトライ、失敗時はエラーコメント投稿 |
| LLMタイムアウト | 設定回数までリトライ → 失敗コメント投稿 |
| LLMレスポンス壊れ | フォーマット崩れでも生レスポンスをそのまま投稿（先頭に注意書き） |
| 重複起動 | Skip通知コメント |
| 設定不備 | 起動失敗（Fail-Fast） |
| Issue関連MRなし | Issueレビューは実行。MRが無い旨をコメントしない（Issueレビュー結果のみ投稿） |

エラー通知コメント例:

```markdown
> :robot: **review-bot**: レビュー実行に失敗しました。
> - template: `code_quality`
> - reason: LLM timeout (3 retries)
> - correlation_id: `01J...`
> 管理者に correlation_id を伝えて確認を依頼してください。
```

---

## 8. GitLab連携

### 8.1 必要権限

- Project Access Token または Group Access Token（推奨: Bot ユーザに付与）。
- スコープ: `api`（最低限）。`read_repository` だけでは notes 作成不可。
- ロール: `Developer` 以上（コメント投稿のため）。

### 8.2 Webhook設定

- 対象プロジェクト or グループで Webhook 追加。
- URL: `https://<vm-host>:8080/api/v1/webhook/gitlab`
- Trigger: **Comments** のみ ON（他はOFF推奨）。
- Secret Token: ランダム32byte以上。`GITLAB_WEBHOOK_SECRET` と一致させる。
- SSL verification: 社内CAなら有効。

### 8.3 主要API利用

| 用途 | エンドポイント |
|---|---|
| MR取得 | `GET /projects/:id/merge_requests/:iid` |
| 変更取得 | `GET /projects/:id/merge_requests/:iid/changes` |
| ノート投稿 (MR) | `POST /projects/:id/merge_requests/:iid/notes` |
| ノート投稿 (Issue) | `POST /projects/:id/issues/:iid/notes` |
| Issue関連MR取得 | `GET /projects/:id/issues/:iid/related_merge_requests` |
| ユーザ確認 | `GET /user`（起動時疎通確認） |

### 8.4 コメント分割

GitLab はノート1件あたり実質的な上限がある（巨大すぎると体験劣化）。`comment_chunk_chars` (例: 3800文字) で分割し、`### Part 1/3` のヘッダを付与する。

---

## 9. ロギング・監査

- 全リクエストに `correlation_id` を付与。Webhook受信時に発行し、後段のログ・LLM呼び出しに伝播。
- 監査ログに以下を1行JSONで記録:
  ```json
  {"ts":"...","corr_id":"...","actor":"yuto","project":42,"mr":7,"template":"security","status":"succeeded","tokens":1234,"duration_ms":18234}
  ```
- ログには Diff 本体・LLMプロンプト本文を出さない（必要時はデバッグフラグで一時的に）。

---

## 10. セキュリティ

- Webhook Secret は GitLab UI と環境変数の両方で管理。Secret 変更時は両方同時更新（手順ドキュメント化）。
- LLM へ送る Diff は社内ポリシー要確認。**機微情報を含むリポジトリは利用申請制**にすることを推奨。
- 監査ログは別ボリュームに保管し、ローテーション（logrotate）。
- 起動時にトークンの存在チェック・GitLab疎通チェック（fail-fast）。

---

## 11. 受け入れ基準（Definition of Done）

- [x] `/review` で general テンプレが実行され、結果がMRに投稿される。
- [x] `/review code_quality` `/review security` `/review test` が動作する。
- [x] `/review help` で利用可能テンプレ一覧が返答される。
- [x] LLMプロバイダを `settings.yaml` で切替できる（Gemini <-> OpenAI）。
- [x] 不正なWebhookは 401 で拒否される。
- [x] 同一MRで `/review` 連打しても二重実行されない。
- [x] 設定/トークン不備で起動が失敗しfail-fastする。
- [x] `pytest` が緑、カバレッジ80%以上（対象モジュール）。
- [x] `docker compose up` で起動、systemd で自動再起動する。
- [x] Issue コメントの `/review` で関連MRを自動レビューできる。
- [x] テンプレ追加手順・Webhook設定手順・トラブルシュートが記載されている。

---

## 12. 用語

| 用語 | 説明 |
|---|---|
| MR | Merge Request |
| Note | GitLab MR/Issue上のコメント |
| テンプレート | レビュー観点と出力フォーマットを定義したYAML |
| コマンド | ノート本文中の `/review ...` 指示 |
| correlation_id | リクエスト追跡用の一意ID |

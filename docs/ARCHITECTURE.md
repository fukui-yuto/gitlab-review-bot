# アーキテクチャ設計書

## 1. 全体構成図

```text
   ┌──────────────────┐                 ┌──────────────────────────────┐
   │ Self-Managed     │  Note Webhook   │  Linux VM (社内)              │
   │ GitLab           ├────────────────►│  ┌────────────────────────┐  │
   │ (Project)        │  POST /webhook  │  │ Docker: review-bot     │  │
   └────────▲─────────┘                 │  │  - FastAPI (uvicorn)   │  │
            │   GitLab REST API         │  │  - Worker (asyncio)    │  │
            │   (notes / diffs)         │  └─────────┬──────────────┘  │
            └───────────────────────────┤            │ HTTPS (proxy)   │
                                        └────────────┼─────────────────┘
                                                     ▼
                                           ┌──────────────────┐
                                           │ 社内 HTTPS Proxy │
                                           └─────────┬────────┘
                                                     ▼
                                       ┌─────────────────────────┐
                                       │ Gemini API / OpenAI API │
                                       └─────────────────────────┘
```

## 2. 採用技術

| 層 | 技術 | 理由 |
|---|---|---|
| 言語 | Python 3.11+ | LLM SDKが充実 |
| Web | FastAPI + uvicorn | 非同期、軽量、型安全 |
| 非同期処理 | `asyncio` + `asyncio.Queue` | 外部MQ不要で社内運用簡素 |
| GitLab連携 | `python-gitlab` | 公式準拠で保守性◎ |
| LLM SDK | `google-genai`, `openai` | 公式SDK |
| 設定 | `pydantic-settings` + YAML | 型安全な設定管理 |
| ロギング | `structlog` | 構造化ログ |
| パッケージ管理 | `uv` | 高速・lock安定 |
| コンテナ | Docker | 社内標準想定 |
| 起動制御 | systemd (`docker compose`) | 再起動・依存関係管理 |
| テスト | `pytest`, `httpx`, `respx` | 単体・モック |
| Lint/Format | `ruff`, `mypy` | 一貫性 |

## 3. デプロイ構成

- **VM**: 社内Linux VM (Ubuntu 22.04+ 想定)
- **Runtime**: Docker Engine + Docker Compose v2
- **Process管理**: systemd unit が `docker compose up` を管理
- **公開ポート**: 8080 (内部のみ。GitLabからの到達性確保)
- **TLS**: 社内CA証明書を `/etc/ssl/certs` に配置、コンテナにマウント

## 4. ディレクトリ構成

```text
gitlab-review-bot/
├── README.md
├── .gitattributes
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml              # 本番用
├── docker-compose.test-gitlab.yml  # テスト用GitLab環境
├── .env.example
├── systemd/
│   └── gitlab-review-bot.service
├── config/
│   ├── settings.example.yaml
│   └── templates/
│       ├── general.yaml
│       ├── code_quality.yaml
│       ├── security.yaml
│       └── test.yaml
├── src/
│   └── review_bot/
│       ├── __init__.py
│       ├── main.py                # FastAPI entrypoint
│       ├── api/
│       │   ├── __init__.py
│       │   └── webhook.py         # /webhook/gitlab エンドポイント
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py          # 設定ロード (pydantic-settings)
│       │   ├── logging.py         # structlog 設定
│       │   └── security.py        # Webhook署名検証
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── command.py         # /review コマンド解析
│       │   └── models.py          # ReviewJob, ReviewResult 等
│       ├── services/
│       │   ├── __init__.py
│       │   ├── gitlab_client.py   # GitLab API ラッパ (MR + Issue)
│       │   ├── template_loader.py # YAMLテンプレ読込・検証
│       │   ├── prompt_builder.py  # プロンプト生成
│       │   ├── reviewer.py        # オーケストレーション
│       │   └── llm/
│       │       ├── __init__.py
│       │       ├── base.py        # LLMProvider 抽象基底
│       │       ├── gemini.py
│       │       ├── openai_provider.py
│       │       ├── mock_provider.py # テスト用モックプロバイダ
│       │       └── factory.py     # プロバイダ選択 (LLM_PROVIDER環境変数対応)
│       └── worker/
│           ├── __init__.py
│           └── queue.py           # asyncio ベースのワーカ + 重複抑止
├── config/
│   └── settings.test.yaml         # テスト用設定 (mock LLMプロバイダ)
├── scripts/
│   ├── run_tests.sh               # lint + pytest
│   ├── run_docker_test.sh         # 全自動Docker統合テスト + E2E
│   ├── run_e2e_test.sh            # E2Eテスト (手動)
│   ├── setup_and_run.py           # GitLab自動セットアップ (トークン/Webhook/テストデータ)
│   ├── start_bot.py               # review-botローカル起動
│   ├── e2e_review_test.py         # E2E自動テスト (/review投稿→応答確認)
│   ├── docker_inline_test.py      # コンポーネント統合テスト
│   └── setup_test_gitlab.py       # テストGitLabセットアップ (Docker内用)
├── docs/
│   ├── SPEC.md                    # 仕様書
│   ├── ARCHITECTURE.md            # アーキテクチャ設計書（本ドキュメント）
│   ├── TESTING.md                 # テストガイド
│   ├── SETUP.md                   # セットアップガイド
│   └── ROADMAP.md                 # ロードマップ
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_command.py
    │   ├── test_config.py
    │   ├── test_security.py
    │   ├── test_template_loader.py
    │   ├── test_prompt_builder.py
    │   ├── test_reviewer.py
    │   └── test_queue.py
    └── integration/
        ├── test_webhook_flow.py
        └── fixtures/
            ├── webhook_note_mr.json
            └── webhook_note_issue.json
```

## 5. コンポーネント設計

### 5.1 処理フローの内部構成

```text
   GitLab (Webhook: Note Event)
        │
        ▼
   FastAPI (api/webhook.py)
        │
        ├── X-Gitlab-Token 検証 (core/security.py)
        │
        ├── /review コマンド解析 (domain/command.py)
        │
        ├── noteable_type 判定
        │   ├── MergeRequest → enqueue_review()
        │   └── Issue → _handle_issue_review()
        │
        ▼
   Worker (worker/queue.py)
        │
        ├── [MR] 重複チェック (_active_jobs)
        │
        ├── [Issue] _handle_issue_review()
        │   ├── (1) Issue自体のレビュー
        │   │   ├── get_issue_info() → Issue情報取得
        │   │   ├── PromptBuilder: build_issue_user_prompt()
        │   │   ├── LLM: Issue品質レビュー生成
        │   │   └── GitLab API: Issueコメント投稿
        │   │
        │   └── (2) 関連MRのコードレビュー (0件以上)
        │       ├── get_issue_related_mrs()
        │       └── 各MRに対して _run_mr_review()
        │
        ▼
   Reviewer (services/reviewer.py)
        │
        ├── execute(): MRレビュー
        │   ├── help → テンプレート一覧をコメント投稿
        │   ├── unknown template → エラーコメント
        │   ├── GitLab API: get MR info + diffs
        │   ├── TemplateLoader: load template
        │   ├── PromptBuilder: build prompt
        │   │   ├── system_prompt ← template.system_prompt
        │   │   ├── user_prompt ← MR情報 + checklist + diffs + output_format
        │   │   └── diff truncation (per_file_head_tail / head_only)
        │   ├── LLMProvider: generate review (retry with backoff)
        │   └── GitLab API: post MR comment (chunked if > 3800 chars)
        │
        └── execute_issue_review(): Issueレビュー
            ├── PromptBuilder: build_issue_system_prompt() + build_issue_user_prompt()
            │   └── Issue情報 + ラベル + 関連MRタイトル → レビュー観点
            ├── LLMProvider: Issue品質レビュー生成 (retry with backoff)
            └── GitLab API: post Issue comment (chunked)
```

### 5.2 LLMプロバイダ抽象化

Strategy パターンで LLM プロバイダを差し替え可能にしている。

```text
           ┌──────────────────┐
           │   LLMProvider    │  (ABC)
           │  + generate()    │
           └────────┬─────────┘
                    │
         ┌──────────┼──────────┐
         │                     │
  ┌──────┴───────┐   ┌────────┴────────┐   ┌──────────────┐
  │ GeminiProvider│   │ OpenAIProvider  │   │ MockProvider │
  │ (google-genai)│   │ (openai SDK)   │   │ (テスト用)   │
  └──────────────┘   └────────────────┘   └──────────────┘
         ▲                     ▲                   ▲
         │                     │                   │
  ┌──────┴─────────────────────┴───────────────────┴──┐
  │              build_llm_provider()                  │
  │  LLM_PROVIDER 環境変数 or settings.llm.provider   │
  └────────────────────────────────────────────────────┘
```

### 5.3 プロンプト構築ロジック

`PromptBuilder` の責務:

1. テンプレートの `system_prompt` をシステムロールに配置。
2. `checklist` を箇条書きで展開しユーザロールに添付。
3. MRメタ情報（タイトル、説明、ターゲットブランチ）を付与。
4. ファイル別 Diff を以下フォーマットで添付:

```text
=== FILE: src/foo.py (modified) ===
@@ -10,7 +10,12 @@
（unified diff）
```

5. `max_diff_lines` を超える場合、`truncate_diff_strategy` に従い縮約。
   - `head_only`: 各ファイル先頭N行のみ残す
   - `per_file_head_tail`: 各ファイル先頭N行/末尾N行を残す（デフォルト）
6. 末尾に `output_format` を再掲してフォーマット遵守を促す。

### 5.4 プロキシ対応

- `httpx.AsyncClient(proxies=os.getenv("HTTPS_PROXY"))` を共通利用。
- Gemini SDK / OpenAI SDK が `httpx` を内部利用するため、環境変数 `HTTPS_PROXY` を尊重する設計。
- 一部SDKは明示的に `http_client` を渡す必要があるので各プロバイダ実装側で対応。

## 6. 監査ログ設計

全リクエストに `correlation_id` (UUID v4) を付与。Webhook受信時に発行し、後段すべてに伝播。

```json
{
  "ts": "2024-12-01T10:15:30Z",
  "corr_id": "550e8400-e29b-41d4-a716-446655440000",
  "actor": "yuto",
  "project": 42,
  "mr": 7,
  "template": "security",
  "status": "succeeded",
  "tokens": 1234,
  "duration_ms": 18234
}
```

ログには Diff 本体・LLMプロンプト本文を出さない（必要時はデバッグフラグで一時的に有効化）。

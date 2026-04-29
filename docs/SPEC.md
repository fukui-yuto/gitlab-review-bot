# GitLab MR 自動レビューツール 仕様書

## 1. 概要

`gitlab-review-bot` は Self-Managed GitLab の MR/Issue コメント欄に `/review` と書き込むことで、LLM による自動コードレビューを実行し、結果をコメントとして投稿するツールです。

## 2. 機能一覧

| ID | 機能 | 概要 |
|---|---|---|
| F-01 | コマンドトリガ | MR/Issue ノートで `/review` を検知して起動 |
| F-02 | テンプレート指定 | `/review <template_name>` で観点を切替 |
| F-03 | テンプレート一覧 | `/review help` で利用可能テンプレートを返答 |
| F-04 | Diff 取得 | 対象MRの差分を GitLab API から取得 |
| F-05 | LLM レビュー実行 | テンプレートに基づきプロンプト生成 → LLM 呼び出し |
| F-06 | 結果投稿 | MRコメントとしてレビュー結果を投稿(Markdown) |
| F-07 | プロバイダ切替 | `gemini` / `openai` を設定で選択 |
| F-08 | Issue連携 | Issue コメントの `/review` で関連MRを自動レビュー |
| F-09 | リトライ | LLM/GitLab API 呼び出し失敗時の指数バックオフ |
| F-10 | 重複抑止 | 同一MRで実行中のジョブがあれば抑止 |

## 3. コマンド仕様

```
/review                     # デフォルトテンプレート (general) で実行
/review code_quality        # コード品質レビュー
/review security            # セキュリティ観点
/review test                # テスト・Docstring観点
/review general             # 総合レビュー
/review help                # 使い方表示
```

### 3.1 MRコメントからの実行

MRのコメント欄で `/review` を投稿すると、そのMRの差分がレビューされます。

### 3.2 Issueコメントからの実行

Issueのコメント欄で `/review` を投稿すると、そのIssueに関連付けられたオープンなMR全てがレビューされます。関連MRがない場合はその旨を通知します。

## 4. アーキテクチャ

```
   GitLab (Webhook)
        │
        ▼
   FastAPI (webhook.py)
        │
        ├─── MR Note → enqueue_review()
        └─── Issue Note → find related MRs → enqueue_review() per MR
                │
                ▼
           Reviewer.execute()
                │
                ├── GitLab API: get MR info + diffs
                ├── TemplateLoader: load review template
                ├── PromptBuilder: build LLM prompt
                ├── LLMProvider: generate review
                └── GitLab API: post comment
```

### 4.1 技術スタック

| 層 | 技術 |
|---|---|
| 言語 | Python 3.11+ |
| Web | FastAPI + uvicorn |
| 非同期 | asyncio |
| GitLab | python-gitlab |
| LLM | google-genai, openai |
| 設定 | pydantic-settings + YAML |
| ログ | structlog (JSON) |
| パッケージ | uv |
| コンテナ | Docker + Docker Compose |

## 5. 設定

### 5.1 環境変数

| 変数 | 必須 | 説明 |
|---|---|---|
| `GITLAB_TOKEN` | Yes | GitLab API トークン (api スコープ) |
| `GITLAB_WEBHOOK_SECRET` | Yes | Webhook 認証シークレット |
| `GEMINI_API_KEY` | provider=gemini時 | Gemini API キー |
| `OPENAI_API_KEY` | provider=openai時 | OpenAI API キー |
| `HTTP_PROXY` / `HTTPS_PROXY` | No | プロキシ設定 |

### 5.2 settings.yaml

`config/settings.yaml` で詳細設定。`config/settings.example.yaml` を参照。

## 6. レビューテンプレート

4種の標準テンプレートを `config/templates/` に提供:

| テンプレート | 目的 |
|---|---|
| `general` | 品質・セキュリティ・テスト全領域の総合レビュー |
| `code_quality` | 設計・バグ・可読性 |
| `security` | OWASP Top 10 ベースのセキュリティレビュー |
| `test` | テストカバレッジ・Docstring |

### 6.1 テンプレート追加手順

1. `config/templates/<name>.yaml` を作成
2. 必須キー: `name`, `system_prompt`, `output_format`
3. コンテナ再起動で反映

## 7. エラーハンドリング

| 事象 | 対応 |
|---|---|
| Webhook署名不一致 | 401返却 |
| 不明テンプレ名 | MRコメントで利用可能テンプレ一覧を返答 |
| Diff取得失敗 | 3回リトライ → エラーコメント投稿 |
| LLMタイムアウト | 指数バックオフで再試行 → エラーコメント投稿 |
| 重複起動 | Skip通知 |

## 8. 非機能要件

| 区分 | 要件 |
|---|---|
| 性能 | 通常MR (1,000行以下) で応答30秒以内 |
| 可用性 | systemd で自動再起動 |
| セキュリティ | トークン類は環境変数管理、監査ログ記録 |
| ロギング | 構造化JSON、correlation_id 付与 |

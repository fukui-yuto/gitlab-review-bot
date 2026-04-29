# テストガイド

## 概要

GitLab Review Bot のテストは以下の3層で構成されます:

| 種別 | 範囲 | 自動/手動 |
|---|---|---|
| Unit | コマンドパーサ、テンプレローダ、プロンプトビルダ、署名検証、設定 | 全自動 |
| Integration | Webhook受信 → Queue投入 → ダミーLLM → ノート投稿 | 全自動 |
| E2E | ステージング GitLab で実MRに `/review` | スクリプト自動化 |

## テスト実行方法

### 全自動テスト (Unit + Integration)

```bash
# 方法1: テストスクリプト (lint + type check + pytest + coverage)
bash scripts/run_tests.sh

# 方法2: pytest のみ
pytest tests/ -v --cov=review_bot --cov-report=term-missing

# 方法3: CI モード (エラーで即終了)
bash scripts/run_tests.sh --ci
```

### 個別テスト実行

```bash
# Unit テストのみ
pytest tests/unit/ -v

# Integration テストのみ
pytest tests/integration/ -v

# 特定テストファイル
pytest tests/unit/test_command.py -v

# 特定テストケース
pytest tests/unit/test_command.py::TestParseReviewCommand::test_simple_review -v
```

### カバレッジレポート

```bash
pytest tests/ --cov=review_bot --cov-report=html:htmlcov
# ブラウザで htmlcov/index.html を開く
```

カバレッジ目標: コアロジック (`domain/`, `services/`) 80%以上

## テスト用 GitLab 環境の構築

### 1. GitLab CE の起動

```bash
docker compose -f docker-compose.test-gitlab.yml up -d
```

初回起動は GitLab の初期化に 3-5 分程度かかります。

### 2. 起動確認

```bash
# readiness チェック
curl http://localhost:8929/-/readiness

# ログ確認
docker logs test-gitlab -f
```

### 3. 自動セットアップ

`gitlab-setup` コンテナが自動的に以下を実行します:
- テストプロジェクト `review-bot-test` の作成
- テストブランチとMRの作成
- Webhook の設定

### 4. 手動アクセス

- URL: http://localhost:8929
- ユーザー: `root`
- パスワード: `reviewbot-test-2024`

### 5. E2E テスト

```bash
# GitLab + review-bot が起動した状態で:
export GITLAB_TOKEN="<root の personal access token>"
bash scripts/run_e2e_test.sh
```

## テスト構成

```
tests/
├── conftest.py                      # 共通フィクスチャ
├── unit/
│   ├── test_command.py              # /review コマンドパーサ
│   ├── test_config.py               # 設定ロード
│   ├── test_security.py             # Webhook 署名検証
│   ├── test_template_loader.py      # テンプレート読込・検証
│   └── test_prompt_builder.py       # プロンプト生成
└── integration/
    ├── test_webhook_flow.py         # Webhook → レビュー実行フロー
    └── fixtures/
        ├── webhook_note_mr.json     # MR コメント Webhook ペイロード
        └── webhook_note_issue.json  # Issue コメント Webhook ペイロード
```

## テスト方針

### Unit テスト
- 外部依存 (GitLab API, LLM API) は全てモック
- 境界値・異常系を重点的にテスト
- テンプレートファイルの実データを使用してスキーマ検証

### Integration テスト
- FastAPI の TestClient (httpx) を使用
- Webhook 認証、コマンド解析、レビュー実行の一連のフローを検証
- GitLab/LLM クライアントはモック

### E2E テスト
- 実際の GitLab CE (Docker) を使用
- `/review` コマンドの投稿からレビュー結果の投稿まで検証
- `scripts/run_e2e_test.sh` で自動化

## CI/CD での実行

```yaml
# .gitlab-ci.yml の例
test:
  image: python:3.11-slim
  script:
    - pip install uv
    - uv pip install --system -e ".[dev]"
    - bash scripts/run_tests.sh --ci
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

## トラブルシューティング

### テスト GitLab が起動しない
```bash
# ログ確認
docker logs test-gitlab
# メモリ確認 (GitLab は最低 4GB 推奨)
docker stats
```

### テストが import エラーで失敗する
```bash
# 開発依存をインストール
pip install -e ".[dev]"
# または
uv pip install --system -e ".[dev]"
```

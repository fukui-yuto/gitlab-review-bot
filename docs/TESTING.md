# テストガイド

## 概要

GitLab Review Bot のテストは以下の4層で構成されます:

| 種別 | 範囲 | 自動/手動 |
|---|---|---|
| Unit | コマンドパーサ、テンプレローダ、プロンプトビルダ、署名検証、設定、レビューア、キュー | 全自動 |
| Integration | Webhook受信(MR/Issue) → Queue投入 → ダミーLLM → ノート投稿 | 全自動 |
| Component | セキュリティ、コマンド、設定、テンプレート、プロンプトの結合テスト | 全自動 |
| E2E | 実GitLab CE + review-bot起動 → `/review` コメント → ボット応答確認 | 全自動 |

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

## 全自動 Docker 統合テスト + E2E

全て自動で実行できるオールインワンスクリプト:

```bash
bash scripts/run_docker_test.sh
```

このスクリプトは以下を順番に実行します:

1. **GitLab CE の起動確認** — Docker コンテナが起動していなければ自動起動
2. **テストデータ自動セットアップ** — トークン取得、プロジェクト/MR/Issue 作成、Webhook 登録
3. **コンポーネント統合テスト** — 22項目 (セキュリティ、コマンド、設定、テンプレート、プロンプト)
4. **pytest スイート** — 76テスト + カバレッジ
5. **review-bot 起動** — Mock LLM プロバイダで自動起動 (APIキー不要)
6. **E2E テスト** — GitLab上で実際に `/review` を実行し、ボット応答を確認

### Mock LLM プロバイダ

テスト時は `LLM_PROVIDER=mock` を使用すると、実際の LLM API キーなしでテストできます。
Mock プロバイダは固定のレビュー結果を返します。

```bash
# テスト用設定ファイル
config/settings.test.yaml   # provider: mock に設定済み
```

### セットアップスクリプト単体実行

```bash
# GitLab のセットアップのみ実行
python scripts/setup_and_run.py \
  --gitlab-url http://localhost:8929 \
  --password reviewbot-test-2024 \
  --bot-url http://host.docker.internal:8080 \
  --llm-provider mock
```

このスクリプトは以下を自動化します:
- GitLab OAuth トークンの取得
- テストプロジェクト・MR・Issue の作成
- ローカルネットワーク Webhook の許可設定
- Webhook の登録 (`host.docker.internal` 経由)
- `.env.test` ファイルの生成

### review-bot 単体起動

```bash
# .env.test を読み込んでローカル起動
python scripts/start_bot.py
```

### E2E テスト単体実行

```bash
# review-bot が起動した状態で:
python scripts/e2e_review_test.py \
  --gitlab-url http://localhost:8929 \
  --password reviewbot-test-2024 \
  --timeout 30
```

E2E テスト内容:
- MR で `/review` → ボットがレビュー結果をコメント
- MR で `/review help` → テンプレート一覧をコメント
- MR で `/review security` → セキュリティレビュー結果をコメント
- Issue で `/review` → Issue レビュー結果をコメント
- 手順書 Issue で `/review` → 手順書のレビュー結果をコメント

## テスト用 GitLab 環境の構築

### 1. GitLab CE の起動

```bash
docker compose -f docker-compose.test-gitlab.yml up -d
```

初回起動は GitLab の初期化に 3-5 分程度かかります。

> **注意**: `docker-compose.test-gitlab.yml` に `extra_hosts: host.docker.internal:host-gateway` が設定されています。
> これにより、GitLab コンテナからホストマシン上の review-bot にアクセスできます（Linux/Windows/Mac 対応）。

### 2. 起動確認

```bash
# readiness チェック
curl http://localhost:8929/-/readiness

# ログ確認
docker logs test-gitlab -f
```

### 3. 手動アクセス

- URL: http://localhost:8929
- ユーザー: `root`
- パスワード: `reviewbot-test-2024`

## テスト構成

```
tests/
├── conftest.py                      # 共通フィクスチャ
├── unit/
│   ├── test_command.py              # /review コマンドパーサ (15テスト)
│   ├── test_config.py               # 設定ロード (7テスト)
│   ├── test_security.py             # Webhook 署名検証 (5テスト)
│   ├── test_template_loader.py      # テンプレート読込・検証 (10テスト)
│   ├── test_prompt_builder.py       # プロンプト生成 MR+Issue (13テスト)
│   ├── test_reviewer.py             # レビューア MR+Issue (9テスト)
│   └── test_queue.py                # キュー MR/Issue/重複抑止 (7テスト)
└── integration/
    ├── test_webhook_flow.py         # Webhook → レビュー実行フロー MR+Issue (10テスト)
    └── fixtures/
        ├── webhook_note_mr.json     # MR コメント Webhook ペイロード
        └── webhook_note_issue.json  # Issue コメント Webhook ペイロード

scripts/
├── docker_inline_test.py            # コンポーネント統合テスト (22項目)
└── e2e_review_test.py               # E2E テスト (10項目)
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

### Component テスト
- `docker_inline_test.py` で実際のモジュールを組み合わせて検証
- セキュリティ、コマンドパーサ、設定、テンプレート、プロンプトビルダを統合的にテスト

### E2E テスト
- 実際の GitLab CE (Docker) + review-bot を使用
- `/review` コマンドの投稿からレビュー結果の投稿まで検証
- Mock LLM プロバイダを使用 (APIキー不要)
- MR レビュー、Issue レビュー、手順書レビューを自動検証

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

### E2E テストでボットが応答しない
```bash
# 1. ボットのヘルスチェック
curl http://localhost:8080/health

# 2. Webhook が正しいか確認
# GitLab → Settings → Webhooks で URL が
# http://host.docker.internal:8080/api/v1/webhook/gitlab になっているか

# 3. ボットのログ確認
cat /tmp/bot.log
```

### Windows で CRLF 警告が出る
`.gitattributes` で LF に統一されています。既存ファイルで警告が出る場合:
```bash
git add --renormalize .
```

# セットアップガイド

## 前提条件

- Python 3.11+
- Docker / Docker Compose v2
- Self-Managed GitLab (15.0+)
- LLM API キー (Gemini or OpenAI、テスト時は `mock` プロバイダで不要)

## クイックスタート

### 1. リポジトリクローン

```bash
git clone https://github.com/fukui-yuto/gitlab-review-bot.git
cd gitlab-review-bot
```

### 2. 環境変数設定

```bash
cp .env.example .env
# .env を編集して各値を設定:
#   GITLAB_TOKEN     - GitLab PAT (glpat-...) または OAuth トークン
#   LLM_PROVIDER     - gemini / openai / mock (テスト用)
#   GEMINI_API_KEY   - Gemini 使用時
#   OPENAI_API_KEY   - OpenAI 使用時
```

### 3. 設定ファイル

```bash
cp config/settings.example.yaml config/settings.yaml
# settings.yaml を環境に合わせて編集
```

### 4. 起動

```bash
docker compose up -d
```

### 5. GitLab Webhook 設定

1. GitLab プロジェクト → Settings → Webhooks
2. URL: `http://<bot-host>:8080/api/v1/webhook/gitlab`
3. Secret Token: `.env` の `GITLAB_WEBHOOK_SECRET` と同じ値
4. Trigger: **Comments** のみ ON
5. SSL verification: 環境に応じて設定

### 6. 動作確認

- MR のコメントで `/review help` を投稿 → テンプレート一覧が返答されれば成功。
- Issue のコメントで `/review` を投稿 → Issueレビュー + 関連MRのコードレビューが実行されれば成功。

### テスト環境の全自動セットアップ

テスト用GitLab CE を使って全自動でセットアップ・検証できます:

```bash
# 1. GitLab CE 起動
docker compose -f docker-compose.test-gitlab.yml up -d gitlab

# 2. 全自動セットアップ (トークン取得/プロジェクト作成/Webhook登録)
python scripts/setup_and_run.py

# 3. review-bot 起動 (Mock LLMプロバイダ、APIキー不要)
python scripts/start_bot.py

# 4. ブラウザで http://localhost:8929 にアクセス
#    root / reviewbot-test-2024 でログイン
#    MR や Issue で /review とコメントして動作確認
```

一括テスト:
```bash
bash scripts/run_docker_test.sh  # 全自動 (起動→セットアップ→テスト→E2E)
```

## 開発環境

```bash
# uv を使う場合
pip install uv
uv pip install --system -e ".[dev]"

# テスト実行
bash scripts/run_tests.sh
```

## 本番デプロイ (systemd)

```bash
# 1. アプリケーション配置
sudo mkdir -p /opt/gitlab-review-bot
sudo cp -r . /opt/gitlab-review-bot/
sudo cp systemd/gitlab-review-bot.service /etc/systemd/system/

# 2. ユーザー作成
sudo useradd -r -s /bin/false reviewbot
sudo chown -R reviewbot:reviewbot /opt/gitlab-review-bot

# 3. サービス有効化
sudo systemctl daemon-reload
sudo systemctl enable gitlab-review-bot
sudo systemctl start gitlab-review-bot
```

## Webhook設定の詳細

### 必要なトークン権限

- **スコープ**: `api` (最低限)
- **ロール**: `Developer` 以上
- 推奨: Bot ユーザーに付与した Project/Group Access Token
- **対応トークン形式**:
  - Personal Access Token (PAT): `glpat-` で始まるトークン
  - OAuth Access Token: `/oauth/token` エンドポイントで取得したトークン
  - ボットは自動的にトークン形式を判別します

### Webhook Trigger

- **Comments** のみ ON (他はOFF推奨)
- MR コメントと Issue コメントの両方に対応
- Issue コメントで `/review` を実行すると、Issue に関連付けられたオープンなMR全てが自動レビューされます

## テンプレート追加

1. `config/templates/<name>.yaml` を作成
2. 必須フィールド:
   - `name`: テンプレート名 (ファイル名と一致)
   - `display_name`: 表示名
   - `description`: 説明
   - `system_prompt`: LLM へのシステムプロンプト
   - `output_format`: 出力フォーマット指定
3. コンテナ再起動で反映

## トラブルシューティング

### Bot が応答しない
1. `docker logs gitlab-review-bot` でログ確認
2. `/health` エンドポイント確認: `curl http://localhost:8080/health`
3. Webhook 設定の URL と Secret が正しいか確認

### 401 エラー
- Webhook Secret Token が `.env` の値と一致しているか確認

### LLM タイムアウト
- `settings.yaml` の `llm.timeout_sec` を調整
- プロキシ設定を確認 (`HTTPS_PROXY`)

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
```

`.env` を編集して以下の値を設定してください:

| 変数 | 説明 | 例 |
|---|---|---|
| `GITLAB_URL` | GitLab インスタンスの URL | `https://gitlab.example.com` |
| `GITLAB_TOKEN` | GitLab PAT または OAuth トークン（[Step 1 参照](#step-1-personal-access-token-pat-の作成)） | `glpat-xxxxxxxxxxxx` |
| `GITLAB_WEBHOOK_SECRET` | Webhook 検証用の秘密文字列（[Step 3 参照](#step-3-webhook-secret-の準備)） | `openssl rand -hex 32` で生成 |
| `LLM_PROVIDER` | 使用する LLM プロバイダ | `gemini` / `openai` / `mock` |
| `GEMINI_API_KEY` | Gemini 使用時の API キー | [Google AI Studio](https://aistudio.google.com/apikey) で取得 |
| `OPENAI_API_KEY` | OpenAI 使用時の API キー | [OpenAI Platform](https://platform.openai.com/api-keys) で取得 |

> **注意**: `GITLAB_URL` はデフォルトで `http://localhost:8929`（テスト用）になっています。本番環境では必ず実際の GitLab URL に変更してください。

### 3. 設定ファイル

```bash
cp config/settings.example.yaml config/settings.yaml
```

`settings.yaml` の主要項目を環境に合わせて編集してください:

| 項目 | デフォルト値 | 説明 |
|---|---|---|
| `gitlab.url` | `http://localhost:8929` | `.env` の `GITLAB_URL` と同じ値を設定 |
| `gitlab.ssl_verify` | `false` | 本番では `true` に変更（正規の SSL 証明書がある場合） |
| `llm.provider` | `gemini` | `.env` の `LLM_PROVIDER` と同じ値を設定 |
| `llm.timeout_sec` | `60` | LLM の応答タイムアウト（秒） |
| `llm.gemini.model` | `gemini-2.5-flash` | 使用する Gemini モデル |
| `llm.openai.model` | `gpt-4o-mini` | 使用する OpenAI モデル |

### 4. 起動

```bash
docker compose up -d
```

### 5. GitLab 側の設定・動作確認

[GitLab 側の設定](#gitlab-側の設定) セクションの Step 1〜5 を実施してください。

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

## GitLab 側の設定

### Step 1: Personal Access Token (PAT) の作成

1. GitLab にログイン
2. 右上のアバター → **「Edit profile」**（プロフィール編集）
3. 左メニュー → **「Access Tokens」**
4. 以下を入力:

   | 項目 | 設定値 |
   |---|---|
   | **Token name** | `review-bot`（任意） |
   | **Expiration date** | 必要に応じて設定（空欄 = 無期限） |
   | **Scopes** | **`api`** にチェック |

5. **「Create personal access token」** をクリック
6. 表示された `glpat-xxxxxxxxxxxx` をコピーし、`.env` の `GITLAB_TOKEN` に設定

> **推奨**: 個人アカウントではなく Bot 用ユーザーを作成し、そのユーザーの PAT を使うと、レビューコメントが Bot 名義で投稿されます。

### Step 2: Bot ユーザーの権限設定

Bot ユーザー（または PAT を作成したユーザー）が対象プロジェクトで **Developer 以上** のロールを持っていることを確認してください。

1. 対象プロジェクト → **Settings** → **Members**
2. Bot ユーザーを追加し、ロールに **Developer** 以上を選択
3. **「Invite」** をクリック

### Step 3: Webhook Secret の準備

`GITLAB_WEBHOOK_SECRET` は GitLab から取得するものではなく、**自分で決める任意の秘密文字列** です。GitLab が Webhook を送信する際にこの値をヘッダーに含め、Bot 側で照合することでリクエストが正規の GitLab からのものか検証します。

ランダムな文字列を生成するのが推奨です:

```bash
# Linux / macOS
openssl rand -hex 32

# Python
python -c "import secrets; print(secrets.token_hex(32))"
```

生成した値を `.env` の `GITLAB_WEBHOOK_SECRET` に設定し、次の Step 4 の Webhook 登録画面でも **同じ値** を入力してください。

### Step 4: Webhook の登録

1. 対象プロジェクト → **Settings** → **Webhooks**
2. **「Add new webhook」** をクリック
3. 以下を設定:

   | 項目 | 設定値 |
   |---|---|
   | **URL** | `http://<bot-host>:8080/api/v1/webhook/gitlab` |
   | **Secret token** | `.env` の `GITLAB_WEBHOOK_SECRET` と同じ値 |
   | **Trigger** | **Comments** のみ ON（他は全て OFF） |
   | **SSL verification** | 自己証明書なら無効化、本番なら有効 |

4. **「Add webhook」** をクリック

### Step 5: 動作確認

Bot を起動した状態で:

1. MR を開き、コメントに **`/review help`** と投稿 → テンプレート一覧が返れば成功
2. **`/review`** と投稿 → コードレビューが実行される

## トークン詳細

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

## ネットワーク要件

Bot と GitLab の間で **双方向の通信** が必要です:

| 方向 | 用途 | ポート例 |
|---|---|---|
| **GitLab → Bot** | Webhook の送信 | Bot の `8080` ポートに到達できること |
| **Bot → GitLab** | API 呼び出し（diff 取得、コメント投稿等） | GitLab の `443` or `80` ポート |

- Bot を `127.0.0.1:8080` でリッスンしている場合、同一マシン上の GitLab からのみ到達可能です。別ホストの GitLab から Webhook を受けるには、`docker-compose.yml` の `ports` を `"0.0.0.0:8080:8080"` に変更するか、リバースプロキシを設定してください。
- ファイアウォールやセキュリティグループで上記ポートが開放されていることを確認してください。
- プロキシ環境の場合は `.env` の `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` を設定してください。

## トラブルシューティング

### Bot が応答しない
1. `docker logs gitlab-review-bot` でログ確認
2. `/health` エンドポイント確認: `curl http://localhost:8080/health`
3. Webhook 設定の URL と Secret が正しいか確認
4. GitLab から Bot へのネットワーク到達性を確認（[ネットワーク要件](#ネットワーク要件) 参照）

### 401 エラー
- `GITLAB_TOKEN` が正しく設定されているか確認（`glpat-` で始まる有効なトークン）
- トークンの **スコープ** に `api` が含まれているか確認
- トークンが **有効期限切れ** になっていないか確認
- Bot ユーザーが対象プロジェクトで **Developer 以上** のロールを持っているか確認

### 403 エラー（Webhook 検証失敗）
- GitLab の Webhook 設定の Secret Token と `.env` の `GITLAB_WEBHOOK_SECRET` が一致しているか確認

### LLM タイムアウト
- `settings.yaml` の `llm.timeout_sec` を調整
- プロキシ設定を確認 (`HTTPS_PROXY`)

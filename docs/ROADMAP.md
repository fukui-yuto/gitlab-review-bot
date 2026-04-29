# ロードマップ

## フェーズ一覧

| フェーズ | 内容 | 状態 |
|---|---|---|
| P0 | 雛形作成、`/review` で general テンプレが動く | Done |
| P1 | テンプレ4種完備、エラーハンドリング、監査ログ | Done |
| P2 | プロバイダ切替（Gemini/OpenAI）、コメント分割、Issue連携 | Done |
| P3 | 認可制御（特定グループのみ）、`--files` 引数 | Planned |
| P4 | Inline Comment（行コメント）対応、複数MR並列実行制御 | Planned |
| P5 | K8sへの移行（Helm Chart 追加） | Planned |

---

## P0: 基本動作 (Done)

- [x] リポジトリ初期化 (`pyproject.toml`, テスト基盤)
- [x] `/review` コマンドパーサ (`domain/command.py`)
- [x] 設定管理 (`core/config.py`, pydantic-settings + YAML)
- [x] テンプレートローダ (`services/template_loader.py`)
- [x] general テンプレートで基本動作

## P1: テンプレート・エラーハンドリング (Done)

- [x] 4種テンプレート (general, code_quality, security, test)
- [x] `/review help` でテンプレート一覧返答
- [x] 不明テンプレート時のエラーメッセージ
- [x] LLM呼び出し失敗時のリトライ（指数バックオフ）
- [x] エラー時のMRコメント通知
- [x] 構造化ログ (structlog, correlation_id)

## P2: プロバイダ・運用機能 (Done)

- [x] Gemini / OpenAI プロバイダ切替 (Strategy パターン)
- [x] コメント分割投稿 (3800字閾値)
- [x] 同一MR重複実行抑止
- [x] Issue コメントからの `/review` (関連MR自動レビュー)
- [x] Webhook署名検証
- [x] Docker / Docker Compose / systemd
- [x] テスト用GitLab環境 (docker-compose.test-gitlab.yml)
- [x] 自動テスト (76 unit + 10 E2E テスト, カバレッジ93%)
- [x] Mock LLMプロバイダ (APIキー不要でテスト可能)
- [x] 全自動E2Eテスト (セットアップ → bot起動 → `/review` 実行 → 応答確認)

## P3: 認可・フィルタリング (Planned)

- [ ] 許可ユーザ/ロールの制限 (`allowed_groups`, `allowed_users`)
- [ ] `--files=src/foo.py` 引数でレビュー対象ファイルを限定
- [ ] ブランチパターンによる拒否リスト
- [ ] 巨大バイナリ拡張子の除外設定

## P4: 高度なレビュー機能 (Planned)

- [ ] Inline Comment（行単位のコメント）対応
- [ ] 複数MRの並列実行制御（ワーカー数制限）
- [ ] LLMレスポンスのフォーマット検証・自動修正
- [ ] レビュー結果のキャッシュ（同一Diffなら再利用）

## P5: スケーラビリティ (Planned)

- [ ] Kubernetes対応 (Helm Chart)
- [ ] Redis/RabbitMQ ベースのジョブキュー
- [ ] 水平スケーリング対応
- [ ] Prometheus メトリクス公開

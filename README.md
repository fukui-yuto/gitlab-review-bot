# gitlab-review-bot

GitLab MR/Issue コメントで `/review` と書くだけで、LLM が自動コードレビューを実行するボットです。

## 特徴

- MR コメントでもIssue コメントでも `/review` で自動レビュー
- 4種のレビューテンプレート (総合 / コード品質 / セキュリティ / テスト)
- Gemini / OpenAI 切替対応
- Docker + systemd で安定運用

## クイックスタート

```bash
cp .env.example .env        # 環境変数を設定
cp config/settings.example.yaml config/settings.yaml
docker compose up -d
```

## コマンド

```
/review              # 総合レビュー
/review code_quality # コード品質レビュー
/review security     # セキュリティレビュー
/review test         # テスト・Docstringレビュー
/review help         # 使い方表示
```

## ドキュメント

- [セットアップガイド](docs/SETUP.md)
- [テストガイド](docs/TESTING.md)
- [仕様書](docs/SPEC.md)

## 開発

```bash
pip install -e ".[dev]"
bash scripts/run_tests.sh
```

## ライセンス

Private

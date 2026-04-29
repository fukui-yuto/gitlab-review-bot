"""Mock LLM provider for testing.

Parses the prompt content and generates a realistic, detailed review
that demonstrates what a real LLM review would look like.
"""

from __future__ import annotations

import re

from review_bot.services.llm.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> LLMResponse:
        if "Issue情報" in user_prompt:
            text = self._build_issue_review(user_prompt)
        else:
            text = self._build_mr_review(user_prompt)
        return LLMResponse(text=text, input_tokens=500, output_tokens=1200)

    def _build_mr_review(self, user_prompt: str) -> str:
        title = _extract(user_prompt, r"\*\*タイトル\*\*:\s*(.+)")
        files = re.findall(r"=== FILE:\s*(\S+)", user_prompt)
        has_divide = "divide" in user_prompt or "/ b" in user_prompt
        has_todo = "TODO" in user_prompt

        parts = [
            "## レビュー結果\n",
            "### 総合評価",
            f"MR「{title}」のコードレビューを実施しました。",
            "",
        ]

        findings: list[str] = []

        if has_divide:
            findings.append(
                "1. **[High] ゼロ除算の未処理**\n"
                "   - **ファイル**: `test_app.py` → `divide(a, b)`\n"
                "   - **問題**: 引数 `b` が `0` の場合に `ZeroDivisionError` が発生します。\n"
                "     本番で呼び出された場合、500エラーやプロセスクラッシュの原因になります。\n"
                "   - **改善案**:\n"
                "     ```python\n"
                "     def divide(a, b):\n"
                "         if b == 0:\n"
                "             raise ValueError(\"divisor must not be zero\")\n"
                "         return a / b\n"
                "     ```"
            )

        if has_todo:
            findings.append(
                "2. **[Medium] TODOコメントの残存**\n"
                "   - **問題**: `# TODO: add error handling` が残っています。\n"
                "     MRとしてマージする前にTODOを解消するか、\n"
                "     別Issueとして起票してからマージすべきです。\n"
                "   - **改善案**: TODOをIssueに起票し、Issue番号をコメントに記載"
            )

        for f in files:
            if f.endswith(".py"):
                findings.append(
                    f"{len(findings)+1}. **[Low] docstringの欠如** (`{f}`)\n"
                    f"   - **問題**: 関数に docstring がありません。\n"
                    f"   - **改善案**: 各公開関数に引数・戻り値・例外を記載した docstring を追加"
                )
                break

        findings.append(
            f"{len(findings)+1}. **[Info] 型アノテーションの欠如**\n"
            "   - **問題**: 関数の引数・戻り値に型アノテーションがありません。\n"
            "   - **改善案**: `def divide(a: float, b: float) -> float:` のように型を明示"
        )

        parts.append("### 指摘事項\n")
        parts.extend(findings)
        parts.append("")

        parts.append("### 良い点")
        parts.append("- 関数が小さく単一責務に分かれている")
        parts.append("- 命名が直感的で可読性が高い")
        parts.append("")
        parts.append("---")
        parts.append("*このレビューは review-bot (mock) によって自動生成されました。*")

        return "\n".join(parts)

    def _build_issue_review(self, user_prompt: str) -> str:
        title = _extract(user_prompt, r"\*\*タイトル\*\*:\s*(.+)")
        labels = _extract(user_prompt, r"\*\*ラベル\*\*:\s*(.+)")
        description = _extract_block(user_prompt, r"\*\*説明\*\*:\n([\s\S]*?)(?=\n- \*\*ラベル)")
        is_procedure = "手順" in user_prompt
        is_bug = "バグ" in user_prompt or "bug" in labels.lower()

        if is_procedure:
            return self._procedure_review(title, description, labels)
        elif is_bug:
            return self._bug_review(title, description, labels)
        else:
            return self._general_issue_review(title, description, labels)

    def _procedure_review(self, title: str, description: str, labels: str) -> str:
        has_ip = bool(re.search(r"\d+\.\d+\.\d+\.\d+", description))
        has_hostname = bool(re.search(r"(サーバー名|ホスト名|hostname)\s*[:：]", description, re.I))
        has_ssh = "ssh" in description.lower()
        has_user = bool(re.search(r"(実行ユーザー|sudo|root|作業ユーザー)", description))
        has_rollback = "ロールバック" in description or "切り戻し" in description
        has_rollback_criteria = bool(
            re.search(r"(判断基準|判断条件|いつ.*(戻す|ロールバック))", description)
        )
        has_time_estimate = bool(re.search(r"(所要時間|目安|分|時間)", description))
        has_verification = bool(
            re.search(r"(確認事項|確認コマンド|ヘルスチェック|動作確認)", description)
        )
        has_contact = bool(re.search(r"(連絡先|エスカレーション|緊急連絡)", description))
        has_approval = bool(re.search(r"(承認|レビュー|確認者)", description))
        has_backup = bool(re.search(r"(バックアップ|スナップショット|退避)", description))
        has_env = bool(
            re.search(r"(ステージング|staging|production|本番|環境)", description, re.I)
        )
        has_absolute_path = bool(re.search(r"(/opt/|/var/|/etc/|/home/|C:\\)", description))
        has_expected_output = bool(
            re.search(r"(期待.*出力|出力例|結果.*表示|が表示される)", description)
        )

        criticals: list[str] = []
        highs: list[str] = []
        mediums: list[str] = []
        lows: list[str] = []

        if not has_ip and not has_hostname:
            criticals.append(
                "**対象サーバーが未特定**\n"
                "   - **現状**: サーバー名・IPアドレス・ホスト名の記載がありません。\n"
                "   - **問題**: 作業者が誤ったサーバーで実行するリスクがあります。\n"
                "   - **改善案**: 以下のように対象環境を明記してください:\n"
                "     ```\n"
                "     ## 対象環境\n"
                "     - サーバー: app-prod-01 (10.0.1.100)\n"
                "     - 踏み台: bastion.example.com\n"
                "     - 接続方法: ssh -J bastion app-prod-01\n"
                "     ```"
            )

        if not has_user:
            criticals.append(
                "**実行ユーザーの未指定**\n"
                "   - **現状**: 各コマンドをどのユーザーで実行するか記載がありません。\n"
                "   - **問題**: rootで実行すべき箇所とアプリユーザーで実行すべき箇所の混同は\n"
                "     権限エラーやセキュリティ事故の原因になります。\n"
                "   - **改善案**: 各コマンドの先頭に実行ユーザーを明記:\n"
                "     ```bash\n"
                "     # rootで実行\n"
                "     $ sudo systemctl restart app\n"
                "     \n"
                "     # deployユーザーで実行\n"
                "     $ cd /opt/app && git pull\n"
                "     ```"
            )

        if has_rollback and not has_rollback_criteria:
            highs.append(
                "**ロールバック判断基準の欠如**\n"
                "   - **現状**: ロールバック手順は記載されていますが、\n"
                "     「いつロールバックすべきか」の判断基準がありません。\n"
                "   - **改善案**: 以下のような判断基準を追加:\n"
                "     ```\n"
                "     ## ロールバック判断基準\n"
                "     以下のいずれかに該当する場合、即座にロールバックを実施:\n"
                "     - ヘルスチェックが3回連続で失敗\n"
                "     - エラーレートが5%を超過\n"
                "     - レスポンスタイムが3秒を超過\n"
                "     ```"
            )

        if not has_rollback:
            criticals.append(
                "**ロールバック手順の欠如**\n"
                "   - **現状**: 失敗時の切り戻し手順が記載されていません。\n"
                "   - **問題**: 本番作業でロールバック手順がないのは重大なリスクです。\n"
                "   - **改善案**: 各主要ステップに対するロールバック手順を追加"
            )

        if not has_ssh and "ssh" not in description.lower():
            highs.append(
                "**アクセス方法の未記載**\n"
                "   - **現状**: サーバーへの接続方法（SSH、踏み台経由等）が記載されていません。\n"
                "   - **改善案**: 接続コマンドを具体的に記載（踏み台、ポート番号含む）"
            )

        if not has_backup:
            highs.append(
                "**バックアップ手順の欠如**\n"
                "   - **現状**: 作業前のバックアップ/スナップショット取得手順がありません。\n"
                "   - **改善案**: 作業前に以下を追加:\n"
                "     ```bash\n"
                "     # 作業前バックアップ\n"
                "     pg_dump -Fc mydb > /backup/mydb_$(date +%Y%m%d_%H%M%S).dump\n"
                "     ```"
            )

        if not has_time_estimate:
            mediums.append(
                "**所要時間の未記載**\n"
                "   - **現状**: 各ステップおよび全体の所要時間が記載されていません。\n"
                "   - **改善案**: 各セクションに所要時間を追加 (例: `[所要時間: 約5分]`)"
            )

        if not has_contact:
            mediums.append(
                "**緊急連絡先の未記載**\n"
                "   - **現状**: 問題発生時の連絡先・エスカレーションパスがありません。\n"
                "   - **改善案**: 連絡先セクションを追加:\n"
                "     ```\n"
                "     ## 緊急連絡先\n"
                "     - 1次: @on-call-engineer (Slack: #ops-alert)\n"
                "     - 2次: インフラチームリーダー (内線: xxxx)\n"
                "     ```"
            )

        if not has_expected_output:
            mediums.append(
                "**期待結果の未記載**\n"
                "   - **現状**: 各ステップ実行後の期待される出力が記載されていません。\n"
                "   - **改善案**: 各コマンドの後に期待出力を追加:\n"
                "     ```\n"
                "     $ curl http://localhost:8080/health\n"
                "     # 期待出力: {\"status\":\"ok\"}\n"
                "     ```"
            )

        if not has_approval:
            lows.append(
                "**承認フローの未定義**: 実行前に誰の承認が必要か記載がありません"
            )

        if not has_env:
            lows.append(
                "**環境の明示なし**: ステージング/本番の区別が明記されていません"
            )

        # Determine overall rating
        if criticals:
            rating = "🔴 差し戻し推奨"
            summary = "本番作業に必要な情報が不足しており、このままでは安全に実行できません。"
        elif highs:
            rating = "⚠️ 要改善"
            summary = "手順としての骨格はありますが、重要な情報が欠けています。"
        else:
            rating = "✅ 承認可能（軽微な改善推奨）"
            summary = "基本的な手順は整っています。"

        parts = [
            "## Issue レビュー結果\n",
            "### 総合評価",
            f"**評価**: {rating}\n",
            summary,
            "",
            "### 指摘事項\n",
        ]

        parts.append("#### 🔴 Critical（対応必須）\n")
        if criticals:
            for i, c in enumerate(criticals, 1):
                parts.append(f"{i}. {c}\n")
        else:
            parts.append("該当なし\n")

        parts.append("#### 🟡 High（強く推奨）\n")
        if highs:
            for i, h in enumerate(highs, 1):
                parts.append(f"{i}. {h}\n")
        else:
            parts.append("該当なし\n")

        parts.append("#### 🔵 Medium（推奨）\n")
        if mediums:
            for i, m in enumerate(mediums, 1):
                parts.append(f"{i}. {m}\n")
        else:
            parts.append("該当なし\n")

        parts.append("#### ⚪ Low / Info（参考）\n")
        if lows:
            for i, lo in enumerate(lows, 1):
                parts.append(f"{i}. {lo}\n")
        else:
            parts.append("該当なし\n")

        # Good points
        parts.append("### 良い点")
        goods: list[str] = []
        if has_rollback:
            goods.append("- ロールバック手順が記載されている")
        if has_verification:
            goods.append("- 確認事項/ヘルスチェックが含まれている")
        if "```" in description:
            goods.append("- コマンドがコードブロックで記載されており、コピペしやすい")
        if re.search(r"^#{1,3}\s", description, re.MULTILINE):
            goods.append("- セクション分けされており構造が明確")
        if re.search(r"- \[[ x]\]", description):
            goods.append("- チェックリスト形式で確認漏れを防止できる")
        if not goods:
            goods.append("- 手順の大まかな流れは記載されている")
        parts.extend(goods)

        parts.append("")
        parts.append("---")
        parts.append("*このレビューは review-bot (mock) によって自動生成されました。*")

        return "\n".join(parts)

    def _bug_review(self, title: str, description: str, labels: str) -> str:
        has_steps = bool(re.search(r"(再現手順|手順|steps)", description, re.I))
        has_expected = bool(re.search(r"(期待.*動作|expected)", description, re.I))
        has_actual = bool(re.search(r"(実際.*動作|actual|発生)", description, re.I))
        has_env_info = bool(
            re.search(r"(バージョン|version|OS|ブラウザ|環境)", description, re.I)
        )
        has_screenshot = bool(
            re.search(r"(スクリーンショット|screenshot|画像|!\[)", description, re.I)
        )
        has_error = bool(
            re.search(r"(エラー|error|exception|stack|traceback)", description, re.I)
        )

        criticals: list[str] = []
        highs: list[str] = []
        mediums: list[str] = []

        if not has_steps:
            criticals.append(
                "**再現手順の欠如**\n"
                "   - **問題**: ステップバイステップの再現手順がありません。\n"
                "   - **改善案**: 番号付きリストで具体的な手順を記載"
            )
        if not has_expected:
            highs.append(
                "**期待される動作の未記載**\n"
                "   - **問題**: 正常時にどう動くべきかが不明です。"
            )
        if not has_actual:
            highs.append(
                "**実際の動作の未記載**\n"
                "   - **問題**: 実際に何が起きているか具体的に記載されていません。"
            )
        if not has_env_info:
            mediums.append(
                "**環境情報の不足**: OS、ブラウザ、バージョン等の情報がありません。"
            )
        if not has_error:
            mediums.append(
                "**エラーメッセージの未記載**: エラーメッセージやログがあれば記載してください。"
            )

        rating = "🔴 差し戻し推奨" if criticals else ("⚠️ 要改善" if highs else "✅ 承認可能")

        parts = [
            "## Issue レビュー結果\n",
            "### 総合評価",
            f"**評価**: {rating}\n",
            "",
            "### 指摘事項\n",
            "#### 🔴 Critical（対応必須）\n",
        ]
        if criticals:
            for i, c in enumerate(criticals, 1):
                parts.append(f"{i}. {c}\n")
        else:
            parts.append("該当なし\n")

        parts.append("#### 🟡 High（強く推奨）\n")
        if highs:
            for i, h in enumerate(highs, 1):
                parts.append(f"{i}. {h}\n")
        else:
            parts.append("該当なし\n")

        parts.append("#### 🔵 Medium（推奨）\n")
        if mediums:
            for i, m in enumerate(mediums, 1):
                parts.append(f"{i}. {m}\n")
        else:
            parts.append("該当なし\n")

        parts.append("### 良い点")
        if has_screenshot:
            parts.append("- スクリーンショットが添付されている")
        if has_steps:
            parts.append("- 再現手順が記載されている")
        if has_error:
            parts.append("- エラーメッセージが記載されている")
        if not (has_screenshot or has_steps or has_error):
            parts.append("- Issue が起票されたこと自体は良い (問題の可視化)")

        parts.append("")
        parts.append("---")
        parts.append("*このレビューは review-bot (mock) によって自動生成されました。*")
        return "\n".join(parts)

    def _general_issue_review(self, title: str, description: str, labels: str) -> str:
        has_acceptance = bool(
            re.search(r"(受け入れ|完了条件|definition.*done|acceptance)", description, re.I)
        )
        has_labels = labels and labels != "(なし)"
        desc_length = len(description)

        highs: list[str] = []
        mediums: list[str] = []

        if desc_length < 50:
            highs.append(
                "**説明が不十分**\n"
                "   - **現状**: 説明が非常に短く、背景や目的が読み取れません。\n"
                "   - **改善案**: 背景、目的、期待される結果を具体的に記載"
            )
        if not has_acceptance:
            highs.append(
                "**受け入れ基準の欠如**\n"
                "   - **問題**: 完了条件が定義されていません。\n"
                "   - **改善案**: チェックリスト形式で受け入れ基準を追加"
            )
        if not has_labels:
            mediums.append(
                "**ラベルの未設定**: 優先度やカテゴリのラベルを付与してください。"
            )

        rating = "⚠️ 要改善" if highs else "✅ 承認可能"
        parts = [
            "## Issue レビュー結果\n",
            "### 総合評価",
            f"**評価**: {rating}\n",
            "",
            "### 指摘事項\n",
            "#### 🟡 High（強く推奨）\n",
        ]
        if highs:
            for i, h in enumerate(highs, 1):
                parts.append(f"{i}. {h}\n")
        else:
            parts.append("該当なし\n")
        parts.append("#### 🔵 Medium（推奨）\n")
        if mediums:
            for i, m in enumerate(mediums, 1):
                parts.append(f"{i}. {m}\n")
        else:
            parts.append("該当なし\n")

        parts.append("### 良い点")
        if has_acceptance:
            parts.append("- 受け入れ基準が定義されている")
        if has_labels:
            parts.append("- 適切なラベルが付与されている")
        if desc_length >= 50:
            parts.append("- 説明に十分な情報量がある")
        if not (has_acceptance or has_labels or desc_length >= 50):
            parts.append("- Issueが起票されたこと自体は良い")

        parts.append("")
        parts.append("---")
        parts.append("*このレビューは review-bot (mock) によって自動生成されました。*")
        return "\n".join(parts)


def _extract(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def _extract_block(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

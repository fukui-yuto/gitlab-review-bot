"""Mock LLM provider for testing. Returns a fixed review response."""

from __future__ import annotations

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
        # Detect if this is an Issue review or MR review
        if "Issue" in system_prompt or "Issue" in user_prompt:
            text = self._issue_review()
        else:
            text = self._mr_review()
        return LLMResponse(text=text, input_tokens=100, output_tokens=200)

    @staticmethod
    def _mr_review() -> str:
        return (
            "## レビュー結果 (Mock)\n\n"
            "### 1. 総合評価\n"
            "テスト用のモックレビューです。実際のLLMは使用していません。\n\n"
            "### 2. 指摘事項\n"
            "- **[低]** `divide(a, b)` でゼロ除算の例外処理がありません。\n"
            "- **[情報]** docstring の追加を推奨します。\n\n"
            "### 3. 良い点\n"
            "- コードがシンプルで読みやすいです。\n\n"
            "---\n"
            "*このレビューは review-bot (mock) によって自動生成されました。*"
        )

    @staticmethod
    def _issue_review() -> str:
        return (
            "## Issue レビュー結果 (Mock)\n\n"
            "### 1. タイトル\n"
            "明確で分かりやすいタイトルです。\n\n"
            "### 2. 説明\n"
            "具体的な説明が記載されています。\n\n"
            "### 3. 受け入れ基準\n"
            "明確な受け入れ基準の追加を推奨します。\n\n"
            "---\n"
            "*このレビューは review-bot (mock) によって自動生成されました。*"
        )

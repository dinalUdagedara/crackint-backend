"""
Unit tests for Session Q&A agent (question generation and answer evaluation).
Mocks OpenAI so no API key or network required.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.fallback import FALLBACK_QUESTION_BANK, pick_fallback_question
from app.agents.session_qa_agent import (
    _is_session_qa_available,
    generate_next_question,
    get_suggested_difficulty,
    evaluate_answer,
    summarize_session_feedback,
    QuestionGenerationResult,
    AnswerEvaluationResult,
    SessionSummaryResult,
)


class TestSessionQAAvailability:
    """Test _is_session_qa_available."""

    @patch("app.agents.session_qa_agent.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        mock_settings.SESSION_QA_AGENT_ENABLED = False
        mock_settings.OPENAI_API_KEY = "sk-fake"
        assert _is_session_qa_available() is False

    @patch("app.agents.session_qa_agent.settings")
    def test_returns_false_when_no_api_key(self, mock_settings):
        mock_settings.SESSION_QA_AGENT_ENABLED = True
        mock_settings.OPENAI_API_KEY = None
        assert _is_session_qa_available() is False

    @patch("app.agents.session_qa_agent.settings")
    def test_returns_true_when_enabled_and_key_set(self, mock_settings):
        mock_settings.SESSION_QA_AGENT_ENABLED = True
        mock_settings.OPENAI_API_KEY = "sk-fake"
        assert _is_session_qa_available() is True


class TestGetSuggestedDifficulty:
    """Test get_suggested_difficulty (v2 difficulty curve)."""

    def test_first_questions_easy(self):
        assert get_suggested_difficulty(0) == "easy"
        assert get_suggested_difficulty(1) == "easy"

    def test_mid_session_medium(self):
        assert get_suggested_difficulty(2) == "medium"
        assert get_suggested_difficulty(3) == "medium"
        assert get_suggested_difficulty(4) == "medium"

    def test_later_questions_hard(self):
        assert get_suggested_difficulty(5) == "hard"
        assert get_suggested_difficulty(10) == "hard"


@pytest.mark.asyncio
class TestGenerateNextQuestion:
    """Test generate_next_question."""

    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_raises_when_agent_disabled(self, mock_available):
        mock_available.return_value = False
        with pytest.raises(ValueError, match="disabled"):
            await generate_next_question(
                role_level="ASE",
                job_entities={},
                resume_entities={},
                previous_messages=[],
            )

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_returns_result_when_llm_returns_valid_json(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"question": "Tell me about a challenging project.", "difficulty": "medium", "question_type": "behavioral"}'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await generate_next_question(
                role_level="ASE",
                job_entities={"JOB_TITLE": ["Engineer"]},
                resume_entities={"SKILL": ["Python"]},
                previous_messages=[],
                question_type=None,
            )

        assert isinstance(result, QuestionGenerationResult)
        assert result.question == "Tell me about a challenging project."
        assert result.difficulty == "medium"
        assert result.question_type == "behavioral"

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_strips_markdown_fence_from_llm_response(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='```json\n{"question": "What is your greatest strength?", "difficulty": "easy"}\n```'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await generate_next_question(
                role_level="INTERN",
                job_entities={},
                resume_entities={},
                previous_messages=[],
            )

        assert result.question == "What is your greatest strength?"
        assert result.difficulty == "easy"

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_uses_fallback_when_llm_raises(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await generate_next_question(
                role_level="ASE",
                job_entities={},
                resume_entities={},
                previous_messages=[],
            )

        assert isinstance(result, QuestionGenerationResult)
        assert result.question
        assert any(
            e["question"] == result.question for e in FALLBACK_QUESTION_BANK
        ) or "recent project or experience" in result.question.lower()

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_uses_fallback_when_llm_returns_invalid_json(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="not json"))]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await generate_next_question(
                role_level="ASE",
                job_entities={},
                resume_entities={},
                previous_messages=[],
            )

        assert isinstance(result, QuestionGenerationResult)
        assert result.question


class TestPickFallbackQuestion:
    """Static fallback bank selection and dedup."""

    def test_skips_question_already_in_session(self):
        first = FALLBACK_QUESTION_BANK[0]["question"]
        q, _, _ = pick_fallback_question(
            previous_messages=[
                {"sender": "ASSISTANT", "type": "QUESTION", "content": first},
            ],
            question_index=0,
        )
        assert q != first

    def test_prefers_technical_when_requested(self):
        q, diff, qtype = pick_fallback_question(
            previous_messages=[],
            question_index=0,
            question_type="technical",
            suggested_difficulty="easy",
        )
        assert qtype == "technical"
        assert diff in ("easy", "medium", "hard", None)


@pytest.mark.asyncio
class TestEvaluateAnswer:
    """Test evaluate_answer."""

    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_raises_when_agent_disabled(self, mock_available):
        mock_available.return_value = False
        with pytest.raises(ValueError, match="disabled"):
            await evaluate_answer(
                question="Tell me about yourself.",
                answer="I am a developer.",
                role_level="ASE",
                job_entities={},
                resume_entities={},
            )

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_returns_result_when_llm_returns_valid_json(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"feedback": "Good structure. Add more metrics.", "score": 75, "dimension_tags": ["communication", "structure"]}'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await evaluate_answer(
                question="Describe a bug you fixed.",
                answer="I fixed a null pointer in production.",
                role_level="ASE",
                job_entities={},
                resume_entities={},
            )

        assert isinstance(result, AnswerEvaluationResult)
        assert result.feedback == "Good structure. Add more metrics."
        assert result.score == 75
        assert result.dimension_tags == ["communication", "structure"]

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_clamps_score_to_0_100(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"feedback": "Ok.", "score": 150, "dimension_tags": []}'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await evaluate_answer(
                question="Q",
                answer="A",
                role_level="ASE",
                job_entities={},
                resume_entities={},
            )

        assert result.score == 100

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_returns_fallback_when_llm_raises(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await evaluate_answer(
                question="Describe a bug you fixed.",
                answer="I fixed a null pointer in production.",
                role_level="ASE",
                job_entities={},
                resume_entities={},
            )

        assert isinstance(result, AnswerEvaluationResult)
        assert "personalized feedback" in result.feedback.lower()
        assert result.score == 50
        assert "offline" in result.dimension_tags


@pytest.mark.asyncio
class TestSummarizeSessionFeedback:
    """Test summarize_session_feedback."""

    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_raises_when_agent_disabled(self, mock_available):
        mock_available.return_value = False
        with pytest.raises(ValueError, match="disabled"):
            await summarize_session_feedback(
                role_level="ASE",
                feedback_items=[],
            )

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_returns_result_when_llm_returns_valid_json(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"strengths": "Good structure.", "areas_for_improvement": "Add metrics."}'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await summarize_session_feedback(
                role_level="ASE",
                feedback_items=[
                    {"content": "Good use of STAR.", "meta": {"score": "75", "dimension_tags": "behavioral"}},
                ],
            )

        assert isinstance(result, SessionSummaryResult)
        assert result.strengths == "Good structure."
        assert result.areas_for_improvement == "Add metrics."

    @patch("openai.AsyncOpenAI")
    @patch("app.agents.session_qa_agent._is_session_qa_available")
    async def test_strips_markdown_fence_from_llm_response(self, mock_available, mock_openai_cls):
        mock_available.return_value = True
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='```json\n{"strengths": "Clear examples.", "areas_for_improvement": "More depth."}\n```'
                        )
                    )
                ]
            )
        )
        mock_openai_cls.return_value = mock_client

        with patch("app.agents.session_qa_agent.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.SESSION_QA_AGENT_MODEL = "gpt-4o-mini"
            mock_settings.SESSION_QA_AGENT_TEMPERATURE = 0.7

            result = await summarize_session_feedback(
                role_level="INTERN",
                feedback_items=[{"content": "Feedback one.", "meta": {}}],
            )

        assert result.strengths == "Clear examples."
        assert result.areas_for_improvement == "More depth."

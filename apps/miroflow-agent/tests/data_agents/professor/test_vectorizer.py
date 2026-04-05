# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.vectorizer import (
    EmbeddingClient,
    ProfessorVectorizer,
    _VECTOR_DIM,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "research_directions": ["大语言模型", "RLHF"],
        "profile_summary": "张三教授专注于大语言模型研究",
        "evaluation_summary": "h-index 45",
        "profile_url": "https://example.com",
        "roster_source": "https://example.com",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _mock_embedding_response(texts: list[str], dim: int = _VECTOR_DIM) -> dict:
    return {
        "data": [
            {"index": i, "embedding": [0.1] * dim}
            for i in range(len(texts))
        ]
    }


class TestEmbeddingClient:
    def test_embed_batch_returns_correct_shape(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _mock_embedding_response(["text1", "text2"])
        mock_response.raise_for_status = MagicMock()

        with patch("src.data_agents.professor.vectorizer.httpx.post", return_value=mock_response):
            client = EmbeddingClient(base_url="http://test:8005/v1")
            vectors = client.embed_batch(["text1", "text2"])
            assert len(vectors) == 2
            assert len(vectors[0]) == _VECTOR_DIM
            assert len(vectors[1]) == _VECTOR_DIM

    def test_embed_batch_empty_input(self):
        client = EmbeddingClient()
        result = client.embed_batch([])
        assert result == []


class TestProfessorVectorizer:
    def _make_vectorizer(self):
        mock_embedding = MagicMock(spec=EmbeddingClient)
        mock_embedding.embed_batch.return_value = [[0.1] * _VECTOR_DIM]

        mock_milvus = MagicMock()
        mock_milvus.has_collection.return_value = True

        with patch(
            "src.data_agents.professor.vectorizer._create_milvus_client",
            return_value=mock_milvus,
        ):
            vectorizer = ProfessorVectorizer(
                embedding_client=mock_embedding,
                milvus_uri="test.db",
            )

        return vectorizer, mock_embedding, mock_milvus

    def test_vectorize_and_upsert_returns_count(self):
        vectorizer, mock_embedding, mock_milvus = self._make_vectorizer()
        profile = _profile()
        mock_embedding.embed_batch.return_value = [[0.1] * _VECTOR_DIM]

        count = vectorizer.vectorize_and_upsert([
            ("PROF-001", profile, "ready"),
        ])
        assert count == 1
        mock_milvus.upsert.assert_called_once()

    def test_vectorize_empty_input(self):
        vectorizer, mock_embedding, mock_milvus = self._make_vectorizer()
        count = vectorizer.vectorize_and_upsert([])
        assert count == 0
        mock_milvus.upsert.assert_not_called()

    def test_search_by_profile(self):
        vectorizer, mock_embedding, mock_milvus = self._make_vectorizer()
        mock_milvus.search.return_value = [[{"id": "PROF-001"}, {"id": "PROF-002"}]]

        results = vectorizer.search_by_profile("大语言模型研究")
        assert len(results) == 2
        assert "PROF-001" in results

    def test_search_by_direction_with_filter(self):
        vectorizer, mock_embedding, mock_milvus = self._make_vectorizer()
        mock_milvus.search.return_value = [[{"id": "PROF-001"}]]

        results = vectorizer.search_by_direction(
            "RLHF", institution="南方科技大学"
        )
        assert len(results) == 1
        call_kwargs = mock_milvus.search.call_args
        assert call_kwargs.kwargs.get("filter") is not None

    def test_ensure_collection_skips_when_exists(self):
        vectorizer, _, mock_milvus = self._make_vectorizer()
        mock_milvus.has_collection.return_value = True
        vectorizer.ensure_collection()
        mock_milvus.create_collection.assert_not_called()

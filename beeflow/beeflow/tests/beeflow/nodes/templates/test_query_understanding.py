"""Unit tests for QueryUnderstandingNode template.

This test suite covers:
1) Testing the vector search query building function
2) Testing QueryUnderstandingNode initialization and schema
3) Testing the prompt template
4) Integration test with actual execution

Run:
  pytest tests/beeflow/nodes/templates/test_query_understanding.py -v
"""

import pytest

from beeflow.nodes.base_node import INPUT, OUTPUT
from beeflow.nodes.templates.query_understanding import (
    QueryUnderstandingNode,
    build_vector_search_query
)


class TestBuildVectorSearchQuery:
    """Tests for the build_vector_search_query function."""

    def test_build_vector_search_query_with_valid_input(self):
        """Test building SQL query with valid embedding and role_ids."""
        emb_result = [[0.1] * 1024]  # Simulated embedding result
        role_ids = ["TCKT", "LOG_APP"]

        result = build_vector_search_query(emb_result, role_ids)

        assert "query" in result
        assert "params" in result
        assert "SELECT" in result["query"]
        assert "meta.business_term_mapping" in result["query"]
        assert "embedding <=>" in result["query"]
        assert "similarity_score" in result["query"]
        # Verify role filter is included
        assert "role_ids" in result["query"]
        assert "&&" in result["query"]
        # Verify params contain embedding and role_ids
        assert len(result["params"]) > 0

    def test_build_vector_search_query_with_empty_emb_result(self):
        """Test building SQL query with empty embedding result."""
        emb_result = []
        role_ids = ["TCKT", "LOG_APP"]

        result = build_vector_search_query(emb_result, role_ids)

        assert result["query"] == "SELECT NULL LIMIT 0"
        assert result["params"] == []

    def test_build_vector_search_query_with_none_emb_result(self):
        """Test building SQL query with None embedding result."""
        emb_result = None
        role_ids = ["TCKT"]

        result = build_vector_search_query(emb_result, role_ids)

        assert result["query"] == "SELECT NULL LIMIT 0"
        assert result["params"] == []

    def test_build_vector_search_query_with_single_role(self):
        """Test building SQL query with single role_id."""
        emb_result = [[0.5] * 100]
        role_ids = ["TCKT"]

        result = build_vector_search_query(emb_result, role_ids)

        assert "query" in result
        assert "params" in result
        # Should have one placeholder for single role
        assert "%s" in result["query"]

    def test_build_vector_search_query_similarity_threshold(self):
        """Test that similarity threshold is set correctly."""
        emb_result = [[0.1] * 100]
        role_ids = ["TCKT"]

        result = build_vector_search_query(emb_result, role_ids)

        # Verify similarity threshold of 0.4 is in the query
        assert "> 0.4" in result["query"]


class TestQueryUnderstandingNode:
    """Tests for QueryUnderstandingNode."""

    def test_query_understanding_node_initialization(self):
        """Test QueryUnderstandingNode can be initialized."""
        node = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT,
            embedding="bge-m3",
            resource_key="gpt-4.1",
            sql_resource="anapp",
            limit=5
        )

        assert node.name == "query_understanding"
        assert node.embedding == "bge-m3"
        assert node.resource_key == "gpt-4.1"
        assert node.sql_resource == "anapp"
        assert node.limit == 5

    def test_query_understanding_node_default_values(self):
        """Test QueryUnderstandingNode with default values."""
        node = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT
        )

        assert node.embedding == "bge-m3"  # default
        assert node.resource_key == "gpt-4.1"  # default
        assert node.sql_resource == "anapp"  # default
        assert node.limit == 5  # default

    def test_query_understanding_node_input_schema(self):
        """Test QueryUnderstandingNode has correct input schema."""
        node = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT
        )

        # Check input_schema contains required fields
        assert "query" in node.input_schema
        assert "role_ids" in node.input_schema

    def test_query_understanding_node_output_schema(self):
        """Test QueryUnderstandingNode has correct output schema."""
        node = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT
        )

        # Check output_schema contains selected_terms field
        assert "selected_terms" in node.output_schema

    def test_query_understanding_node_type(self):
        """Test QueryUnderstandingNode has correct type."""
        node = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT
        )

        assert node.type == "query_understanding"


class TestTermSelectionPrompt:
    """Tests for TERM_SELECTION_QUERY prompt template."""

    def test_prompt_contains_selection_rules(self):
        """Test that prompt contains selection rules."""
        from beeflow.nodes.templates.query_understanding import TERM_SELECTION_QUERY

        # Verify prompt contains key instructions
        assert "Điều kiện 1 (Từ ngữ)" in TERM_SELECTION_QUERY
        assert "Điều kiện 2 (Ngữ nghĩa)" in TERM_SELECTION_QUERY
        assert "similarity_score" in TERM_SELECTION_QUERY

    def test_prompt_placeholder_format(self):
        """Test that prompt has correct placeholders."""
        from beeflow.nodes.templates.query_understanding import TERM_SELECTION_QUERY

        assert "{query}" in TERM_SELECTION_QUERY
        assert "{context_terms}" in TERM_SELECTION_QUERY

    def test_prompt_returns_empty_array_when_no_match(self):
        """Test that prompt instructs to return empty array when no match."""
        from beeflow.nodes.templates.query_understanding import TERM_SELECTION_QUERY

        assert "mảng rỗng" in TERM_SELECTION_QUERY
        assert "selected_terms" in TERM_SELECTION_QUERY


class TestQueryUnderstandingIntegration:
    """Integration tests for QueryUnderstandingNode with full workflow."""

    @pytest.mark.asyncio
    async def test_main_execution_returns_expected_result(self):
        """Test full execution of main() with the query about MB AMC profit."""
        from beeflow.states import WorkflowState, WorkflowIndexer
        from beeflow.nodes.templates.query_understanding import QueryUnderstandingNode

        query_understanding = QueryUnderstandingNode(
            name="query_understanding",
            inputs=INPUT,
            outputs=OUTPUT
        )

        indexer = WorkflowIndexer(name="query_understanding").add_node(query_understanding).build()

        state = WorkflowState(
            indexer=indexer,
            inputs={
                "query": "Tính đến tháng 6/2025 lợi nhuận trước thuế của MB AMC là bao nhiêu tỷ?",
                "role_ids": ["TCKT", "LOG_APP"]
            }
        )

        result = await query_understanding.run(state=state)

        # Verify result structure
        assert "continue_loop" in result
        assert "selected_terms" in result
        assert result["continue_loop"] == False

        # Verify selected_terms is a list
        assert isinstance(result["selected_terms"], list)
        assert len(result["selected_terms"]) > 0

        # Verify each term has required fields
        for term in result["selected_terms"]:
            assert "term_name" in term
            assert "description" in term
            assert "similarity_score" in term
            assert isinstance(term["similarity_score"], float)
            assert term["similarity_score"] > 0.4  # Above threshold

        # Verify the expected terms are selected
        term_names = [t["term_name"] for t in result["selected_terms"]]
        assert "LNTT" in term_names  # Lợi nhuận trước thuế
        assert "MBAMC" in term_names  # MB AMC

        # Verify exact result matches expected
        expected = {
            'continue_loop': False,
            'selected_terms': [
                {'id': 789, 'term_name': 'LNTT', 'description': 'Lợi nhuận trước thuế', 'similarity_score': 0.5311138592822757},
                {'id': 719, 'term_name': 'MBAMC', 'description': 'Công ty TNHH Quản lý nợ và khai thác tài sản MB', 'similarity_score': 0.527576001142026}
            ]
        }

        # Check key fields match
        assert result["continue_loop"] == expected["continue_loop"]
        assert len(result["selected_terms"]) == len(expected["selected_terms"])

        # Verify first term matches
        assert result["selected_terms"][0]["term_name"] == expected["selected_terms"][0]["term_name"]
        assert result["selected_terms"][0]["description"] == expected["selected_terms"][0]["description"]

        # Verify second term matches
        assert result["selected_terms"][1]["term_name"] == expected["selected_terms"][1]["term_name"]
        assert result["selected_terms"][1]["description"] == expected["selected_terms"][1]["description"]

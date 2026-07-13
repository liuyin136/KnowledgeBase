"""Tests for Liquid YAML graph parser."""
from __future__ import annotations

import json

import pytest

from app.services.liquid_extract import LiquidExtractError, parse_graph_yaml


SAMPLE_YAML = """
summary: Ada Lovelace contributed to computing.
entities:
  - id: e1
    name: Ada Lovelace
    type: person
  - id: e2
    name: Computing
    type: field
relations:
  - source_id: e1
    target_id: e2
    type: contributed_to
claims:
  - id: c1
    text: First algorithm for a computer
    entity_id: e1
    confidence: 0.9
"""


def test_parse_graph_yaml_fixture():
    graph = parse_graph_yaml(SAMPLE_YAML)
    assert len(graph.entities) == 2
    assert len(graph.relations) == 1
    assert len(graph.claims) == 1
    assert "Ada" in graph.summary


def test_parse_graph_json_with_colons_in_claim_text():
    """Regression: paths like (.cursor/rules/docker-build.mdc): break YAML scanners."""
    raw = json.dumps(
        {
            "summary": "Docker build discipline",
            "entities": [{"id": "e1", "name": "api-worker", "type": "service"}],
            "relations": [],
            "claims": [
                {
                    "id": "c1",
                    "text": "See plan-docker-first (.cursor/rules/docker-build.mdc): rebuild api-worker",
                    "entity_id": "e1",
                    "confidence": 0.9,
                }
            ],
        }
    )
    graph = parse_graph_yaml(raw)
    assert len(graph.claims) == 1
    assert "docker-build.mdc" in graph.claims[0].text


def test_parse_graph_yaml_rejects_empty():
    with pytest.raises(LiquidExtractError):
        parse_graph_yaml("")


def test_parse_rejects_truncated_json():
    with pytest.raises(LiquidExtractError):
        parse_graph_yaml('{"summary": "Phase 2 will')

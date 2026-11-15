import copy
import datetime

import pydantic
import pytest

from app.models import ai as models_ai
from app.utils import ai_reference as ai_reference_utils


class _DraftReferenceSource(models_ai.ReferenceSourceMetadata):
    id: str


class _ReferencedClaim(pydantic.BaseModel):
    reference_ids: list[str]


class _ReferencedPayload(pydantic.BaseModel):
    claims: list[_ReferencedClaim]
    reference_ids: list[str]
    references: list[_DraftReferenceSource]


def _source(
    source_id: str = "temporary-source",
    url: str = "https://example.com/source",
) -> _DraftReferenceSource:
    return _DraftReferenceSource(
        id=source_id,
        title="Example source",
        publisher="Example",
        source_type="Research",
        published_at=None,
        accessed_at="2026-08-20",
        url=url,
    )


def _payload(
    references: list[_DraftReferenceSource],
    reference_ids: list[str],
) -> _ReferencedPayload:
    return _ReferencedPayload(
        claims=[_ReferencedClaim(reference_ids=reference_ids)],
        reference_ids=reference_ids,
        references=references,
    )


def test_normalize_url_canonicalizes_equivalent_source_locations():
    result = ai_reference_utils.normalize_url(
        " HTTPS://Example.com/research/quarterly/#summary ",
    )

    assert result == "https://example.com/research/quarterly"


def test_normalize_url_preserves_query_as_part_of_source_identity():
    first_page = ai_reference_utils.normalize_url("https://example.com/source/?page=1#results")
    second_page = ai_reference_utils.normalize_url("https://example.com/source?page=2")

    assert first_page == "https://example.com/source?page=1"
    assert first_page != second_page


def test_generate_source_id_is_stable_for_equivalent_urls():
    source_id = ai_reference_utils.generate_source_id("https://Example.com/source/")

    assert source_id.startswith("src-")
    assert source_id == ai_reference_utils.generate_source_id("https://example.com/source")
    assert source_id != ai_reference_utils.generate_source_id("https://example.com/source?version=2")


def test_collect_reference_ids_reads_nested_payload_without_counting_registry():
    payload = {
        "reference_ids": ["source-1"],
        "sections": [
            {"reference_ids": ["source-2", "source-1"]},
        ],
        "references": [
            {"id": "registry-only-source"},
        ],
    }

    assert ai_reference_utils.collect_reference_ids(payload) == {
        "source-1",
        "source-2",
    }


def test_collect_reference_ids_supports_pydantic_payloads():
    sources = [_source("source-1"), _source("source-2", "https://example.com/source-2")]
    payload = _payload(sources, ["source-1", "source-2"])

    assert ai_reference_utils.collect_reference_ids(payload) == {
        "source-1",
        "source-2",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"reference_ids": "source-1"},
        {"reference_ids": ["source-1", 2]},
    ],
)
def test_collect_reference_ids_rejects_invalid_links(payload):
    with pytest.raises(TypeError, match="reference_ids"):
        ai_reference_utils.collect_reference_ids(payload)


def test_filter_reference_ids_preserves_order_and_reports_removed_ids():
    result = ai_reference_utils.filter_reference_ids(
        ["source-2", "source-1", "source-2", "unsupported"],
        {"source-1", "source-2", "source-3"},
    )

    assert result.reference_ids == ["source-2", "source-1"]
    assert result.removed_ids == frozenset({"unsupported"})


@pytest.mark.parametrize(
    "reference_ids",
    [
        "source-1",
        ["source-1", 2],
    ],
)
def test_filter_reference_ids_rejects_invalid_input(reference_ids):
    with pytest.raises(TypeError, match="sequence of strings"):
        ai_reference_utils.filter_reference_ids(reference_ids, {"source-1"})


def test_validate_reference_registry_accepts_complete_nested_links():
    sources = [_source("source-1"), _source("source-2", "https://example.com/source-2")]
    payload = {
        "reference_ids": ["source-1"],
        "sections": [{"reference_ids": ["source-2"]}],
        "references": sources,
    }

    result = ai_reference_utils.validate_reference_registry(sources, payload)

    assert result is None


@pytest.mark.parametrize(
    ("references", "used_ids", "message"),
    [
        (
            [
                _source("source-1"),
                _source("source-1", "https://example.com/source-2"),
            ],
            ["source-1"],
            "reference IDs must be unique",
        ),
        (
            [
                _source("source-1"),
                _source("source-2", "https://example.com/source/"),
            ],
            ["source-1", "source-2"],
            "reference URLs must be unique",
        ),
        (
            [_source("source-1")],
            ["missing"],
            "unknown reference IDs",
        ),
        (
            [
                _source("source-1"),
                _source("source-2", "https://example.com/source-2"),
            ],
            ["source-1"],
            "unused reference IDs",
        ),
    ],
)
def test_validate_reference_registry_rejects_inconsistent_contracts(
    references,
    used_ids,
    message,
):
    payload = {
        "reference_ids": used_ids,
        "references": references,
    }

    with pytest.raises(ValueError, match=message):
        ai_reference_utils.validate_reference_registry(references, payload)


@pytest.mark.parametrize(
    ("citation_urls", "is_verified"),
    [
        (["https://example.com/source/"], True),
        (["https://example.com/different"], False),
        ([], False),
    ],
)
def test_canonicalize_references_flags_provider_verification(citation_urls, is_verified):
    source = _source(source_id="provider-source")
    accessed_at = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)

    result = ai_reference_utils.canonicalize_reference_sources(
        [source],
        citation_urls,
        accessed_at=accessed_at,
    )

    final_source = result.references[0]
    assert final_source.id == ai_reference_utils.generate_source_id(str(source.url))
    assert final_source.is_verified is is_verified
    assert final_source.accessed_at == accessed_at
    assert result.id_map == {source.id: final_source.id}
    assert final_source.title == source.title
    assert final_source.publisher == source.publisher


def test_canonicalize_references_rejects_duplicate_source_identity():
    sources = [
        _source("source-1"),
        _source("source-2", "https://example.com/source/"),
    ]

    with pytest.raises(ValueError, match="reference URLs must be unique"):
        ai_reference_utils.canonicalize_reference_sources(
            sources,
            [],
            accessed_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC),
        )


def test_remap_reference_ids_updates_nested_values_without_mutating_input():
    source = _source()
    payload = _payload([source], [source.id])
    original_payload = copy.deepcopy(payload.model_dump())

    remapped = ai_reference_utils.remap_reference_ids(
        payload,
        {"temporary-source": "src-final"},
    )

    assert remapped == {
        "reference_ids": ["src-final"],
        "claims": [{"reference_ids": ["src-final"]}],
        "references": [source.model_dump()],
    }
    assert payload.model_dump() == original_payload


def test_remap_reference_ids_returns_plain_lists_for_tuple_payloads():
    payload = ({"reference_ids": ("temporary-source",)},)

    remapped = ai_reference_utils.remap_reference_ids(
        payload,
        {"temporary-source": "src-final"},
    )

    assert remapped == [{"reference_ids": ["src-final"]}]


def test_remap_reference_ids_rejects_unknown_ids():
    with pytest.raises(ValueError, match="unknown reference IDs"):
        ai_reference_utils.remap_reference_ids(
            {"reference_ids": ["missing"]},
            {"temporary-source": "src-final"},
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"reference_ids": "temporary-source"},
        {"reference_ids": ["temporary-source", 2]},
    ],
)
def test_remap_reference_ids_rejects_invalid_links(payload):
    with pytest.raises(TypeError, match="reference_ids"):
        ai_reference_utils.remap_reference_ids(
            payload,
            {"temporary-source": "src-final"},
        )

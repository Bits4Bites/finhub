import copy
import datetime

import pydantic
import pytest

from app.models import ai as models_ai
from app.utils import ai_reference as ai_reference_utils


class _ReferencedClaim(pydantic.BaseModel):
    reference_ids: list[str]


class _ReferencedPayload(pydantic.BaseModel):
    claims: list[_ReferencedClaim]
    reference_ids: list[str]
    references: list[models_ai.ReferenceSourceMetadata]


def _source(
    source_id: str = "temporary-source",
    url: str = "https://example.com/source",
) -> models_ai.ReferenceSourceMetadata:
    return models_ai.ReferenceSourceMetadata(
        id=source_id,
        title="Example source",
        publisher="Example",
        source_type="Research",
        published_at=None,
        accessed_at="2026-08-20",
        url=url,
    )


def _final_source(
    source_id: str,
    url: str,
) -> models_ai.ReferenceSource:
    return models_ai.ReferenceSource(
        **_source(source_id, url).model_dump(),
        is_verified=True,
    )


def _payload(
    references: list[models_ai.ReferenceSourceMetadata],
    reference_ids: list[str],
) -> _ReferencedPayload:
    return _ReferencedPayload(
        claims=[_ReferencedClaim(reference_ids=reference_ids)],
        reference_ids=reference_ids,
        references=references,
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            " HTTPS://Example.com/research/quarterly/#summary ",
            "https://example.com/research/quarterly",
        ),
        ("https://Example.com", "https://example.com/"),
        (
            "https://example.com/source/?page=1#results",
            "https://example.com/source?page=1",
        ),
    ],
)
def test_normalize_url_returns_the_public_source_identity(url, expected):
    assert ai_reference_utils.normalize_url(url) == expected


def test_normalize_url_keeps_query_parameters_in_source_identity():
    first_page = ai_reference_utils.normalize_url("https://example.com/source?page=1")
    second_page = ai_reference_utils.normalize_url("https://example.com/source?page=2")

    assert first_page != second_page


def test_generate_source_id_follows_normalized_url_identity():
    first = ai_reference_utils.generate_source_id("https://Example.com/source/")
    equivalent = ai_reference_utils.generate_source_id("https://example.com/source#section")
    different = ai_reference_utils.generate_source_id("https://example.com/source?version=2")

    assert first == equivalent
    assert first != different


def test_collect_reference_ids_supports_documented_nested_containers():
    payload = {
        "reference_ids": ("source-1",),
        "sections": (
            {"reference_ids": {"source-2", "source-1"}},
            [{"summary": "No source links here"}],
        ),
        "references": [
            {"id": "registry-only-source"},
        ],
    }

    assert ai_reference_utils.collect_reference_ids(payload) == {
        "source-1",
        "source-2",
    }


def test_collect_reference_ids_supports_pydantic_results():
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
        {"reference_ids": {"source-1": True}},
    ],
)
def test_collect_reference_ids_rejects_invalid_links(payload):
    with pytest.raises(TypeError):
        ai_reference_utils.collect_reference_ids(payload)


def test_filter_reference_ids_returns_supported_links_and_removed_ids():
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
def test_filter_reference_ids_rejects_invalid_links(reference_ids):
    with pytest.raises(TypeError):
        ai_reference_utils.filter_reference_ids(reference_ids, {"source-1"})


def test_validate_reference_registry_accepts_a_complete_public_registry():
    references = [
        _final_source("source-1", "https://example.com/source-1"),
        _final_source("source-2", "https://example.com/source-2"),
    ]
    payload = {
        "reference_ids": ["source-1"],
        "sections": [{"reference_ids": ["source-2"]}],
        "references": references,
    }

    assert ai_reference_utils.validate_reference_registry(references, payload) is None


@pytest.mark.parametrize(
    "references",
    [
        [
            _final_source("source-1", "https://example.com/source-1"),
            _final_source("source-1", "https://example.com/source-2"),
        ],
        [
            _final_source("source-1", "https://example.com/source"),
            _final_source("source-2", "https://example.com/source/"),
        ],
    ],
)
def test_validate_reference_registry_rejects_duplicate_public_identity(references):
    payload = {
        "reference_ids": [reference.id for reference in references],
        "references": references,
    }

    with pytest.raises(ValueError):
        ai_reference_utils.validate_reference_registry(references, payload)


def test_validate_reference_registry_rejects_an_unknown_link():
    references = [_source("source-1")]
    payload = {
        "reference_ids": ["source-1", "missing"],
        "references": references,
    }

    with pytest.raises(ValueError):
        ai_reference_utils.validate_reference_registry(references, payload)


def test_validate_reference_registry_rejects_an_unused_source():
    references = [
        _source("source-1"),
        _source("source-2", "https://example.com/source-2"),
    ]
    payload = {
        "reference_ids": ["source-1"],
        "references": references,
    }

    with pytest.raises(ValueError):
        ai_reference_utils.validate_reference_registry(references, payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"reference_ids": "source-1"},
        {"reference_ids": ["source-1", 2]},
    ],
)
def test_validate_reference_registry_rejects_malformed_links(payload):
    with pytest.raises(TypeError):
        ai_reference_utils.validate_reference_registry(
            [_source("source-1")],
            payload,
        )


@pytest.mark.parametrize(
    ("citation_urls", "is_verified"),
    [
        (["https://example.com/source/#provider-fragment"], True),
        (["https://example.com/different"], False),
        ([], False),
    ],
)
def test_canonicalize_reference_sources_reports_provider_verification(
    citation_urls,
    is_verified,
):
    source = _source(source_id="provider-source")
    accessed_at = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)

    result = ai_reference_utils.canonicalize_reference_sources(
        [source],
        citation_urls,
        accessed_at=accessed_at,
    )

    final_source = result.references[0]
    assert result.id_map == {source.id: final_source.id}
    assert final_source.is_verified is is_verified
    assert final_source.accessed_at == accessed_at
    assert final_source.title == source.title
    assert final_source.publisher == source.publisher


def test_canonicalize_reference_sources_rejects_duplicate_temporary_ids():
    sources = [
        _source("temporary", "https://example.com/source-1"),
        _source("temporary", "https://example.com/source-2"),
    ]

    with pytest.raises(ValueError):
        ai_reference_utils.canonicalize_reference_sources(
            sources,
            [],
            accessed_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC),
        )


def test_canonicalize_reference_sources_rejects_duplicate_urls():
    sources = [
        _source("source-1", "https://example.com/source"),
        _source("source-2", "https://example.com/source/"),
    ]

    with pytest.raises(ValueError):
        ai_reference_utils.canonicalize_reference_sources(
            sources,
            [],
            accessed_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC),
        )


def test_remap_reference_ids_updates_supported_results_without_mutating_input():
    source = _source()
    payload = _payload([source], [source.id])
    original_payload = copy.deepcopy(payload.model_dump())

    remapped = ai_reference_utils.remap_reference_ids(
        (
            payload,
            {"sections": [{"reference_ids": (source.id,)}]},
        ),
        {source.id: "src-final"},
    )

    assert ai_reference_utils.collect_reference_ids(remapped) == {"src-final"}
    assert payload.model_dump() == original_payload


def test_remap_reference_ids_rejects_unknown_ids():
    with pytest.raises(ValueError):
        ai_reference_utils.remap_reference_ids(
            {"reference_ids": ["missing"]},
            {"temporary-source": "src-final"},
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"reference_ids": "temporary-source"},
        {"reference_ids": ["temporary-source", 2]},
        {"reference_ids": {"temporary-source"}},
    ],
)
def test_remap_reference_ids_rejects_invalid_links(payload):
    with pytest.raises(TypeError):
        ai_reference_utils.remap_reference_ids(
            payload,
            {"temporary-source": "src-final"},
        )

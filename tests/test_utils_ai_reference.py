from datetime import UTC, datetime

import pytest
import xxhash
from pydantic import BaseModel

from app.models import ai as models_ai
from app.utils import ai_reference as ai_reference_utils


class _DraftReferenceSource(models_ai.ReferenceSourceMetadata):
    id: str


class _ReferencedClaim(BaseModel):
    reference_ids: list[str]


class _ReferencedPayload(BaseModel):
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


def test_source_ids_are_deterministic_for_normalized_urls():
    url = "https://Example.com/source/"

    source_id = ai_reference_utils.generate_source_id(url)
    hasher = xxhash.xxh3_128()
    hasher.update(b"https://example.com/source")

    assert source_id == f"src-{hasher.hexdigest()}"
    assert len(source_id) == 36
    assert source_id == ai_reference_utils.generate_source_id("https://example.com/source")


@pytest.mark.parametrize(
    ("citation_urls", "is_verified"),
    [
        (["https://example.com/source/"], True),
        (["https://example.com/different"], False),
        ([], False),
    ],
)
def test_canonicalize_references_flags_provider_verification(citation_urls, is_verified):
    source = _source(source_id="https://example.com/source")
    accessed_at = datetime(2026, 8, 20, tzinfo=UTC)

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


def test_remap_reference_ids_updates_nested_values_without_mutating_input():
    payload = {
        "reference_ids": ["temporary-source"],
        "nested": [{"reference_ids": ["temporary-source"]}],
    }

    remapped = ai_reference_utils.remap_reference_ids(
        payload,
        {"temporary-source": "src-final"},
    )

    assert remapped == {
        "reference_ids": ["src-final"],
        "nested": [{"reference_ids": ["src-final"]}],
    }
    assert payload["reference_ids"] == ["temporary-source"]


def test_collect_reference_ids_reads_nested_mapping_keys():
    payload = {
        "reference_ids": ["source-1"],
        "nested": [{"reference_ids": ["source-2"]}],
        "references": [{"id": "source-3"}],
    }

    assert ai_reference_utils.collect_reference_ids(payload) == {
        "source-1",
        "source-2",
    }


def test_remap_reference_ids_rejects_unknown_ids():
    with pytest.raises(ValueError, match="unknown reference IDs"):
        ai_reference_utils.remap_reference_ids(
            {"reference_ids": ["missing"]},
            {"temporary-source": "src-final"},
        )


def test_validate_reference_registry_accepts_complete_registry():
    source = _source()
    payload = _payload([source], [source.id])

    ai_reference_utils.validate_reference_registry(payload.references, payload)


def test_validate_reference_registry_rejects_duplicate_normalized_urls():
    references = [
        _source("source-1"),
        _source("source-2", "https://example.com/source/"),
    ]
    payload = _payload(references, ["source-1", "source-2"])

    with pytest.raises(ValueError, match="reference URLs must be unique"):
        ai_reference_utils.validate_reference_registry(references, payload)


@pytest.mark.parametrize(
    ("registry_ids", "used_ids", "message"),
    [
        (["source-1", "source-1"], ["source-1"], "reference IDs must be unique"),
        (["source-1"], ["missing"], "unknown reference IDs"),
        (["source-1", "source-2"], ["source-1"], "unused reference IDs"),
    ],
)
def test_validate_reference_registry_rejects_invalid_links(
    registry_ids,
    used_ids,
    message,
):
    references = [_source(source_id, f"https://example.com/{index}") for index, source_id in enumerate(registry_ids)]
    payload = _payload(references, used_ids)

    with pytest.raises(ValueError, match=message):
        ai_reference_utils.validate_reference_registry(references, payload)

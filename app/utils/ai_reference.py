"""Shared trust-boundary utilities for references returned by AI providers."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import xxhash
from pydantic import BaseModel

from ..models import ai as models_ai


@dataclass(frozen=True)
class CanonicalizedReferences:
    """Final reference sources and the temporary-to-final ID mapping."""

    references: list[models_ai.ReferenceSource]
    id_map: dict[str, str]


@dataclass(frozen=True)
class FilteredReferenceIds:
    """Supported reference IDs plus links removed at a trust boundary."""

    reference_ids: list[str]
    removed_ids: frozenset[str]


def normalize_url(url: str) -> str:
    """Normalize a source URL for reference identity and comparison.

    Args:
        url: The source URL to normalize.

    Returns:
        The canonical URL used to identify and compare reference sources.

    Notes:
        Leading and trailing whitespace, URL fragments, scheme or host casing,
        and trailing path slashes do not create separate source identities.
        Query parameters remain part of the identity.
    """
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def generate_source_id(url: str) -> str:
    """Generate a stable application-owned identifier for a reference source.

    Args:
        url: The source URL used as the reference identity.

    Returns:
        An opaque deterministic source identifier. URLs that normalize to the
        same identity produce the same identifier.
    """
    normalized_url = normalize_url(url)
    hasher = xxhash.xxh3_128()
    hasher.update(normalized_url.encode("utf-8"))
    return f"src-{hasher.hexdigest()}"


def collect_reference_ids(value: object) -> set[str]:
    """Report every source linked by an AI-generated result.

    Args:
        value: A result represented by Pydantic models, mappings, or nested
            list, tuple, and set containers containing ``reference_ids`` fields.

    Returns:
        The unique reference IDs linked from the payload.

    Raises:
        TypeError: If a mapping contains a ``reference_ids`` value other than a
            list, tuple, or set of strings.

    Notes:
        Embedded ``references`` registries are ignored because registry entries
        do not by themselves count as used references.
    """
    if isinstance(value, BaseModel):
        result: set[str] = set()
        for field_name in type(value).model_fields:
            if field_name == "references":
                continue
            field_value = getattr(value, field_name)
            if field_name == "reference_ids":
                result.update(field_value)
            else:
                result.update(collect_reference_ids(field_value))
        return result
    if isinstance(value, Mapping):
        result: set[str] = set()
        for field_name, field_value in value.items():
            if field_name == "references":
                continue
            if field_name == "reference_ids":
                if not isinstance(field_value, list | tuple | set) or not all(
                    isinstance(reference_id, str) for reference_id in field_value
                ):
                    raise TypeError("reference_ids must be a collection of strings")
                result.update(field_value)
            else:
                result.update(collect_reference_ids(field_value))
        return result
    if isinstance(value, list | tuple | set):
        return {item for field_value in value for item in collect_reference_ids(field_value)}
    return set()


def filter_reference_ids(
    reference_ids: Sequence[str],
    allowed_reference_ids: Collection[str],
) -> FilteredReferenceIds:
    """Remove unsupported source links from an AI-generated result.

    Args:
        reference_ids: Source IDs linked from a claim or result section.
        allowed_reference_ids: Source IDs that the application permits at the
            current trust boundary.

    Returns:
        The retained IDs in first-seen order and the unsupported IDs that were
        removed. Duplicate retained IDs appear only once.

    Raises:
        TypeError: If ``reference_ids`` is not a sequence of strings.

    Notes:
        Unsupported IDs are reported rather than mapped to guessed sources.
    """

    if isinstance(reference_ids, str) or not all(isinstance(reference_id, str) for reference_id in reference_ids):
        raise TypeError("reference_ids must be a sequence of strings")
    allowed_ids = set(allowed_reference_ids)
    retained_ids = list(dict.fromkeys(reference_id for reference_id in reference_ids if reference_id in allowed_ids))
    removed_ids = frozenset(reference_id for reference_id in reference_ids if reference_id not in allowed_ids)
    return FilteredReferenceIds(
        reference_ids=retained_ids,
        removed_ids=removed_ids,
    )


def validate_reference_registry(
    references: Sequence[models_ai.ReferenceSourceMetadata],
    payload: object,
) -> None:
    """Validate that a payload and its source registry form a complete contract.

    Args:
        references: The source registry exposed with the payload.
        payload: The AI-generated result containing source links in any shape
            supported by ``collect_reference_ids``.

    Returns:
        None when every source identity is unique and every registered source is
        referenced by the payload.

    Raises:
        TypeError: If a ``reference_ids`` field is not a collection of strings.
        ValueError: If source IDs or normalized URLs are duplicated, a link is
            unknown, or a registered source is unused.
    """

    _validate_reference_identity(references)

    reference_ids = {reference.id for reference in references}
    used_reference_ids = collect_reference_ids(payload)
    unknown_reference_ids = used_reference_ids - reference_ids
    if unknown_reference_ids:
        raise ValueError(f"unknown reference IDs: {sorted(unknown_reference_ids)}")

    unused_reference_ids = reference_ids - used_reference_ids
    if unused_reference_ids:
        raise ValueError(f"unused reference IDs: {sorted(unused_reference_ids)}")


def canonicalize_reference_sources(
    references: Sequence[models_ai.ReferenceSourceMetadata],
    citation_urls: Sequence[str],
    *,
    accessed_at: datetime,
) -> CanonicalizedReferences:
    """Convert provider reference metadata into application-owned sources.

    Args:
        references: Source metadata using temporary provider or workflow IDs.
        citation_urls: Source URLs attributed by the AI provider.
        accessed_at: The application retrieval time assigned to every final
            source.

    Returns:
        Final reference sources and a mapping from each temporary ID to its
        application-owned source ID.

    Raises:
        ValueError: If temporary source IDs or normalized source URLs are not
            unique, or final application-owned identities collide.

    Notes:
        Structurally valid sources are retained when provider citations are
        missing or unmatched; those sources are returned as unverified.
        Citation URLs use the same normalization rules as source identity.
    """

    _validate_reference_identity(references)

    verified_urls = {normalize_url(url) for url in citation_urls if url.strip()}
    id_map = {reference.id: generate_source_id(str(reference.url)) for reference in references}
    if len(id_map.values()) != len(set(id_map.values())):
        raise ValueError("generated source IDs must be unique")

    canonical_references = [
        models_ai.ReferenceSource.model_validate(
            {
                **reference.model_dump(),
                "id": id_map[reference.id],
                "accessed_at": accessed_at,
                "is_verified": normalize_url(str(reference.url)) in verified_urls,
            }
        )
        for reference in references
    ]
    return CanonicalizedReferences(references=canonical_references, id_map=id_map)


def remap_reference_ids(value: object, id_map: Mapping[str, str]) -> object:
    """Replace temporary source links in an AI-generated result.

    Args:
        value: A result represented by Pydantic models, mappings, or nested list
            and tuple containers containing ``reference_ids`` fields.
        id_map: Mapping from temporary source IDs to application-owned IDs.

    Returns:
        A copied plain-data result with every linked reference ID replaced.

    Raises:
        TypeError: If a ``reference_ids`` field is not a list or tuple of
            strings.
        ValueError: If the payload links to an ID absent from ``id_map``.

    Notes:
        The input result is not modified. Every linked temporary ID must have a
        corresponding entry in ``id_map``.
    """

    if isinstance(value, BaseModel):
        return remap_reference_ids(value.model_dump(), id_map)
    if isinstance(value, Mapping):
        return {
            key: (
                _remap_reference_id_list(nested_value, id_map)
                if key == "reference_ids"
                else remap_reference_ids(nested_value, id_map)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [remap_reference_ids(item, id_map) for item in value]
    return value


def _validate_reference_identity(
    references: Sequence[models_ai.ReferenceSourceMetadata],
) -> None:
    reference_ids = [reference.id for reference in references]
    if any(not reference_id.strip() for reference_id in reference_ids):
        raise ValueError("reference IDs must be non-empty")
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("reference IDs must be unique")

    reference_urls = [normalize_url(str(reference.url)) for reference in references]
    if len(reference_urls) != len(set(reference_urls)):
        raise ValueError("reference URLs must be unique")


def _remap_reference_id_list(
    reference_ids: object,
    id_map: Mapping[str, str],
) -> list[str]:
    if not isinstance(reference_ids, list | tuple) or not all(
        isinstance(reference_id, str) for reference_id in reference_ids
    ):
        raise TypeError("reference_ids must be a list of strings")

    unknown_reference_ids = set(reference_ids) - set(id_map)
    if unknown_reference_ids:
        raise ValueError(f"unknown reference IDs: {sorted(unknown_reference_ids)}")
    return [id_map[reference_id] for reference_id in reference_ids]

"""Shared trust-boundary utilities for references returned by AI providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def generate_source_id(url: str) -> str:
    normalized_url = normalize_url(url)
    hasher = xxhash.xxh3_128()
    hasher.update(normalized_url.encode("utf-8"))
    return f"src-{hasher.hexdigest()}"


def collect_reference_ids(value: object) -> set[str]:
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


def validate_reference_registry(
    references: Sequence[models_ai.ReferenceSourceMetadata],
    payload: object,
) -> None:
    """Validate reference identity plus all links found in a payload."""

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
    """Generate final IDs and set verification flags from provider citations."""

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
    """Copy a nested payload while replacing every reference_ids value."""

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

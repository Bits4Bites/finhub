from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models import ai as models_ai


def _valid_source_data() -> dict:
    return {
        "id": "asx-listing-1",
        "title": "Upcoming floats and listings",
        "publisher": "ASX",
        "source_type": "Exchange",
        "published_at": None,
        "accessed_at": datetime(2026, 8, 19, 1, 0, tzinfo=UTC),
        "url": "https://www.asx.com.au/listings/upcoming-floats-and-listings",
        "is_verified": True,
    }


def test_strict_ai_model_rejects_extra_fields():
    class ExampleStrictModel(models_ai.StrictAIModel):
        value: int

    with pytest.raises(ValidationError):
        ExampleStrictModel(value=1, unexpected=True)


def test_reference_source_accepts_valid_data_and_strips_text():
    data = _valid_source_data()
    data.update(
        {
            "id": " asx-listing-1 ",
            "title": " Upcoming floats and listings ",
            "publisher": " ASX ",
        }
    )

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.id == "asx-listing-1"
    assert source.title == "Upcoming floats and listings"
    assert source.publisher == "ASX"
    assert source.published_at is None
    assert source.is_verified is True


def test_reference_source_requires_verification_flag():
    data = _valid_source_data()
    del data["is_verified"]

    with pytest.raises(ValidationError, match="is_verified"):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_url_as_final_id():
    data = _valid_source_data()
    data["id"] = "https://www.asx.com.au/announcement"

    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        models_ai.ReferenceSource.model_validate(data)


@pytest.mark.parametrize("field", ["id", "title", "publisher"])
def test_reference_source_rejects_blank_required_text(field):
    data = _valid_source_data()
    data[field] = " "

    with pytest.raises(ValidationError):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_unsupported_source_type():
    data = _valid_source_data()
    data["source_type"] = "SocialMedia"

    with pytest.raises(ValidationError):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_non_https_url():
    data = _valid_source_data()
    data["url"] = "http://example.com/source"

    with pytest.raises(ValidationError, match="url must use HTTPS"):
        models_ai.ReferenceSource.model_validate(data)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 8, 19), datetime(2026, 8, 19, tzinfo=UTC)),
        ("2026-08-19", datetime(2026, 8, 19, tzinfo=UTC)),
        (datetime(2026, 8, 19, 1, 0), datetime(2026, 8, 19, 1, 0, tzinfo=UTC)),
        (
            datetime(2026, 8, 19, 11, 0, tzinfo=timezone(timedelta(hours=10))),
            datetime(2026, 8, 19, 1, 0, tzinfo=UTC),
        ),
    ],
)
def test_reference_source_normalizes_dates_and_datetimes_to_utc(value, expected):
    data = _valid_source_data()
    data["accessed_at"] = value

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.accessed_at == expected
    assert source.accessed_at.tzinfo is UTC


def test_reference_source_normalizes_published_at_to_utc():
    data = _valid_source_data()
    data["published_at"] = "2026-08-18"

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.published_at == datetime(2026, 8, 18, tzinfo=UTC)
    assert source.published_at.tzinfo is UTC


def test_reference_source_allows_publication_after_access():
    data = _valid_source_data()
    data["published_at"] = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.published_at == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)

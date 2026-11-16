import datetime

import pydantic
import pytest

from app.models import ai as models_ai


def _valid_source_data() -> dict[str, object]:
    return {
        "id": "asx-listing-1",
        "title": "Upcoming floats and listings",
        "publisher": "ASX",
        "source_type": "Exchange",
        "published_at": None,
        "accessed_at": datetime.datetime(2026, 8, 19, 1, 0, tzinfo=datetime.UTC),
        "url": "https://www.asx.com.au/listings/upcoming-floats-and-listings",
        "is_verified": True,
    }


def test_strict_ai_model_rejects_undeclared_fields():
    class ExampleStrictModel(models_ai.StrictAIModel):
        value: int

    with pytest.raises(pydantic.ValidationError):
        ExampleStrictModel(value=1, unexpected=True)


def test_reference_source_normalizes_required_text_and_serializes():
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
    assert source.model_dump(mode="json")["is_verified"] is True


def test_reference_source_requires_verification_flag():
    data = _valid_source_data()
    del data["is_verified"]

    with pytest.raises(pydantic.ValidationError):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_non_identifier_id():
    data = _valid_source_data()
    data["id"] = "https://www.asx.com.au/announcement"

    with pytest.raises(pydantic.ValidationError):
        models_ai.ReferenceSource.model_validate(data)


@pytest.mark.parametrize("field", ["id", "title", "publisher"])
def test_reference_source_rejects_blank_required_text(field):
    data = _valid_source_data()
    data[field] = " "

    with pytest.raises(pydantic.ValidationError):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_unsupported_source_type():
    data = _valid_source_data()
    data["source_type"] = "SocialMedia"

    with pytest.raises(pydantic.ValidationError):
        models_ai.ReferenceSource.model_validate(data)


def test_reference_source_rejects_non_https_url():
    data = _valid_source_data()
    data["url"] = "http://example.com/source"

    with pytest.raises(pydantic.ValidationError):
        models_ai.ReferenceSource.model_validate(data)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime.date(2026, 8, 19),
            datetime.datetime(2026, 8, 19, tzinfo=datetime.UTC),
        ),
        (
            "2026-08-19",
            datetime.datetime(2026, 8, 19, tzinfo=datetime.UTC),
        ),
        (
            datetime.datetime(2026, 8, 19, 1, 0),
            datetime.datetime(2026, 8, 19, 1, 0, tzinfo=datetime.UTC),
        ),
        (
            datetime.datetime(
                2026,
                8,
                19,
                11,
                0,
                tzinfo=datetime.timezone(datetime.timedelta(hours=10)),
            ),
            datetime.datetime(2026, 8, 19, 1, 0, tzinfo=datetime.UTC),
        ),
    ],
)
def test_reference_source_normalizes_access_time_to_utc(value, expected):
    data = _valid_source_data()
    data["accessed_at"] = value

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.accessed_at == expected
    assert source.model_dump(mode="json")["accessed_at"].endswith("Z")


def test_reference_source_normalizes_publication_date_to_utc():
    data = _valid_source_data()
    data["published_at"] = "2026-08-18"

    source = models_ai.ReferenceSource.model_validate(data)

    assert source.published_at == datetime.datetime(2026, 8, 18, tzinfo=datetime.UTC)

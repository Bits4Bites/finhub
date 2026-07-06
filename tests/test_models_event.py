from app.models import event as models_event


class TestParseNewListingEventsFromJson:
    def test_parses_public_offer_close_date(self):
        json_str = (
            '[{"symbol": "ASX:ABC", "company": "Alpha Ltd", "date": "2026-07-10", '
            '"price": 1.5, "sector": "TECHNOLOGY", "capital": 1000000, '
            '"public_offer_close_date": "2026-07-05"}]'
        )

        result = models_event.parse_new_listing_events_from_json(json_str, {"exchange": "ASX"})

        assert len(result) == 1
        assert result[0].public_offer_close_date == "2026-07-05"

    def test_public_offer_close_date_defaults_to_none(self):
        json_str = (
            '[{"symbol": "ASX:XYZ", "company": "Beta Ltd", "date": "2026-07-10", '
            '"price": 2.0, "sector": "TECHNOLOGY", "capital": 500000}]'
        )

        result = models_event.parse_new_listing_events_from_json(json_str, {"exchange": "ASX"})

        assert len(result) == 1
        assert result[0].public_offer_close_date is None

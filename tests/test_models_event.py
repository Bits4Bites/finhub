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


class TestParseListingAnalysisFromJson:
    def test_parses_d1_outlook(self):
        json_str = (
            '{"ASX:ABC": {"status": "upcoming", "stance": "Bullish", '
            '"outlook": {'
            '"d1": {"dir": "↑", "reason": "strong demand", "confidence": 70}, '
            '"w1": {"dir": "↑", "reason": "early momentum", "confidence": 65}, '
            '"w2": {"dir": "→", "reason": "settling", "confidence": 50}, '
            '"m1": {"dir": "↑", "reason": "momentum", "confidence": 60}}}}'
        )

        result = models_event.parse_listing_analysis_from_json(json_str, {})

        analysis = result["ASX:ABC"]
        assert analysis.outlook["d1"].direction == "↑"
        assert analysis.outlook["d1"].reason == "strong demand"
        assert analysis.outlook["d1"].confidence == 70
        assert set(analysis.outlook.keys()) == {"d1", "w1", "w2", "m1"}

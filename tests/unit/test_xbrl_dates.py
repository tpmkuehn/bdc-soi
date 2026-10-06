from datetime import date, datetime

from bdc_soi.xbrl_inventory import semantic_end_date, semantic_instant_date, semantic_start_date


def test_arelle_midnight_instant_maps_back_to_reporting_date():
    # Arelle represents instant 2025-06-30 as 2025-07-01T00:00:00.
    assert semantic_instant_date(datetime(2025, 7, 1, 0, 0)) == date(2025, 6, 30)
    assert semantic_end_date(datetime(2026, 1, 1, 0, 0)) == date(2025, 12, 31)
    assert semantic_start_date(datetime(2025, 1, 1, 0, 0)) == date(2025, 1, 1)


def test_non_midnight_datetime_is_kept():
    assert semantic_instant_date(datetime(2025, 6, 30, 15, 30)) == date(2025, 6, 30)
    assert semantic_instant_date(None) is None
    assert semantic_instant_date(date(2025, 6, 30)) == date(2025, 6, 30)

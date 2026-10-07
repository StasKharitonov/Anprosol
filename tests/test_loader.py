from datetime import datetime
from pathlib import Path

from app.loader import read_csv

ROOT = Path(__file__).resolve().parents[1]


def test_csv_assigns_stable_ids_and_parses_rubrics():
    records = read_csv(ROOT / "data" / "posts.csv")

    assert len(records) == 1500
    assert [item.id for item in records] == list(range(1, 1501))
    assert records[0].created_date == datetime(2019, 7, 25, 12, 42, 13)
    assert records[0].rubrics == [
        "VK-1603736028819866",
        "VK-11879320040",
        "VK-63192684938",
    ]
    assert records[0].text.startswith("Слив информации на пассивки:")
    assert records[-1].id == 1500
    assert records[-1].created_date.year == 2019

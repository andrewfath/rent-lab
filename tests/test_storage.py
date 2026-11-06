import json

import pyarrow.parquet as pq

from rentlab.storage import flatten_record, to_table, write_records


def test_flatten_one_level_and_json_fields():
    rec = {
        "id": "x",
        "hoa": {"fee": 300},
        "history": {"2024-01-01": {"price": 2000}},
        "listingAgent": {"name": "A", "phone": "1"},
        "tags": ["a", "b"],
    }
    out = flatten_record(rec, json_fields=["history"], drop_fields=["listingAgent"])
    assert out["hoa__fee"] == 300
    assert json.loads(out["history"]) == {"2024-01-01": {"price": 2000}}
    assert "listingAgent" not in out and "listingAgent__name" not in out
    assert json.loads(out["tags"]) == ["a", "b"]


def test_expected_fields_always_present():
    table = to_table([{"a": 1}], expected_fields=["a", "removedDate"])
    assert table.column_names == ["a", "removedDate"]
    assert table.column("removedDate").to_pylist() == [None]


def test_mixed_types_fall_back_to_string(tmp_path):
    path = write_records([{"unit": 2}, {"unit": "2A"}], tmp_path / "x.parquet")
    assert pq.read_table(path).column("unit").to_pylist() == ["2", "2A"]

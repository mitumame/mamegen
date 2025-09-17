# mamegen/tests/test_common_generator.py
import pytest
from mamegen.common_generator import _should_emit, generate_data


def test_no_null_when_disallowed(monkeypatch):
    # allowNull=False のときは確率に関係なく None を出さない
    monkeypatch.setattr("random.random", lambda: 0.0)
    assert _should_emit({"allowNull": False, "nullProbability": 1.0}) is False


def test_default_is_no_null():
    # 既定: allowNull=True, nullProbability=0.0 → None にはならない
    assert _should_emit({}) is False


def test_zero_probability():
    # p=0.0 は常に None にならない
    assert _should_emit({"allowNull": True, "nullProbability": 0.0}) is False


def test_one_probability(monkeypatch):
    # p=1.0 は常に None（random は何でも OK）
    monkeypatch.setattr("random.random", lambda: 0.42)
    assert _should_emit({"allowNull": True, "nullProbability": 1.0}) is True


def test_threshold_edge(monkeypatch):
    # 比較は "<" なので、random==p は False、わずかに下回れば True
    monkeypatch.setattr("random.random", lambda: 0.5)
    assert _should_emit({"allowNull": True, "nullProbability": 0.5}) is False
    monkeypatch.setattr("random.random", lambda: 0.499999)
    assert _should_emit({"allowNull": True, "nullProbability": 0.5}) is True


def test_missing_allow_but_probability(monkeypatch):
    # allowNull 未指定（=True）でも p に従う
    monkeypatch.setattr("random.random", lambda: 0.2)
    assert _should_emit({"nullProbability": 0.3}) is True
    monkeypatch.setattr("random.random", lambda: 0.3)
    assert _should_emit({"nullProbability": 0.3}) is False


def test_generate_data_respects_null_probability():
    # generate_data 側でも None が反映されることをサクッと確認
    spec = {
        "count": 5,
        "options": {"reproducible": True},
        "header": ["x"],
        "columns": [
            {"name": "x", "rules": {"allowNull": True, "nullProbability": 1.0}}
        ],
    }
    rows = generate_data(spec)
    assert all(r["x"] is None for r in rows)

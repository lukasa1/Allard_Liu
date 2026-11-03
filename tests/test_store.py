"""The SQLite memory store (L7): case file + flat columns, append-only events, outbox, patches."""

import sqlite3
import threading

import pytest

from agent.casefile import Answer, CaseFile
from agent.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cases.sqlite")


def test_case_round_trips_with_flat_columns(store):
    store.create_case(CaseFile(case_id="c1", persona_id="p"))
    store.update_case("c1", lambda c: (setattr(c, "stage", 2), setattr(c, "owner", "intake")))
    case = store.get_case("c1")
    assert (case.stage, case.owner, case.persona_id) == (2, "intake", "p")
    row = sqlite3.connect(store.path).execute("SELECT stage, owner, side_state FROM cases").fetchone()
    assert row == (2, "intake", None)
    with pytest.raises(KeyError):
        store.get_case("nope")


def test_the_case_file_has_no_event_log():
    assert "events" not in CaseFile.model_fields


def test_events_are_appended_in_order_and_filtered(store):
    store.create_case(CaseFile(case_id="c1"))
    for i in range(5):
        store.append_event("c1", "message" if i % 2 else "handoff", {"i": i}, actor="intake")
    store.append_event("other", "handoff", {})
    assert [e.data["i"] for e in store.events("c1")] == [0, 1, 2, 3, 4]
    assert [e.data["i"] for e in store.events("c1", types=("message",))] == [1, 3]
    assert [e.data["i"] for e in store.events("c1", exclude=("message",), last=2)] == [2, 4]
    assert store.events("c1")[0].line().startswith("#1 ")


def test_outbox_since_returns_only_newer_items(store):
    a = store.post("c1", "message", {"text": "one"}, agent="intake")
    store.post("c1", "card", {"type": "sign"}, agent="intake")
    store.post("c2", "message", {"text": "elsewhere"}, agent="support")
    assert [o.payload for o in store.outbox_since("c1")] == [{"text": "one"}, {"type": "sign"}]
    assert [o.kind for o in store.outbox_since("c1", a.seq)] == ["card"]


def test_patches_from_many_threads_lose_nothing(store):
    store.create_case(CaseFile(case_id="c1"))

    def worker(n):
        for i in range(10):
            store.update_case("c1", lambda c, i=i: c.answers.__setitem__(f"{n}-{i}", Answer(value=i, source="t")))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.get_case("c1").answers) == 60

"""The one clock and the one source of random IDs, so an eval case can be replayed.

Live (the demo, tests): the real clock and random IDs. Pinned (`pinned(seed)`, which the eval and
`intake simulate` wrap around each case, and the support eval around each message): the clock
stands still at PINNED_START (every reading the same instant), and IDs (case ids, document ids,
confirmation codes) come from a generator seeded with the case's name. A rerun of the same case on
the same code then sends the model the same prompts, so DSPy's response cache answers it: no cost,
and in minutes. A change only re-asks the model from the first prompt it alters.

The clock stands still, rather than ticking, because claims prep runs in a background thread next
to other turns: a ticking clock would hand out its readings in a different order on a rerun (cached
calls take milliseconds), and every prompt showing a shifted time would miss the cache. Events
and the outbox are ordered by sequence number, not time. poa_skill's DocumentStore.all() sorts by
created_at, which then ties, so documents come in the filesystem's order: live() is safe (a form
has at most one live document: fill_pdf refuses a signed form, a new draft supersedes the old), but
the order of a document list in a prompt can differ (a cache miss, nothing worse), and a new use
of that order must not rely on time while pinned. What can still differ on a
rerun: an ID drawn by two threads at once (IDs are drawn by intake's tools and by the host: the
runtime opening a case, the web host, the eval runner; one at a time per case), and anything that depends on wall time itself, such as a turn's time limit or the
eval's "message during claims prep" timing (new_condition_during_prep); a call that differs is
paid as usual and the run goes on from there. kb_search goes to OpenRouter directly, not through DSPy, so it keeps its own
entries in the same cache, only while pinned (agent/qa.py): its answer is part of the agent's next
prompt, so a fresh search with different results would make every later prompt differ.

poa_skill stays free of this package: it reads its clock and IDs through `poa_skill.documents.CLOCK`,
which pinning points here.
"""

from __future__ import annotations

import random
import secrets
import string
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

from poa_skill import documents as poa_documents

# Mid-day UTC: the same calendar date in every US time zone. Dates are taken in the machine's local
# time, so on a machine far east of UTC (e.g. UTC+8) the pinned date is the next day: consistent
# within a run, but its prompts (and so its cache entries) differ from a US machine's.
PINNED_START = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)

_lock = threading.Lock()
_t: datetime | None = None  # None: live
_rng: random.Random | None = None


def local_date(iso: str) -> str:
    """The local calendar date of a timestamp, as the signature dates are (not its UTC date, a day
    ahead in a US evening)."""
    return datetime.fromisoformat(iso).astimezone().date().isoformat()


def is_pinned() -> bool:
    with _lock:
        return _t is not None


def now() -> datetime:
    with _lock:
        return datetime.now(UTC) if _t is None else _t


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today() -> date:
    """The local date (as the signature dates are): pinned, the pinned date."""
    return now().astimezone().date()


def token_hex(nbytes: int) -> str:
    with _lock:
        if _rng is None:
            return secrets.token_hex(nbytes)
        return _rng.randbytes(nbytes).hex()


def letters(n: int) -> str:
    with _lock:
        if _rng is None:
            return "".join(secrets.choice(string.ascii_uppercase) for _ in range(n))
        return "".join(_rng.choice(string.ascii_uppercase) for _ in range(n))


@contextmanager
def pinned(seed: str, start: datetime = PINNED_START) -> Iterator[None]:
    """Run a case on the pinned clock and seeded IDs; back to live afterwards. One at a time."""
    global _t, _rng
    with _lock:
        if _t is not None:
            raise RuntimeError("the clock is already pinned: one case at a time")
        _t, _rng = start, random.Random(seed)
    poa_documents.CLOCK.update(now=now, token_hex=token_hex)
    try:
        yield
    finally:
        with _lock:
            _t, _rng = None, None
        poa_documents.CLOCK.update(poa_documents.LIVE_CLOCK)

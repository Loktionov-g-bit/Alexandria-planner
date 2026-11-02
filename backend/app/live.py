"""Live refresh: open browser tabs get a short "changed" ping over Server-Sent Events.

In-process only. With two app containers (stable + beta) a tab on the other container misses
the ping and catches up on its next refetch (focus / interval); nothing is lost, just later.
"""

import asyncio
from collections import defaultdict

from . import notify

_subs: dict[int, set[asyncio.Queue]] = defaultdict(set)


def subscribe(user_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    _subs[user_id].add(q)
    return q


def unsubscribe(user_id: int, q: asyncio.Queue) -> None:
    _subs[user_id].discard(q)
    if not _subs[user_id]:
        _subs.pop(user_id, None)


def publish(user_ids: set[int]) -> None:
    for uid in user_ids:
        for q in list(_subs.get(uid, ())):
            if q.empty():  # one pending ping is enough, the client refetches everything anyway
                q.put_nowait("changed")


wakeup = asyncio.Event()  # kicks the dispatcher right after a commit


def _after_commit(user_ids: set[int]) -> None:
    publish(user_ids)
    wakeup.set()


notify.on_commit(_after_commit)

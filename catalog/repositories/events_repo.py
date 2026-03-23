from __future__ import annotations

from typing import List

from agata.catalog.domain.models import QueryEvent


class InMemoryEventsRepo:
    """
    Stub in-memory per event log (tabella catalog_query_events).
    """

    def __init__(self) -> None:
        self._events: List[QueryEvent] = []

    def log_event(self, event: QueryEvent) -> None:
        self._events.append(event)

    def list_events(self) -> List[QueryEvent]:
        # ritorna una copia per evitare mutazioni esterne
        return list(self._events)

    def clear_events(self) -> int:
        n = len(self._events)
        self._events.clear()
        return n

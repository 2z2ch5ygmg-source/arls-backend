from __future__ import annotations

from typing import Any, Callable


class HrDomainApplier:
    def __init__(self, apply_func: Callable[..., dict[str, Any]]):
        self.apply_func = apply_func

    def apply(self, *, tenant, payload, event_type: str) -> dict[str, Any]:
        return self.apply_func(tenant=tenant, payload=payload, event_type=event_type)

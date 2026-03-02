from typing import Any


def ok(data: Any = None, **meta: Any) -> dict:
    payload = {"ok": True, "data": data}
    if meta:
        payload["meta"] = meta
    return payload


def page_meta(*, limit: int, offset: int, total: int | None = None) -> dict:
    meta = {"limit": limit, "offset": offset}
    if total is not None:
        meta["total"] = total
    return meta

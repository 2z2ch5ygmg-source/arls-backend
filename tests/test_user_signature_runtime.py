from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.routers.v1 import users


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchone(self):
        if self.conn.fetchone_queue:
            return self.conn.fetchone_queue.pop(0)
        return None


class _FakeConn:
    def __init__(self, *, fetchone_queue=None) -> None:
        self.fetchone_queue = list(fetchone_queue or [])
        self.executed: list[tuple[str, object]] = []

    def cursor(self):
        return _FakeCursor(self)


class _UploadFileStub:
    def __init__(self, filename: str, raw_bytes: bytes, content_type: str = "image/png") -> None:
        self.filename = filename
        self._raw_bytes = raw_bytes
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._raw_bytes


def _user(role: str = "developer") -> dict:
    return {
        "id": "user-1",
        "tenant_id": "tenant-1",
        "tenant_code": "master",
        "role": role,
    }


def test_get_my_signature_returns_empty_item_when_not_found():
    conn = _FakeConn(fetchone_queue=[None])

    result = users.get_my_signature(conn=conn, user=_user())

    assert result["item"]["has_signature"] is False
    assert result["item"]["preview_data_url"] == ""


def test_get_my_signature_rejects_ineligible_role():
    conn = _FakeConn()

    with pytest.raises(HTTPException) as exc:
        users.get_my_signature(conn=conn, user=_user(role="officer"))

    assert exc.value.status_code == 403


def test_save_my_signature_creates_attachment_object():
    conn = _FakeConn(
        fetchone_queue=[
            None,
            {
                "id": "attachment-1",
                "file_name": "signature.png",
                "mime_type": "image/png",
                "byte_size": 8,
                "metadata_json": {
                    "preview_data_url": "data:image/png;base64,c2lnbmF0dXJl",
                    "source_type": "uploaded",
                },
            },
        ]
    )
    upload = _UploadFileStub("signature.png", b"signature", "image/png")

    result = asyncio.run(
        users.save_my_signature(
            source_type="uploaded",
            file=upload,
            conn=conn,
            user=_user(),
        )
    )

    assert result["item"]["has_signature"] is True
    assert result["item"]["source_type"] == "uploaded"
    assert result["item"]["preview_data_url"].startswith("data:image/png;base64,")
    assert any("INSERT INTO groupware_attachment_objects" in sql for sql, _ in conn.executed)


def test_delete_my_signature_deletes_rows():
    conn = _FakeConn()

    result = users.delete_my_signature(conn=conn, user=_user())

    assert result["item"]["has_signature"] is False
    assert any("DELETE FROM groupware_attachment_objects" in sql for sql, _ in conn.executed)

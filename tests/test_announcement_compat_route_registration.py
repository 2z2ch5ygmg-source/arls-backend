from app.main import app


def test_announcement_compat_get_route_is_registered():
    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods_by_path.setdefault(path, set()).update(getattr(route, "methods", set()) or set())

    assert "GET" in methods_by_path.get("/api/announcements", set())
    assert "POST" in methods_by_path.get("/api/announcements", set())

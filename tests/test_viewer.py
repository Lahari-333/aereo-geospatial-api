"""Tests for interactive geospatial viewer and static routes."""

from fastapi.testclient import TestClient


def test_viewer_root_route(isolated_storage, client: TestClient) -> None:
    """Verify root / serves the HTML viewer."""
    res = client.get("/")
    assert res.status_code == 200
    assert "AEREO GEOSPATIAL ENGINE" in res.text
    assert "Leaflet" in res.text


def test_viewer_named_route(isolated_storage, client: TestClient) -> None:
    """Verify /viewer serves the HTML viewer."""
    res = client.get("/viewer")
    assert res.status_code == 200
    assert "AEREO GEOSPATIAL ENGINE" in res.text


def test_viewer_trailing_slash_route(isolated_storage, client: TestClient) -> None:
    """Verify /viewer/ trailing slash route serves the HTML viewer."""
    res = client.get("/viewer/")
    assert res.status_code == 200
    assert "AEREO GEOSPATIAL ENGINE" in res.text

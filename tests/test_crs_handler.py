"""Unit tests for CRSHandler verifying CRS detection, UTM estimation, and reprojection."""

import geopandas as gpd
import pyproj
import pytest
import shapely

from app.services.crs_handler import CRSHandler, MissingCRSError


@pytest.fixture
def crs_handler() -> CRSHandler:
    return CRSHandler()


def test_is_geographic_and_projected(crs_handler: CRSHandler) -> None:
    """Verify classification of geographic vs projected coordinate systems."""
    assert crs_handler.is_geographic(pyproj.CRS.from_epsg(4326)) is True
    assert crs_handler.is_projected(pyproj.CRS.from_epsg(4326)) is False

    assert crs_handler.is_geographic(pyproj.CRS.from_epsg(3857)) is False
    assert crs_handler.is_projected(pyproj.CRS.from_epsg(3857)) is True

    assert crs_handler.is_geographic(pyproj.CRS.from_epsg(32643)) is False
    assert crs_handler.is_projected(pyproj.CRS.from_epsg(32643)) is True

    assert crs_handler.is_geographic(None) is False
    assert crs_handler.is_projected(None) is False


def test_extract_crs_string(crs_handler: CRSHandler) -> None:
    """Verify standardized string extraction from diverse CRS objects."""
    assert crs_handler.extract_crs_string(pyproj.CRS.from_epsg(4326)) == "EPSG:4326"
    assert crs_handler.extract_crs_string(pyproj.CRS.from_epsg(3857)) == "EPSG:3857"
    assert crs_handler.extract_crs_string(None) is None


def test_is_suitable_metric_crs_matrix(crs_handler: CRSHandler) -> None:
    """Verify suitability classification across geographic, Web Mercator, non-metric, and valid UTM CRSs."""
    # Geographic CRS -> False
    assert crs_handler.is_suitable_metric_crs("EPSG:4326") is False

    # Web Mercator variants -> False (unsuitable due to severe latitude-dependent scale distortion)
    assert crs_handler.is_suitable_metric_crs("EPSG:3857") is False
    assert crs_handler.is_suitable_metric_crs("EPSG:900913") is False

    # Non-metric projected CRS (e.g. California State Plane in US survey feet) -> False
    assert crs_handler.is_suitable_metric_crs("EPSG:2227") is False

    # Valid metric projected CRS (e.g. UTM Zones with meter units) -> True
    assert crs_handler.is_suitable_metric_crs("EPSG:32643") is True
    assert crs_handler.is_suitable_metric_crs("EPSG:32632") is True
    assert crs_handler.is_suitable_metric_crs(None) is False


def test_already_projected_crs_preserved(crs_handler: CRSHandler) -> None:
    """CASE A: Verify that an already-projected suitable metric CRS (UTM) is preserved without unnecessary reprojection."""
    polygon = shapely.Polygon([(500000.0, 1000000.0), (500000.0, 1000100.0), (500100.0, 1000100.0), (500100.0, 1000000.0), (500000.0, 1000000.0)])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[polygon], crs="EPSG:32643")

    selected_crs = crs_handler.determine_measurement_crs(gdf)
    assert selected_crs.to_epsg() == 32643

    transformed_gdf, source_crs, meas_crs, is_transformed = crs_handler.transform_for_measurement(gdf)
    assert source_crs == "EPSG:32643"
    assert meas_crs == "EPSG:32643"
    assert not is_transformed
    assert transformed_gdf.crs.to_epsg() == 32643
    # Geometry coordinates should remain unchanged
    assert transformed_gdf.geometry.iloc[0].equals(polygon)


def test_web_mercator_detected_and_reprojected_to_utm(crs_handler: CRSHandler) -> None:
    """Verify that EPSG:3857 (Web Mercator) is not used directly for measurement, but reprojected to UTM."""
    # Bangalore polygon in Web Mercator coordinates
    polygon = shapely.Polygon([(8637000.0, 1456000.0), (8637000.0, 1457000.0), (8638000.0, 1457000.0), (8638000.0, 1456000.0), (8637000.0, 1456000.0)])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[polygon], crs="EPSG:3857")

    selected_crs = crs_handler.determine_measurement_crs(gdf)
    assert selected_crs is not None
    # Must reproject to UTM (EPSG:32643 for Bangalore longitude ~77.6) rather than staying in 3857
    assert selected_crs.to_epsg() == 32643

    transformed_gdf, source_crs, meas_crs, is_transformed = crs_handler.transform_for_measurement(gdf)
    assert source_crs == "EPSG:3857"
    assert meas_crs == "EPSG:32643"
    assert is_transformed is True
    assert transformed_gdf.crs.to_epsg() == 32643


def test_non_metric_units_detected_and_reprojected_to_utm(crs_handler: CRSHandler) -> None:
    """Verify that a projected CRS in US Survey feet (EPSG:2227) is reprojected to metric UTM."""
    polygon = shapely.Polygon([(6000000.0, 2100000.0), (6000000.0, 2101000.0), (6001000.0, 2101000.0), (6001000.0, 2100000.0), (6000000.0, 2100000.0)])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[polygon], crs="EPSG:2227")

    selected_crs = crs_handler.determine_measurement_crs(gdf)
    assert selected_crs is not None
    # UTM Zone 10N (EPSG:32610) for California
    assert selected_crs.to_epsg() == 32610

    transformed_gdf, source_crs, meas_crs, is_transformed = crs_handler.transform_for_measurement(gdf)
    assert source_crs == "EPSG:2227"
    assert meas_crs == "EPSG:32610"
    assert is_transformed is True
    assert transformed_gdf.crs.to_epsg() == 32610


def test_geographic_crs_estimates_utm_and_transforms(crs_handler: CRSHandler) -> None:
    """CASE B: Verify that a geographic CRS (EPSG:4326) triggers UTM estimation and to_crs() transformation."""
    # Real geographic polygon in Bangalore, India (lat ~12.9, lon ~77.5 -> UTM Zone 43N / EPSG:32643)
    polygon = shapely.Polygon([
        (77.58, 12.96),
        (77.60, 12.96),
        (77.60, 12.98),
        (77.58, 12.98),
        (77.58, 12.96),
    ])
    gdf = gpd.GeoDataFrame([{"name": "Bangalore Region"}], geometry=[polygon], crs="EPSG:4326")

    selected_crs = crs_handler.determine_measurement_crs(gdf)
    assert selected_crs is not None
    assert selected_crs.is_projected
    assert selected_crs.to_epsg() == 32643

    transformed_gdf, source_crs, meas_crs, is_transformed = crs_handler.transform_for_measurement(gdf)
    assert source_crs == "EPSG:4326"
    assert meas_crs == "EPSG:32643"
    assert is_transformed is True
    assert transformed_gdf.crs.to_epsg() == 32643

    # Coordinates must actually differ from degrees (planar meters vs angular degrees)
    transformed_geom = transformed_gdf.geometry.iloc[0]
    orig_geom = gdf.geometry.iloc[0]
    assert transformed_geom.bounds[0] != orig_geom.bounds[0]
    assert transformed_geom.bounds[0] > 100_000  # UTM easting in meters


def test_missing_crs_raises_missing_crs_error(crs_handler: CRSHandler) -> None:
    """CASE C: Verify that missing CRS produces a domain-level MissingCRSError and never assumes EPSG:4326."""
    polygon = shapely.Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[polygon], crs=None)

    with pytest.raises(MissingCRSError) as exc_info:
        crs_handler.determine_measurement_crs(gdf)
    assert "source dataset CRS is missing" in str(exc_info.value)

    with pytest.raises(MissingCRSError):
        crs_handler.transform_for_measurement(gdf)


def test_empty_geodataframe_crs_handling(crs_handler: CRSHandler) -> None:
    """Verify handling when GeoDataFrame has zero rows."""
    gdf = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    res = crs_handler.determine_measurement_crs(gdf)
    assert res is None


def test_all_empty_or_null_geometries(crs_handler: CRSHandler) -> None:
    """Verify dataset containing only null or empty geometries returns None without crashing."""
    gdf = gpd.GeoDataFrame(
        [{"geometry": None}, {"geometry": shapely.Polygon()}],
        crs="EPSG:4326",
    )
    res = crs_handler.determine_measurement_crs(gdf)
    assert res is None

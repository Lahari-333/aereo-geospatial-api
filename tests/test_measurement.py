"""Unit and integration tests for MeasurementService and geospatial metric calculations."""

import geopandas as gpd
import pytest
import shapely

from app.services.crs_handler import MissingCRSError
from app.services.measurement import (
    FeatureMeasurement,
    InvalidGeometryError,
    MeasurementService,
)


@pytest.fixture
def measurement_service() -> MeasurementService:
    return MeasurementService()


# Coordinates for real geographic region in Bangalore, India (approx lat 12.97, lon 77.59)
BANGALORE_POLYGON = shapely.Polygon([
    (77.58, 12.96),
    (77.60, 12.96),
    (77.60, 12.98),
    (77.58, 12.98),
    (77.58, 12.96),
])

BANGALORE_LINESTRING = shapely.LineString([
    (77.58, 12.96),
    (77.60, 12.98),
])

BANGALORE_POINT = shapely.Point(77.59, 12.97)


def test_polygon_in_epsg_4326(measurement_service: MeasurementService) -> None:
    """A. Verify polygon area calculation with automatic reprojection from EPSG:4326 to UTM."""
    gdf = gpd.GeoDataFrame([{"name": "Bangalore Area"}], geometry=[BANGALORE_POLYGON], crs="EPSG:4326")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.feature_id == 0
    assert res.geometry_type == "Polygon"
    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert res.source_crs == "EPSG:4326"
    assert res.measurement_crs == "EPSG:32643"  # UTM Zone 43N
    assert res.value is not None
    # 0.02 deg x 0.02 deg at ~13° latitude is approx 2.2 km x 2.2 km = ~4.7 - 5.0 million square meters
    assert 4_000_000 < res.value < 6_000_000


def test_linestring_in_epsg_4326(measurement_service: MeasurementService) -> None:
    """B. Verify LineString length calculation with automatic reprojection to metric units."""
    gdf = gpd.GeoDataFrame([{"name": "Bangalore Road"}], geometry=[BANGALORE_LINESTRING], crs="EPSG:4326")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.feature_id == 0
    assert res.geometry_type == "LineString"
    assert res.measurement_type == "length"
    assert res.unit == "meters"
    assert res.source_crs == "EPSG:4326"
    assert res.measurement_crs == "EPSG:32643"
    assert res.value is not None
    # Diagonal length across ~0.02 deg is approximately 3.0 - 3.5 km
    assert 2_500 < res.value < 4_000


def test_point_handling(measurement_service: MeasurementService) -> None:
    """C. Verify Point geometries do not perform area or length calculation."""
    gdf = gpd.GeoDataFrame([{"name": "Survey Marker"}], geometry=[BANGALORE_POINT], crs="EPSG:4326")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.feature_id == 0
    assert res.geometry_type == "Point"
    assert res.measurement_type is None
    assert res.value is None
    assert res.unit is None
    assert res.source_crs == "EPSG:4326"
    assert res.measurement_crs is None


def test_already_projected_crs(measurement_service: MeasurementService) -> None:
    """D. Verify measurement service consumes already projected suitable metric CRS directly."""
    # 100m x 200m rectangle in UTM Zone 43N (EPSG:32643)
    rect = shapely.Polygon([(500000, 1000000), (500000, 1000200), (500100, 1000200), (500100, 1000000), (500000, 1000000)])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[rect], crs="EPSG:32643")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert res.source_crs == "EPSG:32643"
    assert res.measurement_crs == "EPSG:32643"
    assert pytest.approx(res.value, rel=1e-3) == 20000.0


def test_web_mercator_3857_reprojected_to_utm_for_accurate_measurement(
    measurement_service: MeasurementService,
) -> None:
    """Verify EPSG:3857 is NOT used directly for metric measurement due to Web Mercator scale distortion."""
    # Bangalore polygon defined in Web Mercator
    rect = shapely.Polygon([
        (8637000.0, 1456000.0),
        (8637000.0, 1456200.0),
        (8637100.0, 1456200.0),
        (8637100.0, 1456000.0),
        (8637000.0, 1456000.0),
    ])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[rect], crs="EPSG:3857")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert res.source_crs == "EPSG:3857"
    # Crucial requirement: measurement_crs MUST NOT be EPSG:3857
    assert res.measurement_crs != "EPSG:3857"
    assert res.measurement_crs == "EPSG:32643"
    assert res.value is not None
    assert res.value > 0


def test_non_metric_units_reprojected_to_utm(measurement_service: MeasurementService) -> None:
    """Verify projected CRS with US survey feet units (EPSG:2227) is reprojected to metric UTM."""
    rect = shapely.Polygon([
        (6000000.0, 2100000.0),
        (6000000.0, 2101000.0),
        (6001000.0, 2101000.0),
        (6001000.0, 2100000.0),
        (6000000.0, 2100000.0),
    ])
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[rect], crs="EPSG:2227")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert res.source_crs == "EPSG:2227"
    assert res.measurement_crs == "EPSG:32610"
    assert res.value is not None


def test_missing_crs_rejected(measurement_service: MeasurementService) -> None:
    """E. Verify dataset with CRS=None fails with clean domain error and does not assume EPSG:4326."""
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[BANGALORE_POLYGON], crs=None)

    with pytest.raises(MissingCRSError) as exc_info:
        measurement_service.calculate_measurements(gdf)

    assert "source dataset CRS is missing" in str(exc_info.value)


def test_invalid_geometry_handling(measurement_service: MeasurementService) -> None:
    """F. Verify invalid geometry produces unavailable measurement without silent repair."""
    # Self-intersecting figure-8 / bowtie polygon (invalid topology)
    bowtie = shapely.Polygon([(0, 0), (0, 2), (2, 0), (2, 2), (0, 0)])
    assert not bowtie.is_valid

    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[bowtie], crs="EPSG:3857")

    # Default non-strict behavior: records unavailable measurement and notes
    results = measurement_service.calculate_measurements(gdf, strict_validity=False)
    assert len(results) == 1
    res = results[0]
    assert res.value is None
    assert res.unit is None
    assert "invalid" in res.notes.lower()

    # Strict mode: raises InvalidGeometryError
    with pytest.raises(InvalidGeometryError) as exc_info:
        measurement_service.calculate_measurements(gdf, strict_validity=True)
    assert "invalid Polygon geometry" in str(exc_info.value)


def test_empty_geometry_handling(measurement_service: MeasurementService) -> None:
    """G. Verify empty geometry marks measurement unavailable without crashing."""
    empty_poly = shapely.Polygon()
    assert empty_poly.is_empty

    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[empty_poly], crs="EPSG:3857")
    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]
    assert res.value is None
    assert res.unit is None
    assert "empty" in res.notes.lower()


def test_multipolygon_area(measurement_service: MeasurementService) -> None:
    """H. Verify area calculation for MultiPolygon geometries."""
    poly1 = shapely.Polygon([(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)])  # 100 m²
    poly2 = shapely.Polygon([(20, 20), (20, 30), (30, 30), (30, 20), (20, 20)])  # 100 m²
    multipoly = shapely.MultiPolygon([poly1, poly2])

    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[multipoly], crs="EPSG:32643")
    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.geometry_type == "MultiPolygon"
    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert pytest.approx(res.value, rel=1e-3) == 200.0


def test_multilinestring_length(measurement_service: MeasurementService) -> None:
    """I. Verify length calculation for MultiLineString geometries."""
    line1 = shapely.LineString([(0, 0), (0, 50)])  # 50m
    line2 = shapely.LineString([(10, 10), (10, 70)])  # 60m
    multiline = shapely.MultiLineString([line1, line2])

    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[multiline], crs="EPSG:32643")
    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 1
    res = results[0]

    assert res.geometry_type == "MultiLineString"
    assert res.measurement_type == "length"
    assert res.unit == "meters"
    assert pytest.approx(res.value, rel=1e-3) == 110.0


def test_mixed_geometry_dataset(measurement_service: MeasurementService) -> None:
    """J. Verify independent calculation across Point, LineString, and Polygon in one dataset."""
    gdf = gpd.GeoDataFrame([
        {"name": "Survey Landmark", "geometry": BANGALORE_POINT},
        {"name": "Boundary Line", "geometry": BANGALORE_LINESTRING},
        {"name": "Reserve Area", "geometry": BANGALORE_POLYGON},
    ], crs="EPSG:4326")

    results = measurement_service.calculate_measurements(gdf)
    assert len(results) == 3

    # Feature 0: Point -> no measurement
    assert results[0].feature_id == 0
    assert results[0].geometry_type == "Point"
    assert results[0].measurement_type is None
    assert results[0].value is None
    assert results[0].measurement_crs is None

    # Feature 1: LineString -> length in meters
    assert results[1].feature_id == 1
    assert results[1].geometry_type == "LineString"
    assert results[1].measurement_type == "length"
    assert results[1].unit == "meters"
    assert results[1].value > 2000

    # Feature 2: Polygon -> area in square meters
    assert results[2].feature_id == 2
    assert results[2].geometry_type == "Polygon"
    assert results[2].measurement_type == "area"
    assert results[2].unit == "square_meters"
    assert results[2].value > 4_000_000


def test_crs_transformation_distinct(measurement_service: MeasurementService) -> None:
    """K. Verify that source CRS != measurement CRS for geographic datasets."""
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[BANGALORE_POLYGON], crs="EPSG:4326")
    results = measurement_service.calculate_measurements(gdf)

    assert results[0].source_crs == "EPSG:4326"
    assert results[0].measurement_crs != "EPSG:4326"
    assert results[0].measurement_crs.startswith("EPSG:326")


def test_critical_requirement_no_direct_degree_measurements(measurement_service: MeasurementService) -> None:
    """CRITICAL REQUIREMENT TEST:

    Verifies that measurements are NOT calculated directly on geographic degrees (EPSG:4326).
    If someone computed gdf.geometry.area or gdf.geometry.length directly in EPSG:4326,
    the values would be angular degrees squared (0.0004 deg²) or angular degrees (0.028 deg),
    which are off by orders of magnitude from planar square meters and meters.
    """
    gdf = gpd.GeoDataFrame([
        {"id": "poly", "geometry": BANGALORE_POLYGON},
        {"id": "line", "geometry": BANGALORE_LINESTRING},
    ], crs="EPSG:4326")

    # Direct raw geometry calculations in EPSG:4326 (WRONG - angular units)
    raw_degree_area = gdf.geometry.iloc[0].area
    raw_degree_length = gdf.geometry.iloc[1].length

    assert raw_degree_area == pytest.approx(0.0004, rel=1e-2)
    assert raw_degree_length == pytest.approx(0.02828, rel=1e-2)

    # Calculation via MeasurementService with automatic UTM reprojection (CORRECT - metric units)
    results = measurement_service.calculate_measurements(gdf)

    metric_area = results[0].value
    metric_length = results[1].value

    # Planar area must be millions of square meters, NOT 0.0004!
    assert metric_area != raw_degree_area
    assert metric_area > 4_000_000
    assert results[0].unit == "square_meters"
    assert results[0].measurement_crs == "EPSG:32643"

    # Planar length must be thousands of meters, NOT 0.028!
    assert metric_length != raw_degree_length
    assert metric_length > 2_500
    assert results[1].unit == "meters"
    assert results[1].measurement_crs == "EPSG:32643"

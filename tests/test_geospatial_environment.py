"""Geospatial environment and dependency verification tests.

Verifies that GeoPandas, Shapely, PyProj, and Pyogrio are properly installed,
importable, and functional for geometry creation, CRS definition, and coordinate
reprojection without external network or file dependencies.
"""

import geopandas as gpd
import pyproj
import shapely
from shapely.geometry import LineString, Point, Polygon


def test_geopandas_import() -> None:
    """Verify that GeoPandas and underlying engines import cleanly."""
    assert gpd.__version__ is not None
    assert shapely.__version__ is not None
    assert pyproj.__version__ is not None


def test_shapely_geometry_creation() -> None:
    """Verify creation and basic validity of core Shapely geometry primitives."""
    point = Point(77.5946, 12.9716)
    assert point.geom_type == "Point"
    assert point.x == 77.5946
    assert point.y == 12.9716
    assert point.is_valid

    line = LineString([(77.0, 12.0), (77.5, 12.5), (78.0, 13.0)])
    assert line.geom_type == "LineString"
    assert len(line.coords) == 3
    assert line.is_valid

    polygon = Polygon([(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0), (0.0, 0.0)])
    assert polygon.geom_type == "Polygon"
    assert polygon.is_valid
    assert polygon.area == 4.0


def test_pyproj_crs_creation() -> None:
    """Verify creation and inspection of geographic and projected CRS objects."""
    crs_geographic = pyproj.CRS.from_epsg(4326)
    assert crs_geographic.is_geographic
    assert not crs_geographic.is_projected
    assert crs_geographic.to_epsg() == 4326

    crs_projected = pyproj.CRS.from_epsg(3857)
    assert crs_projected.is_projected
    assert not crs_projected.is_geographic
    assert crs_projected.to_epsg() == 3857


def test_crs_transformation() -> None:
    """Verify coordinate transformation (to_crs) vs metadata override (set_crs)."""
    # Create GeoDataFrame in WGS84 (EPSG:4326, degrees)
    orig_point = Point(77.5946, 12.9716)
    gdf = gpd.GeoDataFrame([{"id": 1}], geometry=[orig_point], crs="EPSG:4326")

    # to_crs() performs actual mathematical coordinate reprojection
    projected_gdf = gdf.to_crs(epsg=3857)
    assert projected_gdf.crs.to_epsg() == 3857

    transformed_point = projected_gdf.geometry.iloc[0]
    # Projected coordinates in meters differ significantly from angular degree coordinates
    assert transformed_point.x != orig_point.x
    assert transformed_point.y != orig_point.y
    assert transformed_point.x > 1_000_000
    assert transformed_point.y > 1_000_000

    # Contrast with set_crs: overrides CRS metadata only, coordinates remain unchanged
    override_gdf = gdf.copy()
    override_gdf = override_gdf.set_crs(epsg=3857, allow_override=True)
    assert override_gdf.crs.to_epsg() == 3857
    assert override_gdf.geometry.iloc[0].x == orig_point.x
    assert override_gdf.geometry.iloc[0].y == orig_point.y


def test_geodataframe_geometry_handling() -> None:
    """Verify that GeoDataFrame properly recognizes geometry column and attributes."""
    points = [Point(10.0, 20.0), Point(15.0, 25.0)]
    gdf = gpd.GeoDataFrame(
        {"name": ["feature_a", "feature_b"]},
        geometry=points,
        crs="EPSG:4326",
    )

    assert gdf.geometry.name == "geometry"
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert list(gdf.geom_type) == ["Point", "Point"]
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    assert bounds[0] == 10.0
    assert bounds[1] == 20.0
    assert bounds[2] == 15.0
    assert bounds[3] == 25.0

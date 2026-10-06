"""Programmatic test fixtures for geospatial file processing tests."""

import io
from pathlib import Path
import tempfile
import zipfile

import geopandas as gpd
import shapely


def create_valid_kml_bytes() -> bytes:
    """Generate minimal valid KML content with a Placemark Point."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Point</name>
      <description>Sample Placemark</description>
      <Point>
        <coordinates>77.5946,12.9716,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""


def create_empty_kml_bytes() -> bytes:
    """Generate valid KML container with zero features."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
  </Document>
</kml>"""


def create_malformed_kml_bytes() -> bytes:
    """Generate syntactically broken XML content."""
    return b"<kml><Document><unclosed_tag>"


def create_valid_shapefile_zip_bytes(include_prj: bool = True) -> bytes:
    """Generate a valid in-memory ZIP archive containing an ESRI Shapefile."""
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = Path(tmpdir) / "polygon_feature.shp"
        polygon = shapely.Polygon([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)])
        gdf = gpd.GeoDataFrame(
            [{"name": "Zone A", "id": 101}],
            geometry=[polygon],
            crs="EPSG:4326" if include_prj else None,
        )
        gdf.to_file(shp_path, driver="ESRI Shapefile")

        with zipfile.ZipFile(buffer, "w") as zf:
            for item in Path(tmpdir).iterdir():
                if not include_prj and item.suffix.lower() == ".prj":
                    continue
                if item.is_file():
                    zf.write(item, arcname=item.name)

    return buffer.getvalue()


def create_invalid_zip_bytes() -> bytes:
    """Generate corrupted bytes that are not a valid ZIP file."""
    return b"PK\x03\x04Corrupted_Data_Not_A_Real_Zip_Archive_Payload"


def create_zip_without_shapefile_bytes() -> bytes:
    """Generate a valid ZIP archive containing no .shp file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("notes.txt", "This archive contains documentation only.")
        zf.writestr("data.csv", "id,value\n1,100\n")
    return buffer.getvalue()


def create_zip_with_multiple_shapefiles_bytes() -> bytes:
    """Generate a ZIP archive containing two distinct Shapefiles."""
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir:
        # First shapefile
        shp1 = Path(tmpdir) / "layer1.shp"
        gdf1 = gpd.GeoDataFrame([{"id": 1}], geometry=[shapely.Point(1, 1)], crs="EPSG:4326")
        gdf1.to_file(shp1, driver="ESRI Shapefile")

        # Second shapefile
        shp2 = Path(tmpdir) / "layer2.shp"
        gdf2 = gpd.GeoDataFrame([{"id": 2}], geometry=[shapely.Point(2, 2)], crs="EPSG:4326")
        gdf2.to_file(shp2, driver="ESRI Shapefile")

        with zipfile.ZipFile(buffer, "w") as zf:
            for item in Path(tmpdir).iterdir():
                if item.is_file():
                    zf.write(item, arcname=item.name)

    return buffer.getvalue()


def create_zip_with_path_traversal_bytes() -> bytes:
    """Generate a ZIP archive containing a path traversal member entry."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../../malicious.txt", "evil payload")
        zf.writestr("test.shp", "dummy")
    return buffer.getvalue()

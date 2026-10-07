# Geospatial File Measurement API

## Overview

The Geospatial File Measurement API is a production-oriented backend service designed to parse geospatial files (KML files and ZIP archives containing ESRI Shapefiles), extract feature properties and geometries, handle Coordinate Reference System (CRS) transformations, and compute geometric measurements such as polygon areas and linestring lengths.

This project is organized with a clean layered architecture separating HTTP routing, business logic, persistence models, request/response validation schemas, and application configuration.

## Current Status

> **Note**: Steps 1 through 5 are implemented and verified.
> 
> - **Architecture & Setup (Step 1):** Layered FastAPI project structure and configuration.
> - **Geospatial Environment (Step 2):** GeoPandas, Shapely, PyProj, and Pyogrio integration.
> - **File Upload API (Step 3):** Secure `POST /api/files/` endpoint with chunked streaming and size limits.
> - **Geospatial Processing (Step 4):** KML and Shapefile ZIP extraction with Zip Slip defense and companion verification.
> - **Measurement & CRS Handling (Step 5):** Metric area/length calculations and automated UTM reprojection strategy.

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Configuration & Validation:** Pydantic / Pydantic Settings
- **Geospatial Engines:** GeoPandas, Shapely, PyProj, Pyogrio
- **Testing:** Pytest, HTTPX

## Project Structure

```
aereo-geospatial-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # Application entry point and router registration
│   │
│   ├── api/                        # HTTP and API route layer
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── files.py            # Endpoints for file upload and processing
│   │
│   ├── core/                       # Core configuration and environment settings
│   │   ├── __init__.py
│   │   └── config.py
│   │
│   ├── models/                     # Persistence and data models
│   │   ├── __init__.py
│   │   └── file_record.py
│   │
│   ├── schemas/                    # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   └── file.py
│   │
│   ├── services/                   # Business logic and domain processing
│   │   ├── __init__.py
│   │   ├── upload_service.py       # File streaming, size limits, and disk storage
│   │   ├── file_processor.py       # KML and Shapefile archive parsing
│   │   ├── measurement.py          # Metric area and length calculations
│   │   └── crs_handler.py          # CRS reprojection and UTM estimation
│   │
│   └── storage/                    # Database and persistence management
│       ├── __init__.py
│       └── database.py
│
├── tests/                          # Automated test suites
│   ├── __init__.py
│   ├── fixtures.py                 # Deterministic in-memory geospatial test fixtures
│   ├── test_health.py              # Health check endpoint test
│   ├── test_geospatial_environment.py # Environment and driver tests
│   ├── test_upload.py              # Upload validation and security tests
│   ├── test_file_processor.py      # Archive extraction and parsing tests
│   ├── test_crs_handler.py         # CRS inspection and reprojection tests
│   └── test_measurement.py         # Geometric calculation and UTM tests
│
├── uploads/                        # Uploaded file storage directory
│   └── .gitkeep
│
├── processed/                      # Extracted/processed file artifacts
│   └── .gitkeep
│
├── .gitignore
├── requirements.txt
├── README.md
└── Dockerfile
```

## Measurement and CRS Strategy

### 1. Why EPSG:4326 Cannot Be Directly Used for Metric Measurements

`EPSG:4326` (WGS 84) is a **geographic 2D coordinate system** defined on a reference ellipsoid using angular degrees (latitude and longitude). 

Because degrees are angles rather than linear units of length:
- A degree of longitude spans approximately 111.32 km at the equator, but converges to 0 km at the poles.
- Calculating `geom.area` on EPSG:4326 coordinates produces **square degrees** (e.g., `0.0001 deg²` for a local park), which is dimensionally incompatible with metric units and differs from square meters by many orders of magnitude.
- Calculating `geom.length` on EPSG:4326 coordinates produces **angular degrees** (e.g., `0.05 deg`), rather than linear meters.

Therefore, geographic coordinates must **never** be used directly for planar area or length calculations.

### 2. How Geographic CRS Datasets Are Handled

When an incoming dataset is identified as geographic (such as `EPSG:4326` from KML files or unprojected Shapefiles):
1. Non-empty, non-null geometries are inspected to determine the bounding spatial extent.
2. The optimal local **Universal Transverse Mercator (UTM)** projection is determined using `geopandas.GeoDataFrame.estimate_utm_crs()`.
3. The dataset is reprojected using `gdf.to_crs(target_utm_crs)`.
4. Metric measurements are computed on the reprojected planar geometries in standard SI units:
   - **Polygon / MultiPolygon:** Area in **square meters** (`square_meters`).
   - **LineString / MultiLineString:** Length in **meters** (`meters`).
   - **Point:** No measurement required (`value = None`, `unit = None`, `measurement_crs = None`).

### 3. How UTM CRS Is Selected

The Universal Transverse Mercator system divides the Earth into 60 longitudinal zones of 6 degrees each. For any regional or local dataset, `estimate_utm_crs()` automatically computes the centroid of the dataset extent and selects the corresponding UTM EPSG code (for example, `EPSG:32643` for UTM Zone 43N in southern India). UTM projections minimize local conformal and scale distortion within the zone, making them well-suited for planar engineering measurements.

### 4. How Projected CRS Datasets Are Handled

If an uploaded dataset already has a valid projected planar CRS (such as `EPSG:3857` or an existing UTM code) with standard linear meter units:
- The measurement service consumes the projected coordinates directly without unnecessary coordinate transformation.
- The `measurement_crs` matches the `source_crs`.

### 5. What Happens When CRS Is Missing

If a dataset has no coordinate reference system defined (for example, a Shapefile ZIP lacking a `.prj` companion file):
- The service **does not assume EPSG:4326** or fabricate a projection.
- Reprojection and measurement halt immediately, producing a clean domain-level `MissingCRSError`:
  `"Cannot calculate metric measurements because the source dataset CRS is missing."`

### 6. Invalid and Empty Geometries

The measurement service handles topological edge cases gracefully on a per-feature basis:
- **Empty geometries (`geom.is_empty`):** Marked as unavailable (`value = None`, `notes = "Geometry is empty"`).
- **Null geometries (`geom is None`):** Marked as unavailable (`value = None`, `notes = "Geometry is null"`).
- **Invalid geometries (`not geom.is_valid`):** Evaluated without attempting silent geometry modification (no automatic `buffer(0)` repair). Measurements are marked unavailable with explanatory notes (`notes = "Geometry is topologically invalid. Measurement unavailable."`), or can trigger `InvalidGeometryError` when strict validity mode is requested.
- **Fault isolation:** An invalid or empty feature does not invalidate or prevent the measurement of other valid features in the same dataset.

### 7. Coordinate Transformation via `to_crs()`

The implementation strictly distinguishes between CRS assignment and coordinate transformation:
- `set_crs()` only changes the metadata tag without adjusting coordinate values.
- `to_crs()` executes actual mathematical transformation of coordinates from the ellipsoid to planar Cartesian coordinates.
The measurement pipeline **always** uses `to_crs()` for coordinate transformation.

### 8. Limitations of the Strategy

While UTM-based projection is an industry-standard, practical approach for local and regional datasets, it has inherent geographic boundaries:
- Datasets spanning continental scales or crossing multiple UTM zones will experience increasing scale distortion near zone edges.
- For continental or global datasets, specialized equal-area projections (such as Albers Equal Area or sinusoidal projections) or geodesic calculations would be required.

---

## Local Setup

### 1. Prerequisites

- Python 3.11 or higher
- Git

### 2. Clone the Repository & Create Virtual Environment

```bash
git clone <repository-url>
cd aereo-geospatial-api

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Application

Start the local development server using Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Health Check

```bash
curl -X GET http://localhost:8000/health
```

Expected Response:
```json
{
  "status": "ok"
}
```

## Running Tests

Run the complete test suite using `pytest`:

```bash
pytest -v
```

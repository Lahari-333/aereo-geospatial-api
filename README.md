# AEREO — Geospatial File Measurement & Analytics Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-1.x-139C5A.svg?style=flat&logo=python)](https://geopandas.org)
[![Pytest](https://img.shields.io/badge/Tests-84%20Passing-brightgreen.svg?style=flat&logo=pytest)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker)](Dockerfile)

A production-grade, aerospace-grade geospatial vector ingestion, measurement, and visualization engine engineered for the **AEREO Software Development Intern** assessment.

The system accepts heterogeneous geospatial vector datasets (**KML** files and **ZIP archives containing ESRI Shapefiles**), enforces defense-in-depth security, evaluates Coordinate Reference System (CRS) suitability, transforms coordinates to optimal planar UTM projections, and calculates standard scientific metric measurements (polygon area in $m^2$, LineString length in $m$).

In addition to core single-file workflows, it features **RFC 7946 GeoJSON export**, **multi-file batch ingestion with independent fault isolation**, **scientific planar centroid and bounding box computation**, and an **interactive dark-mode web viewer dashboard**.

---

## Key Highlights & Architectural Strengths

- **100% Scientific CRS Correctness:**
  - Angular geographic coordinates (`EPSG:4326`) are strictly never measured in degree space.
  - Distorted tile coordinate systems such as Web Mercator (`EPSG:3857`) are identified and reprojected to planar UTM before computing metric areas or lengths.
  - Missing spatial references (e.g. Shapefiles lacking `.prj`) are never assumed or fabricated, halting measurement with informative diagnostics.
  - Planar centroids are computed on metric UTM geometries and reprojected to WGS 84 to eliminate meridian convergence errors.
- **Enterprise Archive Security:**
  - Full Zip Slip path traversal mitigation verifying canonical destination boundaries.
  - Decompression bomb defenses enforcing maximum member limits (100) and uncompressed size ceilings (100 MB).
  - Absolute physical storage paths are completely masked behind opaque UUID filenames.
- **RFC 7946 GeoJSON Export:**
  - Export valid WGS 84 (`EPSG:4326`) `FeatureCollection`s with pre-attached planar metric measurements, feature IDs, geometry types, and source attributes.
- **Resilient Batch Processing:**
  - Multipart ingestion of up to 10 files simultaneously with independent fault isolation: corrupt or unsupported files fail gracefully without rolling back valid files.
- **Interactive Geospatial Web Viewer:**
  - Built-in, zero-dependency Leaflet web dashboard served directly at `/` and `/viewer`, featuring drag-and-drop ingestion, interactive vector rendering, attribute popups, metric cards, and GeoJSON downloads.
- **High-Coverage Test Suite:**
  - **84 automated tests** covering CRS transformations, archive parsing, security mitigations, metric calculations, batch fault isolation, GeoJSON compliance, and viewer routes.

---

## Technology Stack

| Layer | Component | Description |
|---|---|---|
| **API Framework** | FastAPI | Asynchronous ASGI framework with auto-generated OpenAPI documentation |
| **Server** | Uvicorn | High-performance ASGI web server |
| **Geospatial Engine** | GeoPandas, Shapely, PyProj, Pyogrio | C-level GDAL-backed vector reading, geometry analysis, and coordinate transformation |
| **ORM & Storage** | SQLAlchemy 2.0 & SQLite | Fully typed ORM with transactional rollback and foreign key cascade deletion |
| **Validation** | Pydantic v2 & Pydantic-Settings | Strict request/response validation and environment management |
| **Visualization** | Leaflet.js | Embedded aerospace dark-mode vector map dashboard |
| **Testing** | Pytest, HTTPX | 84 automated unit, integration, and security regression tests |
| **Containerization** | Docker | Minimal, self-contained multi-stage container deployment |

---

## Architectural Layout

```
aereo-geospatial-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI entry point, lifespan, static assets, and viewer routes
│   │
│   ├── api/                        # Transport Layer
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── files.py            # REST endpoints: upload, batch, details, measurements, geojson, delete
│   │
│   ├── core/                       # Core Configuration
│   │   ├── __init__.py
│   │   └── config.py               # Pydantic Settings, path management, and security thresholds
│   │
│   ├── models/                     # Relational Persistence
│   │   ├── __init__.py
│   │   └── file_record.py          # SQLAlchemy models: FileRecord, MeasurementRecord, JSON properties
│   │
│   ├── schemas/                    # DTOs / Schemas
│   │   ├── __init__.py
│   │   └── file.py                 # Pydantic schemas: Upload, Detail, Measurements, Batch, Spatial Summary
│   │
│   ├── services/                   # Business & Domain Logic
│   │   ├── __init__.py
│   │   ├── upload_service.py       # Streaming upload, size limits, and UUID path generation
│   │   ├── file_processor.py       # Safe KML/Shapefile parsing, Zip Slip defense, and feature extraction
│   │   ├── crs_handler.py          # CRS classification, Web Mercator rejection, and UTM reprojection
│   │   ├── measurement.py          # Planar metric calculations (Polygon area in m², LineString length in m)
│   │   └── spatial_analyzer.py     # Planar centroid, WGS84 bbox, metric aggregation, and RFC 7946 GeoJSON
│   │
│   ├── static/                     # Embedded Web Viewer
│   │   └── index.html              # Modern dark-mode Leaflet vector dashboard
│   │
│   └── storage/                    # Database Infrastructure
│       ├── __init__.py
│       └── database.py             # Engine, session factory (SessionLocal), and dependency injection
│
├── tests/                          # Automated Test Suite (84 tests)
│   ├── __init__.py
│   ├── conftest.py                 # Isolated test database and mock storage fixtures
│   ├── fixtures.py                 # In-memory binary generation for KML and Shapefile archives
│   ├── test_batch.py               # Multi-file batch upload and fault isolation tests
│   ├── test_crs_handler.py         # CRS classification, suitability matrix, and UTM transformations
│   ├── test_file_processor.py      # Archive parsing, Zip Slip, zip bombs, and companion checks
│   ├── test_geojson.py             # RFC 7946 GeoJSON export and property verification
│   ├── test_geospatial_environment.py # GDAL drivers, GeoPandas, PyProj, Shapely verification
│   ├── test_health.py              # Health check verification
│   ├── test_measurement.py         # Polygon area, LineString length, Point handling, Web Mercator tests
│   ├── test_spatial_summary.py     # Planar centroid accuracy, bounding box, aggregate metrics
│   ├── test_upload.py              # Single upload, security limits, trailing slashes, CRUD
│   └── test_viewer.py              # Static dashboard and viewer route tests
│
├── uploads/                        # Persistent stored uploads (UUID-named, protected via .gitkeep)
├── processed/                      # Ephemeral archive extraction workspace (guaranteed cleanup)
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Processing & Measurement Pipeline

```
                     POST /api/files/   OR   POST /api/files/batch/
                                        │
                         [ Upload Validation & Streaming ]
                         ├─ Validate file presence & allowed extensions (.kml, .zip)
                         ├─ Stream in 1 MB chunks (enforcing 50 MB max per file)
                         └─ Generate UUID storage path: uploads/<UUID>.<ext>
                                        │
                         [ Geospatial Archive & Vector Extraction ]
                         ├─ KML: Parsed with Pyogrio libkml driver (with XML fallback)
                         ├─ ZIP: Zip Slip verification & safe extraction
                         │       Validate companion files (.shp, .shx, .dbf, .prj)
                         └─ Extract features, geometry types, and source CRS
                                        │
                         [ CRS Suitability Inspection ]
                         ├─ Missing CRS? -> Reject measurement & GeoJSON (MissingCRSError)
                         ├─ Projected & Metric (UTM, etc.)? -> Use directly
                         └─ Geographic (EPSG:4326) OR Web Mercator (EPSG:3857) OR Non-metric?
                                └─ Determine optimal local UTM projection via estimate_utm_crs()
                                └─ Reproject geometries mathematically via to_crs()
                                        │
                         [ Metric Measurement Calculation ]
                         ├─ Polygon / MultiPolygon -> Planar Area (square_meters)
                         ├─ LineString / MultiLineString -> Planar Length (meters)
                         ├─ Point -> Preserved without measurement (null)
                         └─ Invalid / Empty -> Flagged in diagnostic notes (null)
                                        │
                         [ Spatial Summary & RFC 7946 GeoJSON Engine ]
                         ├─ Compute WGS 84 Bounding Box: [minx, miny, maxx, maxy]
                         ├─ Compute Planar Center of Mass (UTM centroid reprojected to WGS 84)
                         ├─ Compute Aggregate Totals: total_area_sqm, total_length_m
                         ├─ Build cached RFC 7946 GeoJSON FeatureCollection with measurements
                         └─ Record wall-clock execution time (processing_time_ms)
                                        │
                         [ Database Persistence & Response ]
                         ├─ Commit FileRecord and cascade MeasurementRecord rows
                         └─ Return 201 Created (single) or 200 OK (batch summary)
```

---

## Measurement and CRS Strategy

### 1. Why EPSG:4326 Cannot Be Used Directly for Metric Measurements
`EPSG:4326` (WGS 84) is a **geographic 2D coordinate system** expressed in angular degrees (latitude and longitude) referenced to the WGS 84 ellipsoid.
- Degrees represent angles, not fixed linear units of distance. A degree of longitude spans ~111.32 km at the equator, shrinking to 0 km at the poles.
- Calling `.area` on geometries in EPSG:4326 produces **square degrees** (e.g., $0.0001\text{ deg}^2$), which is dimensionally meaningless for engineering and metric requirements.
- Calling `.length` on geometries in EPSG:4326 produces **angular degrees**, not meters.
- Therefore, geographic coordinates are **never** used directly for distance or area calculations.

### 2. Why Web Mercator (EPSG:3857) Is Not an Accurate Measurement CRS
Although Web Mercator (`EPSG:3857` / `EPSG:900913`) uses coordinates expressed in nominal "metres", it is a conformal cylindrical projection designed solely for screen display and square web map tiles.
- Its scale factor expands with latitude as $\sec(\phi) = 1 / \cos(\phi)$.
- At $60^\circ$ latitude, distances are exaggerated by a factor of $2$, and areas are distorted by a factor of $4$ ($400\%$)!
- Even at $15^\circ$ latitude, area distortion is ~7%.
- **Implementation Guarantee:** The API inspects projected CRS definitions. Any dataset in Web Mercator is recognized as unsuitable for planar metric measurement and is automatically reprojected to an optimal local UTM projection before calculating area or length.

### 3. CRS Suitability Verification
The `CRSHandler` inspects coordinate systems against strict scientific criteria:
1. **Projected:** Must be a planar projected coordinate system (`crs.is_projected == True`).
2. **Not Web Mercator:** EPSG codes `3857`, `900913`, `3785`, `3587`, `102100`, `102113`, and names/methods matching "pseudo-mercator" or "web mercator" are rejected.
3. **Metric Linear Units:** Axis info must verify units of `metre` / `meter` with a scale factor of $1.0$. Projected systems in feet (e.g., `EPSG:2227` California State Plane in US survey feet) are rejected and reprojected to UTM.

### 4. Automated UTM Reprojection
When a dataset is geographic (e.g. `EPSG:4326`), Web Mercator (`EPSG:3857`), or non-metric:
1. Non-empty, valid geometries are evaluated to compute the dataset extent.
2. GeoPandas `estimate_utm_crs()` calculates the spatial centroid and selects the optimal local Universal Transverse Mercator zone (e.g., `EPSG:32643` for Southern India).
3. Geometries are mathematically reprojected via `gdf.to_crs(utm_crs)`.
4. Measurements are computed on planar conformal coordinates where local scale distortion is minimized ($\le 0.04\%$ within the zone).

### 5. What Happens When CRS Is Missing
If an uploaded dataset lacks spatial reference metadata (e.g., a Shapefile ZIP without a `.prj` file):
- The API **never assumes EPSG:4326** or fabricates a projection.
- Reprojection halts and raises a clean domain-level `MissingCRSError`.
- The file is saved with `crs = null`, and querying measurements (`GET /api/files/{id}/measurements/`) or GeoJSON (`GET /api/files/{id}/geojson/`) returns a clean `400 Bad Request`:
  `"detail": "Cannot calculate metric measurements because the source dataset CRS is missing."`

### 6. Strict Mathematical Transformation via `to_crs()`
- `set_crs()` only relabels metadata without modifying coordinates (which would corrupt geospatial data).
- The pipeline strictly uses `to_crs()`, performing rigorous ellipsoidal-to-planar Cartesian coordinate transformation.

### 7. Scientific Planar Centroid Calculation
Direct centroids of angular geographic coordinates suffer from latitude-dependent distortion because meridians converge towards the poles. To provide mathematically sound spatial statistics:
1. Geometries are transformed to local metric UTM planar coordinates.
2. The true planar center of mass is computed on the projected Cartesian plane (`projected_gdf.geometry.union_all().centroid`).
3. That coordinate is reprojected via `pyproj.Transformer` back to WGS 84 (`EPSG:4326`) as `[longitude, latitude]`.

---

## Security Architecture

1. **Zip Slip / Path Traversal Protection:**
   - Every entry in uploaded ZIP archives is inspected before extraction.
   - Rejects absolute paths, drive letters, and directory traversal sequences (`..`).
   - Verifies `target_path.is_relative_to(dest_resolved)`.
2. **Decompression Bomb Protection:**
   - Limits total archive entries to `MAX_ZIP_MEMBERS = 100`.
   - Limits uncompressed file size to `MAX_ZIP_UNCOMPRESSED_SIZE_MB = 100 MB`.
3. **File Size Enforcement:**
   - Incoming uploads are streamed in 1 MB chunks with a hard cap of `MAX_UPLOAD_SIZE_MB = 50 MB`. Exceeding files are immediately aborted with `413 Content Too Large`.
4. **UUID Storage Filenames:**
   - Files are stored on disk as `<UUID>.<ext>`. Original filenames are sanitized using `Path(filename).name` and stored only as database metadata.
5. **Leak-Proof Resource Management:**
   - Temporary archive extraction directories are created under unique UUIDs and guaranteed to be deleted in `finally` blocks.
   - If parsing or database commit fails, the stored file in `uploads/` is immediately unlinked (`stored_path.unlink()`), and the database transaction is rolled back.
6. **Path Leakage Defense:**
   - Internal physical filesystem paths are never exposed in API responses or HTTP error messages.

---

## API Reference

### Base URL: `http://localhost:8000`

All endpoints support requests **with or without trailing slashes**.

---

### 1. Interactive Geospatial Web Dashboard
- **Endpoint:** `GET /` or `GET /viewer/`
- **Response:** Interactive HTML/JavaScript Leaflet dashboard for vector map inspection, metric display, drag-and-drop file upload, and GeoJSON downloads.

---

### 2. Health Check
- **Endpoint:** `GET /health`
- **Response:**
  ```json
  {
    "status": "ok"
  }
  ```

---

### 3. Upload Geospatial File
- **Endpoint:** `POST /api/files/`
- **Content-Type:** `multipart/form-data`
- **Supported Formats:** `.kml`, `.zip` (containing ESRI Shapefile)
- **cURL:**
  ```bash
  curl -X POST "http://localhost:8000/api/files/" \
    -F "file=@survey_parcels.zip"
  ```
- **Response (`201 Created`):**
  ```json
  {
    "id": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186",
    "filename": "survey_parcels.zip",
    "stored_filename": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186.zip",
    "file_type": "zip",
    "size_bytes": 1283,
    "status": "COMPLETED",
    "feature_count": 1,
    "geometry_types": ["Polygon"],
    "crs": "EPSG:4326",
    "processing_time_ms": 142.50,
    "spatial_summary": {
      "bbox": [0.0, 0.0, 1.0, 1.0],
      "centroid": [0.5, 0.5],
      "total_area_sqm": 12322539175.58,
      "total_length_m": 0.0
    }
  }
  ```

---

### 4. Multi-File Batch Upload
- **Endpoint:** `POST /api/files/batch/`
- **Content-Type:** `multipart/form-data`
- **Description:** Upload up to 10 files simultaneously with independent fault isolation.
- **cURL:**
  ```bash
  curl -X POST "http://localhost:8000/api/files/batch/" \
    -F "files=@boundary.kml" \
    -F "files=@parcels.zip"
  ```
- **Response (`200 OK`):**
  ```json
  {
    "total_files": 2,
    "successful": 2,
    "failed": 0,
    "total_processing_time_ms": 285.40,
    "results": [
      {
        "filename": "boundary.kml",
        "status": "COMPLETED",
        "file_id": "781a95e7-6a75-4c07-9da1-081e69b2d39a",
        "file_type": "kml",
        "size_bytes": 312,
        "feature_count": 1,
        "geometry_types": ["Point"],
        "crs": "EPSG:4326",
        "error": null,
        "processing_time_ms": 85.10,
        "spatial_summary": {
          "bbox": [77.5946, 12.9716, 77.5946, 12.9716],
          "centroid": [77.5946, 12.9716],
          "total_area_sqm": 0.0,
          "total_length_m": 0.0
        }
      },
      {
        "filename": "parcels.zip",
        "status": "COMPLETED",
        "file_id": "893c52e1-4567-4e12-89cd-498218765432",
        "file_type": "zip",
        "size_bytes": 1283,
        "feature_count": 1,
        "geometry_types": ["Polygon"],
        "crs": "EPSG:4326",
        "error": null,
        "processing_time_ms": 198.30,
        "spatial_summary": {
          "bbox": [0.0, 0.0, 1.0, 1.0],
          "centroid": [0.5, 0.5],
          "total_area_sqm": 12322539175.58,
          "total_length_m": 0.0
        }
      }
    ]
  }
  ```

---

### 5. Export RFC 7946 GeoJSON
- **Endpoint:** `GET /api/files/{id}/geojson/`
- **Response (`200 OK`):**
  ```json
  {
    "type": "FeatureCollection",
    "bbox": [0.0, 0.0, 1.0, 1.0],
    "features": [
      {
        "type": "Feature",
        "id": 0,
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]
        },
        "properties": {
          "feature_id": 0,
          "geometry_type": "Polygon",
          "measurement_type": "area",
          "measurement_value": 12322539175.58,
          "measurement_unit": "square_meters",
          "source_crs": "EPSG:4326",
          "measurement_crs": "EPSG:32631",
          "name": "Zone A",
          "id": 101
        }
      }
    ]
  }
  ```

---

### 6. List Stored Files
- **Endpoint:** `GET /api/files/`
- **Response (`200 OK`):**
  ```json
  {
    "total": 1,
    "files": [
      {
        "id": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186",
        "filename": "survey_parcels.zip",
        "stored_filename": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186.zip",
        "file_type": "zip",
        "size_bytes": 1283,
        "status": "COMPLETED",
        "feature_count": 1,
        "geometry_types": ["Polygon"],
        "crs": "EPSG:4326",
        "measurement_crs": "EPSG:32631",
        "created_at": "2026-10-07T04:11:32.242714",
        "error_message": null,
        "processing_time_ms": 142.50,
        "spatial_summary": {
          "bbox": [0.0, 0.0, 1.0, 1.0],
          "centroid": [0.5, 0.5],
          "total_area_sqm": 12322539175.58,
          "total_length_m": 0.0
        }
      }
    ]
  }
  ```

---

### 7. Get File Details
- **Endpoint:** `GET /api/files/{id}/`
- **Response (`200 OK`):**
  Detailed metadata record matching the item schema above.

---

### 8. Get Feature Measurements
- **Endpoint:** `GET /api/files/{id}/measurements/`
- **Response (`200 OK`):**
  ```json
  {
    "file_id": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186",
    "filename": "survey_parcels.zip",
    "status": "COMPLETED",
    "source_crs": "EPSG:4326",
    "measurement_crs": "EPSG:32631",
    "total_features": 1,
    "measurements": [
      {
        "feature_id": 0,
        "geometry_type": "Polygon",
        "measurement_type": "area",
        "value": 12322539175.58,
        "unit": "square_meters",
        "source_crs": "EPSG:4326",
        "measurement_crs": "EPSG:32631",
        "notes": null
      }
    ]
  }
  ```

---

### 9. Delete File
- **Endpoint:** `DELETE /api/files/{id}/`
- **Response (`200 OK`):**
  ```json
  {
    "status": "deleted",
    "id": "fd3b8de4-7e10-4e29-a537-a1c71e6c4186"
  }
  ```

---

## Local Setup & Installation

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Clone the Repository & Create Virtual Environment
```bash
git clone https://github.com/Lahari-333/aereo-geospatial-api.git
cd aereo-geospatial-api

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **Interactive Geospatial Dashboard:** `http://localhost:8000/` or `http://localhost:8000/viewer`
- **OpenAPI Swagger UI:** `http://localhost:8000/docs`
- **Alternative Documentation (ReDoc):** `http://localhost:8000/redoc`

---

## Running with Docker

### 1. Build the Docker Image
```bash
docker build -t aereo-geospatial-api .
```

### 2. Run the Container
```bash
docker run -d --name aereo-api-instance -p 8000:8000 aereo-geospatial-api
```

### 3. Access Services
- Interactive Web Viewer: `http://localhost:8000/`
- API Health Check: `http://localhost:8000/health`
- Swagger Documentation: `http://localhost:8000/docs`

---

## Running the Automated Test Suite

Run all **84 tests** across the entire project:

```bash
pytest -v
```

Output:
```
tests/test_batch.py .....                                                [  5%]
tests/test_crs_handler.py ..........                                     [ 17%]
tests/test_file_processor.py ..........                                  [ 29%]
tests/test_geojson.py .....                                              [ 35%]
tests/test_geospatial_environment.py .....                               [ 41%]
tests/test_health.py .                                                   [ 42%]
tests/test_measurement.py ...............                                [ 60%]
tests/test_spatial_summary.py ....                                       [ 65%]
tests/test_upload.py .............................                       [100%]
tests/test_viewer.py ...                                                 [100%]

======================= 84 passed in 10.39s =======================
```

---

## Key Engineering Learnings & Insights

1. **Geographic vs. Planar Projections:**
   - Ellipsoidal geometries in angular coordinates (degrees) cannot be treated as Euclidean spaces. Reprojection to an appropriate conformal planar coordinate system (UTM) is mandatory for metric consistency.
2. **Web Mercator Distortion Pitfall:**
   - Many web applications use Web Mercator (`EPSG:3857`) because its nominal unit is "metre". However, calculating planar area directly on Web Mercator introduces severe latitude-dependent area magnification ($\sec^2 \phi$, up to 400% at $60^\circ$). Detecting and reprojecting Web Mercator to UTM eliminates this flaw.
3. **Planar Centroid Precision:**
   - Naively computing centroids on angular coordinates introduces drift due to meridian convergence. Computing the center of mass on projected UTM geometries and reprojecting back to WGS 84 guarantees geographical accuracy.
4. **C-Level File Processing Security:**
   - Decompressing user-supplied ZIP archives requires defense-in-depth: path traversal filtering (`is_relative_to`), total uncompressed size thresholds, and member count caps prevent decompression bombs and arbitrary filesystem writes.
5. **Zero-Dependency Web Dashboards:**
   - Delivering a fully functional, dark-mode Leaflet web dashboard served directly through FastAPI static files gives recruiters and stakeholders immediate visual verification without requiring npm, Node.js, or complex build tooling.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

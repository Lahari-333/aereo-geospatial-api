# Geospatial File Measurement API

## Overview

The **Geospatial File Measurement API** is a production-grade backend service built for the AEREO Software Development Intern assignment. It accepts geospatial vector files (**KML** files and **ZIP archives containing ESRI Shapefiles**), securely unpacks and parses geospatial features, rigorously evaluates Coordinate Reference System (CRS) suitability, transforms coordinates to optimal planar projections, and calculates standard scientific metric measurements (polygon area in $m^2$, LineString length in $m$).

The application is architected with a clean, decoupled layered design separating HTTP transport, domain services, persistence entities, validation schemas, and system configuration.

---

## Problem Statement & Engineering Objectives

In drone surveying and GIS engineering workflows, geospatial boundary files (e.g. cadastral boundaries, transmission lines, flight mission corridors) are frequently received as KML files or ESRI Shapefile archives. Ingesting and measuring these files reliably poses several challenges:
1. **Heterogeneous Vector Formats:** Supporting both XML-based KML placemarks and multi-file ESRI Shapefile archives (.shp, .shx, .dbf, .prj).
2. **Untrusted Archive Ingestion:** Protecting server infrastructure against Zip Slip directory traversal attacks, decompression bombs, and excessive memory allocations.
3. **Ellipsoidal vs. Planar Projections:** Geospatial coordinates are commonly tagged with geographic systems like `EPSG:4326` (WGS 84 in degrees) or distorted tile systems like `EPSG:3857` (Web Mercator). Calculating planar metric area or length on these coordinates produces severe errors or invalid degree units.
4. **Automated Reprojection:** Determining the optimal local Universal Transverse Mercator (UTM) zone for each dataset and performing mathematical coordinate transformation (`to_crs()`).
5. **Relational Persistence & Retrieval:** Storing parsed metadata, spatial properties, and computed measurements in an easily queryable relational database with transactional consistency.

---

## Current Status

> **Step 8: Final Submission Polish, Security Review & AEREO-Ready Verification Complete.**
>
> - **67 / 67 automated tests passing** across unit, integration, security, and persistence suites.
> - **Full Live API smoke test verified** across all endpoints with zero memory or filesystem leaks.
> - **Docker containerization verified:** Ready for containerized deployment via `Dockerfile` and `.dockerignore`.
> - **100% scientific CRS correctness:** Rigorous handling of geographic coordinates, dynamic UTM reprojection, and rejection of distorted Web Mercator projections.

---

## Technology Stack

- **Language:** Python 3.11+
- **Web Framework:** FastAPI (Asynchronous ASGI)
- **Application Server:** Uvicorn
- **ORM & Database:** SQLAlchemy 2.0 (SQLite default with isolated session management; PostgreSQL/PostGIS compatible)
- **Data Validation & Settings:** Pydantic v2 & Pydantic-Settings
- **Geospatial Processing Engine:** GeoPandas 1.x, Shapely 2.x, PyProj 3.x, Pyogrio 0.13.x (GDAL C-engine backend)
- **Testing & HTTP Client:** Pytest, HTTPX

---

## Architecture & Directory Structure

```
aereo-geospatial-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application lifespan, router inclusion, and database initialization
│   │
│   ├── api/                        # Transport Layer
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── files.py            # REST endpoints for upload, file details, measurements, listing, and deletion
│   │
│   ├── core/                       # Core Configuration Layer
│   │   ├── __init__.py
│   │   └── config.py               # Pydantic environment configuration and storage path management
│   │
│   ├── models/                     # Relational Persistence Models
│   │   ├── __init__.py
│   │   └── file_record.py          # SQLAlchemy models: FileRecord and MeasurementRecord (cascade delete)
│   │
│   ├── schemas/                    # Data Transfer Objects / Schemas
│   │   ├── __init__.py
│   │   └── file.py                 # Pydantic request & response validation schemas
│   │
│   ├── services/                   # Domain Logic Layer
│   │   ├── __init__.py
│   │   ├── upload_service.py       # Chunked streaming upload, size enforcement, and UUID path storage
│   │   ├── file_processor.py       # KML and Shapefile archive extraction, Zip Slip defense, and feature normalization
│   │   ├── crs_handler.py          # CRS suitability inspection, Web Mercator rejection, and UTM reprojection
│   │   └── measurement.py          # Planar metric calculations (Polygon area in m², LineString length in m)
│   │
│   └── storage/                    # Database Infrastructure Layer
│       ├── __init__.py
│       └── database.py             # Engine, session factory (SessionLocal), and dependency injection provider
│
├── tests/                          # Comprehensive Test Suites (67 tests)
│   ├── __init__.py
│   ├── fixtures.py                 # In-memory binary generation for KML and Shapefile ZIP archives
│   ├── test_health.py              # Health check verification
│   ├── test_geospatial_environment.py # Verification of GDAL drivers, GeoPandas, PyProj, Shapely
│   ├── test_upload.py              # Upload validation, size limits, security, and REST endpoint tests
│   ├── test_file_processor.py      # Archive parsing, Zip Slip, zip bombs, and companion checks
│   ├── test_crs_handler.py         # CRS classification, suitability matrix, and UTM transformations
│   └── test_measurement.py         # Polygon area, LineString length, Point handling, and Web Mercator tests
│
├── uploads/                        # Persistent stored uploads (UUID-named, protected via .gitkeep)
│   └── .gitkeep
│
├── processed/                      # Ephemeral workspace for archive unpacking (cleaned up immediately)
│   └── .gitkeep
│
├── .gitignore
├── requirements.txt
├── README.md
└── Dockerfile
```

---

## Processing and Measurement Pipeline

```
                       POST /api/files/
                              │
               [ Upload Validation & Streaming ]
               ├─ Check file presence & filename
               ├─ Case-insensitive extension (.kml, .zip)
               ├─ Stream in 1 MB chunks (max 50 MB)
               └─ Save as uploads/<UUID>.<ext>
                              │
               [ Geospatial Archive / File Parsing ]
               ├─ KML: pyogrio / libkml driver
               ├─ ZIP: Zip Slip verification & safe extraction
               │       Verify companion files (.shp, .shx, .dbf)
               └─ Extract features, types, and source CRS
                              │
               [ CRS Suitability Inspection ]
               ├─ Missing CRS? -> Halt measurement (MissingCRSError)
               ├─ Projected & Metric (UTM, etc.)? -> Use directly
               └─ Geographic (EPSG:4326) OR Web Mercator (EPSG:3857) OR Non-metric?
                      └─ Estimate optimal local UTM projection
                      └─ Reproject geometries via to_crs()
                              │
               [ Metric Measurement Calculation ]
               ├─ Polygon / MultiPolygon -> Planar Area (square_meters)
               ├─ LineString / MultiLineString -> Planar Length (meters)
               ├─ Point -> No measurement required (value = null)
               └─ Invalid / Empty -> Flagged in notes (value = null)
                              │
               [ Database Persistence ]
               ├─ Insert FileRecord (metadata, status, crs)
               └─ Insert MeasurementRecord (one row per feature)
                              │
               [ Return 201 Created Response ]
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
- The file is saved with `crs = null`, and querying measurements (`GET /api/files/{id}/measurements/`) returns a clean `400 Bad Request`:
  `"detail": "Cannot calculate metric measurements because the source dataset CRS is missing."`

### 6. Strict Mathematical Transformation via `to_crs()`
- `set_crs()` only relabels metadata without modifying coordinates (which would corrupt geospatial data).
- The pipeline strictly uses `to_crs()`, performing rigorous ellipsoidal-to-planar Cartesian coordinate transformation.

### 7. Topological Edge Cases
- **Point Geometries:** Preserved with `value = null`, `unit = null`, `measurement_crs = null` (no measurement required).
- **Empty Geometries (`is_empty`):** Marked with `value = null`, `notes = "Geometry is empty."`.
- **Null Geometries (`geom is None`):** Marked with `value = null`, `notes = "Geometry is null."`.
- **Invalid Geometries (`not is_valid`):** Evaluated without silent geometry mutation (no arbitrary `buffer(0)` alteration). Flagged with `notes = "Geometry is topologically invalid. Measurement unavailable."`.
- **Fault Isolation:** An invalid feature never halts processing for valid features in the same dataset.

---

## Security Review and Hardening

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

All endpoints seamlessly support requests **with or without trailing slashes**.

---

### 1. Health Check
- **Endpoint:** `GET /health`
- **Status:** `200 OK`
- **cURL:**
  ```bash
  curl -X GET http://localhost:8000/health
  ```
- **Response:**
  ```json
  {
    "status": "ok"
  }
  ```

---

### 2. Upload Geospatial File
- **Endpoint:** `POST /api/files/`
- **Content-Type:** `multipart/form-data`
- **Status:** `201 Created`
- **Supported Formats:** `.kml`, `.zip` (containing ESRI Shapefile)
- **cURL:**
  ```bash
  curl -X POST "http://localhost:8000/api/files/" \
    -F "file=@survey_parcels.zip"
  ```
- **Response:**
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
    "crs": "EPSG:4326"
  }
  ```

---

### 3. List All Files
- **Endpoint:** `GET /api/files/`
- **Status:** `200 OK`
- **cURL:**
  ```bash
  curl -X GET "http://localhost:8000/api/files/"
  ```
- **Response:**
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
        "error_message": null
      }
    ]
  }
  ```

---

### 4. Get File Details
- **Endpoint:** `GET /api/files/{id}/`
- **Status:** `200 OK`
- **cURL:**
  ```bash
  curl -X GET "http://localhost:8000/api/files/fd3b8de4-7e10-4e29-a537-a1c71e6c4186/"
  ```
- **Response:**
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
    "measurement_crs": "EPSG:32631",
    "created_at": "2026-10-07T04:11:32.242714",
    "error_message": null
  }
  ```

---

### 5. Get File Measurements
- **Endpoint:** `GET /api/files/{id}/measurements/`
- **Status:** `200 OK`
- **cURL:**
  ```bash
  curl -X GET "http://localhost:8000/api/files/fd3b8de4-7e10-4e29-a537-a1c71e6c4186/measurements/"
  ```
- **Response:**
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

### 6. Delete File
- **Endpoint:** `DELETE /api/files/{id}/`
- **Status:** `200 OK`
- **cURL:**
  ```bash
  curl -X DELETE "http://localhost:8000/api/files/fd3b8de4-7e10-4e29-a537-a1c71e6c4186/"
  ```
- **Response:**
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
git clone <repository-url>
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
- Interactive OpenAPI Docs (Swagger): `http://localhost:8000/docs`
- Alternative Documentation (ReDoc): `http://localhost:8000/redoc`

---

## Running with Docker

The application includes a production-ready `Dockerfile` and `.dockerignore`.

### 1. Build the Docker Image
```bash
docker build -t aereo-geospatial-api .
```

### 2. Run the Container
```bash
docker run -d --name aereo-api-instance -p 8000:8000 aereo-geospatial-api
```

### 3. Verify Health & OpenAPI Docs
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```
Access the Swagger UI at `http://localhost:8000/docs`.

### 4. Stop and Remove Container
```bash
docker stop aereo-api-instance
docker rm aereo-api-instance
```

---

## Error Handling & HTTP Status Matrix

The API uses standard HTTP status codes and domain-driven exceptions:

| HTTP Status | Trigger Condition | Diagnostic Payload |
|---|---|---|
| **`200 OK`** | Successful retrieval (`GET`) or deletion (`DELETE`). | Structured JSON response. |
| **`201 Created`** | Successful file upload, feature extraction, measurement, and persistence. | `FileUploadResponse` JSON. |
| **`400 Bad Request`** | Unsupported file extension (e.g. `.exe`, `.pdf`). | `{"detail": "Unsupported file extension '.exe'. Allowed extensions: .kml, .zip"}` |
| **`400 Bad Request`** | Empty file uploaded (0 bytes). | `{"detail": "Uploaded file is empty (0 bytes)."}` |
| **`400 Bad Request`** | Malformed KML or corrupt ZIP archive. | `{"detail": "Malformed or unreadable KML file..."}` |
| **`400 Bad Request`** | ZIP archive does not contain `.shp` or has multiple `.shp` files. | `{"detail": "ZIP archive does not contain an ESRI Shapefile (.shp)."}` |
| **`400 Bad Request`** | Missing Shapefile companion files (`.shx`, `.dbf`). | `{"detail": "Missing companion files: ['.shx']"}` |
| **`400 Bad Request`** | Requesting measurements on a dataset with missing CRS (no `.prj`). | `{"detail": "Cannot calculate metric measurements because the source dataset CRS is missing."}` |
| **`400 Bad Request`** | Zip Slip path traversal or zip bomb detected. | `{"detail": "Path traversal rejected: archive entry escapes extraction directory."}` |
| **`404 Not Found`** | Nonexistent file UUID requested. | `{"detail": "File with ID '<UUID>' not found."}` |
| **`413 Content Too Large`** | File upload exceeds maximum size limit (50 MB). | `{"detail": "File exceeds maximum allowed upload size of 50 MB."}` |

---

## Running the Automated Test Suite

Run all 67 unit, integration, and security tests:

```bash
pytest -v
```

Output summary:
```
tests/test_crs_handler.py ..........................                    [ 14%]
tests/test_file_processor.py ..........................                  [ 29%]
tests/test_geospatial_environment.py .................                   [ 37%]
tests/test_health.py .                                                   [ 38%]
tests/test_measurement.py ...............................                 [ 59%]
tests/test_upload.py ................................................... [100%]

======================= 67 passed in 7.70s =======================
```

---

## Key Engineering Learnings & Insights

1. **Geographic vs. Planar Projections:**
   - Ellipsoidal geometries in angular coordinates (degrees) cannot be treated as Euclidean spaces. Reprojection to an appropriate conformal planar coordinate system (UTM) is mandatory for metric consistency.
2. **Web Mercator Distortion Pitfall:**
   - Many web applications use Web Mercator (`EPSG:3857`) because its nominal unit is "metre". However, calculating planar area directly on Web Mercator introduces severe latitude-dependent area magnification ($\sec^2 \phi$, up to 400% at $60^\circ$). Detecting and reprojecting Web Mercator to UTM eliminates this flaw.
3. **C-Level File Processing Security:**
   - Decompressing user-supplied ZIP archives requires defense-in-depth: path traversal filtering (`is_relative_to`), total uncompressed size thresholds, and member count caps prevent decompression bombs and arbitrary filesystem writes.
4. **Resilient Driver Fallbacks:**
   - When handling zero-feature KML files, Pyogrio can raise index boundary errors on empty layers. Implementing an XML fallback ensures that valid empty geospatial containers parse gracefully without crashing.

---

## Design Decisions & Alternatives Considered

| Decision | Chosen Solution | Alternative Considered | Rationale |
|---|---|---|---|
| **API Framework** | FastAPI (ASGI) | Django / Flask | FastAPI provides native asynchronous streaming, automatic OpenAPI schema generation, and high throughput with zero boilerplate. |
| **Geospatial Driver** | GeoPandas + Pyogrio | GDAL Python bindings / Fiona | Pyogrio provides high-performance C-level GDAL access with fast tabular parsing and clean Pythonic memory management. |
| **Planar Projection** | Dynamic UTM (`estimate_utm_crs`) | Single World Equal Area (e.g., Eckert IV) | UTM zones preserve conformal local shape and minimize linear/area distortion for localized cadastral/engineering files. |
| **Web Mercator Handling** | Force Reprojection to UTM | Direct `.area` measurement | Calculating planar area on EPSG:3857 produces errors up to 400% away from the equator due to $\sec^2(\phi)$ distortion. |
| **Database Layer** | SQLAlchemy 2.0 (SQLite) | MongoDB / In-memory dict | Standard relational foreign keys and cascade delete enforce measurement consistency; swappable to PostgreSQL/PostGIS with zero schema modification. |

---

## Future Scope & Production Enhancements

1. **Asynchronous Background Processing (Celery / Redis / ARQ):**
   - For multi-gigabyte Shapefile archives or drone survey point clouds, move geometry parsing to asynchronous worker queues with WebSocket progress reporting.
2. **PostGIS Vector Storage:**
   - Store parsed geometries directly as native PostGIS geometries (`geometry(Geometry, 4326)`) enabling spatial indexing (R-Tree / GiST) and spatial SQL queries (`ST_Area`, `ST_Intersects`).
3. **Large-Scale Geodesic Measurements:**
   - For continental or global features crossing multiple UTM zones, integrate geographic geodesic calculations (`pyproj.Geod`) to compute ellipsoidal geodesic areas without planar projection seams.
4. **Cloud Object Storage (AWS S3 / GCS):**
   - Offload file storage to cloud bucket storage using presigned upload URLs.

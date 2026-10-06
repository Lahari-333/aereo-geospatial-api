# Geospatial File Measurement API

## Overview

The Geospatial File Measurement API is a production-oriented backend service designed to parse geospatial files (KML files and ZIP archives containing ESRI Shapefiles), extract feature properties and geometries, handle Coordinate Reference System (CRS) transformations, and compute geometric measurements such as polygon areas and linestring lengths.

This project is organized with a clean layered architecture separating HTTP routing, business logic, persistence models, request/response validation schemas, and application configuration.

## Current Status

> **Note**: This repository is currently in the **initial setup stage** (Stage 1).
> 
> The application architecture, directory structure, configuration management, and a minimal working FastAPI application with health check endpoints are initialized.
> 
> **Geospatial file processing, parsing, geometric measurements, and persistent storage are not implemented yet** and will be introduced deliberately in subsequent stages.

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Configuration & Validation:** Pydantic / Pydantic Settings
- **Testing:** Pytest, HTTPX

*(Geospatial libraries such as GeoPandas, Shapely, and PyProj will be integrated in subsequent stages.)*

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
│   │       └── files.py            # Endpoints for file operations (to be implemented)
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
│   │   ├── file_processor.py       # File parsing and extraction (to be implemented)
│   │   ├── measurement.py          # Metric calculations (to be implemented)
│   │   └── crs_handler.py          # CRS reprojection & validation (to be implemented)
│   │
│   └── storage/                    # Database and persistence management
│       ├── __init__.py
│       └── database.py
│
├── tests/                          # Automated tests
│   ├── __init__.py
│   └── test_health.py              # Health check endpoint test
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

Verify service availability by querying the health endpoint:

### Request
```bash
curl -X GET http://localhost:8000/health
```

### Expected Response
```json
{
  "status": "ok"
}
```

## Running Tests

Run the test suite using `pytest`:

```bash
pytest
```

# AI Agreement Extraction LLM Service

## Overview

The AI Agreement Extraction LLM Service is a local Large Language Model (LLM)-based API responsible for extracting important information from agreement PDF documents.

The service receives a PDF agreement file from an external system, extracts the document text, processes the content using a locally hosted **Qwen2.5:7B** model through **Ollama**, and returns structured JSON containing extracted agreement information, confidence scores, and evidence references.

This service is designed as an independent LLM extraction component that can be integrated with the main Agreement Management System.

---

# System Workflow

```text
External System
   |
   |  PDF Agreement Upload
   v
FastAPI LLM Extraction API
   |
   v
PDF Text Extraction
   |
   v
Qwen2.5:7B (Local Ollama Model)
   |
   v
Structured JSON Response
   |
   v
External System
```

---

# Features

- PDF agreement processing
- Local LLM inference using Ollama
- Qwen2.5:7B model integration
- Agreement information extraction
- Structured JSON response generation
- Confidence score generation
- Evidence extraction with page references
- Fully local processing without external AI APIs

---

# Extracted Information

The service extracts the following agreement details:

| Field | Description |
|---|---|
| Agreement Number | Unique agreement identifier |
| Title | Agreement document title |
| Vendor / Customer | Parties involved in the agreement |
| Start Date | Agreement effective date |
| Expiry Date | Agreement termination date |
| Value | Agreement amount and currency |
| Agreement Classification | Determines whether the document is an agreement |

---

# Technology Stack

## Backend

- Python 3
- FastAPI
- Uvicorn

## Database

- MySQL 8 (via PyMySQL)

## Document Processing

- PyPDF

## Artificial Intelligence

- Ollama
- Qwen2.5:7B

---

# Project Structure

```text
AI_Agreement_LLM_Service/
│
├── main.py              # FastAPI application and LLM extraction logic
├── requirements.txt     # Python dependency list
├── README.md            # Project documentation
└── .gitignore           # Git ignored files configuration
```

---

# Prerequisites

Before running the project, install:

- Python 3.10 or higher
- Ollama
- Qwen2.5:7B model
- MySQL 8.0 or higher

---

# MySQL Setup

The service stores the extraction job queue and saved agreements in MySQL. The database and tables are created automatically on startup.

## Install and Start MySQL (macOS)

```bash
brew install mysql
brew services start mysql
```

Optionally set a root password:

```bash
mysql_secure_installation
```

## Configure Connection Settings

Copy the example environment file and fill in your MySQL password and API keys:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| MYSQL_HOST | 127.0.0.1 | MySQL server host |
| MYSQL_PORT | 3306 | MySQL server port |
| MYSQL_USER | root | MySQL user |
| MYSQL_PASSWORD | (empty) | MySQL password |
| MYSQL_DATABASE | amp_extraction | Database name (created if missing) |

---

# Ollama Setup

## Install Ollama

Download and install Ollama:

https://ollama.com/

## Download Qwen2.5:7B Model

Run:

```bash
ollama pull qwen2.5:7b
```

Verify installation:

```bash
ollama list
```

Expected output:

```
qwen2.5:7b
```

---

# Installation Guide

## 1. Clone Repository

```bash
git clone <repository-url>
cd AI_Agreement_LLM_Service
```

---

## 2. Create Virtual Environment

### macOS / Linux

```bash
python3 -m venv venv
```

Activate:

```bash
source venv/bin/activate
```

### Windows

Create:

```bash
python -m venv venv
```

Activate:

```bash
venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Running the Service

Start the FastAPI server:

```bash
python3 main.py
```

The API will start at:

```
http://127.0.0.1:8000
```

---

# API Documentation

FastAPI Swagger UI:

```
http://127.0.0.1:8000/docs
```

---

# API Endpoint

## Extract Agreement Information

### Endpoint

```http
POST /extract
```

### Request Type

```
multipart/form-data
```

### Parameter

| Parameter | Type | Description        |
| --------- | ---- | ------------------ |
| file      | PDF  | Agreement document |

---

# Example JSON Response

```json
{
  "schema_version": "1.0",
  "document_classification": {
    "is_agreement": true,
    "confidence": 0.98
  },
  "fields": {
    "agreement_number": {
      "value": "AG-001",
      "confidence": 0.95,
      "source": "explicit",
      "evidence": {
        "page": 1,
        "text": "Agreement No: AG-001"
      }
    }
  },
  "model": {
    "name": "qwen2.5:7b"
  }
}
```

---

# Duplicate Handling

The service avoids saving the same agreement twice in the `agreements` table:

| Case | What happens |
| ---- | ------------ |
| Exact same file (same SHA-256) | The model is **not** run again. The saved result is returned immediately. `POST /v1/extractions` responds with `"status": "completed"` and the result is available from `/v1/extractions/status` straight away. |
| Different file, same `agreement_number` and `vendor_customer` (e.g. a rescan) | The model runs, and the existing `agreements` row is **updated** (same reference, new `updated_at`) instead of inserting a new row. |
| Anything else (including documents with no agreement number) | A new row is inserted. |

Every processed file is linked to its agreement in the `agreement_files` table (`file_sha256` → `agreement_reference`), so an older copy of an agreement is still recognised after a rescan has updated the row.

The legacy `POST /extract` endpoint returns the stored agreement's `reference` plus a `duplicate` field: `"same_file"`, `"same_agreement_number"` or `null`.

On startup, `init_db()` adds the `updated_at` column and the `(agreement_number, vendor_customer)` index to an existing `agreements` table if they are missing; existing rows are kept.

---

# Model Information

## Model

```
Qwen2.5:7B
```

## Runtime

```
Ollama Local Runtime
```

## Processing

```text
PDF
 ↓
Text Extraction
 ↓
Qwen2.5:7B
 ↓
JSON Extraction Result
```

---

# Development Scope

This service is responsible for:

✅ Receiving PDF documents
✅ Extracting document text
✅ Processing agreement content using LLM
✅ Generating structured JSON output

The following components are handled by the main system:

* User interface
* Agreement management workflow
* Database storage
* User authentication
* Business process management

---

# Troubleshooting

## Ollama Connection Error

Check available models:

```bash
ollama list
```

Start Ollama service:

```bash
ollama serve
```

---

## Missing Python Dependencies

Run:

```bash
pip install -r requirements.txt
```

---

## API Not Starting

Check:

```bash
python3 --version
```

and ensure the virtual environment is activated.

---

# Security Notes

* The LLM runs locally using Ollama.
* Document content is not sent to external AI providers.
* Uploaded agreement files are processed only during API execution.

---

# Author

AI Agreement Extraction Team

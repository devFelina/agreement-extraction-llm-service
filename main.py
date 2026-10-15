import hashlib
import io
import json
import re
import time
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_bytes
import ollama

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Configure Tesseract binary path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ==========================================================
# APP & DATABASE CONFIG
# ==========================================================

app = FastAPI(
    title="AI Agreement Extraction Service",
    version="1.1"
)

MODEL_NAME = "llama3.2:3b"

# SQLite Database setup
DATABASE_URL = "sqlite:///./extractions.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ExtractionRecord(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, index=True)
    file_hash = Column(String(64), unique=True, index=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    agreement_number = Column(String(100), nullable=True)
    vendor_customer = Column(String(255), nullable=True)
    contract_value = Column(String(100), nullable=True)
    extraction_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Create table on startup
Base.metadata.create_all(bind=engine)


# ==========================================================
# JSON OUTPUT TEMPLATE
# ==========================================================

OUTPUT_SCHEMA = {
    "schema_version": "1.0",

    "document_classification": {
        "is_agreement": False,
        "confidence": 0.0
    },

    "fields": {
        "agreement_number": {
            "value": None,
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        },

        "title": {
            "value": None,
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        },

        "vendor_customer": {
            "value": None,
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        },

        "start_date": {
            "value": None,
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        },

        "expiry_date": {
            "value": None,
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        },

        "value": {
            "value": {
                "amount": None,
                "currency": None
            },
            "confidence": 0.0,
            "source": None,
            "evidence": {
                "page": None,
                "text": None
            }
        }
    },

    "warnings": [],

    "document": {
        "page_count": 0,
        "ocr_applied": False,
        "language": "en"
    }
}


# ==========================================================
# UTILS & HELPERS
# ==========================================================

def compute_sha256(file_bytes: bytes) -> str:
    """Calculates SHA-256 fingerprint of the binary file content."""
    return hashlib.sha256(file_bytes).hexdigest()


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int, bool]:
    """Extracts text page-by-page with Tesseract OCR fallback."""
    reader = PdfReader(io.BytesIO(file_bytes))
    page_count = len(reader.pages)
    pages = []
    ocr_applied = False

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""

        if len(text.strip()) < 50:
            ocr_applied = True
            try:
                images = convert_from_bytes(
                    file_bytes,
                    first_page=page_number,
                    last_page=page_number,
                    dpi=200
                )
                if images:
                    text = pytesseract.image_to_string(images[0], lang='eng')
            except Exception as e:
                print(f"OCR Error on page {page_number}: {e}")

        if text.strip():
            pages.append(f"\n--- PAGE {page_number} ---\n{text.strip()}")

    full_text = "\n".join(pages)
    return full_text, page_count, ocr_applied


def clean_json_response(output: str) -> str:
    text = output.strip()
    text = text.replace("```json", "").replace("```", "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        text = text[start:end+1]

    return text.strip()


def validate_result(result: dict) -> dict:
    if "fields" not in result:
        result["fields"] = {}

    required_fields = [
        "agreement_number",
        "title",
        "vendor_customer",
        "start_date",
        "expiry_date",
        "value"
    ]

    for field in required_fields:
        if field not in result["fields"]:
            result["fields"][field] = OUTPUT_SCHEMA["fields"][field]

    for field in result["fields"].values():
        if isinstance(field, dict) and "confidence" in field:
            if field["confidence"] > 1:
                field["confidence"] = 1.0
            elif field["confidence"] < 0:
                field["confidence"] = 0.0

    return result


# ==========================================================
# ENDPOINTS
# ==========================================================

@app.get("/")
def home():
    return {
        "service": "Agreement Extraction API",
        "model": MODEL_NAME,
        "database": "connected",
        "status": "running"
    }


@app.post("/extract")
async def extract_agreement(file: UploadFile = File(...)):
    start_time = time.time()

    if not file.filename:
        raise HTTPException(400, "Filename missing")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    try:
        pdf_bytes = await file.read()
        file_hash = compute_sha256(pdf_bytes)

        db = SessionLocal()
        try:
            # 1. CHECK CACHE (DATABASE LOOKUP BY SHA-256 HASH)
            existing_record = db.query(ExtractionRecord).filter(ExtractionRecord.file_hash == file_hash).first()
            if existing_record:
                cached_json = json.loads(existing_record.extraction_json)
                cached_json["cached"] = True
                cached_json["processing_ms"] = int((time.time() - start_time) * 1000)
                return cached_json
        finally:
            db.close()

        # 2. PROCESS NEW PDF (TEXT / OCR EXTRACTION)
        text, page_count, ocr_applied = extract_pdf_text(pdf_bytes)

        if not text.strip():
            raise HTTPException(400, "Unable to extract text from PDF (Scan unreadable)")

        # 3. CALL OLLAMA LLM
        prompt = f"""
You are an enterprise agreement extraction AI.

Extract information from the agreement document.
Return ONLY JSON.

Required fields:
- agreement_number
- title
- vendor_customer
- start_date
- expiry_date
- value.amount
- value.currency
- is_agreement

Rules:
1. Never invent information.
2. Missing values must be null.
3. Evidence text must come directly from the document.
4. Page number must be numeric.
5. Confidence must be a float between 0 and 1.
6. Source must be only: 'explicit' or 'inferred'.
7. Dates format: YYYY-MM-DD
8. Currency must be ISO 4217 code (e.g., LKR, USD).

JSON FORMAT:
{json.dumps(OUTPUT_SCHEMA, indent=2)}

DOCUMENT:
{text}
"""

        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a legal document extraction API. Return only valid JSON. Do not use markdown. Do not explain."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format={"type": "object"},
            options={
                "temperature": 0,
                "num_ctx": 4096
            }
        )

        raw_output = response["message"]["content"]
        cleaned = clean_json_response(raw_output)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            print("MODEL OUTPUT ERROR:", raw_output)
            raise HTTPException(500, "LLM returned invalid JSON")

        result = validate_result(result)

        # Attach metadata
        result["cached"] = False
        result["model"] = {
            "name": MODEL_NAME,
            "version": "latest"
        }

        result["processing_ms"] = int((time.time() - start_time) * 1000)

        if "document" not in result:
            result["document"] = {}

        result["document"]["page_count"] = page_count
        result["document"]["ocr_applied"] = ocr_applied
        result["document"]["language"] = "en"

        if ocr_applied and len(text.strip()) < 150:
            if "warnings" not in result:
                result["warnings"] = []
            result["warnings"].append({
                "code": "LOW_SCAN_QUALITY",
                "field": None,
                "message": "OCR confidence low. Document text recovery was poor."
            })

        # 4. SAVE NEW RESULT TO DATABASE
        db = SessionLocal()
        try:
            ag_num = result["fields"].get("agreement_number", {}).get("value")
            vc_name = result["fields"].get("vendor_customer", {}).get("value")
            val_amt = result["fields"].get("value", {}).get("value", {}).get("amount") if isinstance(result["fields"].get("value", {}).get("value"), dict) else None

            new_record = ExtractionRecord(
                file_hash=file_hash,
                file_name=file.filename,
                agreement_number=ag_num,
                vendor_customer=vc_name,
                contract_value=str(val_amt) if val_amt else None,
                extraction_json=json.dumps(result)
            )
            db.add(new_record)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Database Save Error: {e}")
        finally:
            db.close()

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ==========================================================
# RUN
# ==========================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
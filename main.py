import io
import json
import re
import time

from fastapi import FastAPI, UploadFile, File, HTTPException
from pypdf import PdfReader
import ollama


# ==========================================================
# APP CONFIG
# ==========================================================

app = FastAPI(
    title="AI Agreement Extraction Service",
    version="1.0"
)


MODEL_NAME = "qwen2.5:7b"


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
# PDF TEXT EXTRACTION
# ==========================================================

def extract_pdf_text(file_bytes):

    reader = PdfReader(
        io.BytesIO(file_bytes)
    )

    pages = []

    page_count = len(reader.pages)


    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):

        text = page.extract_text()


        if text:

            pages.append(
                f"""
--- PAGE {page_number} ---
{text}
"""
            )


    return (
        "\n".join(pages),
        page_count
    )



# ==========================================================
# CLEAN QWEN RESPONSE
# ==========================================================

def clean_json_response(output):

    text = output.strip()


    # Remove markdown

    text = text.replace(
        "```json",
        ""
    )


    text = text.replace(
        "```",
        ""
    )


    # Remove thinking tags if model produces them

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL
    )


    # Extract JSON object

    start = text.find("{")

    end = text.rfind("}")


    if start != -1 and end != -1:

        text = text[start:end+1]


    return text.strip()



# ==========================================================
# VALIDATE RESULT
# ==========================================================

def validate_result(result):


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

            result["fields"][field] = (
                OUTPUT_SCHEMA["fields"][field]
            )



    # confidence checking

    for field in result["fields"].values():

        if "confidence" in field:

            if field["confidence"] > 1:

                field["confidence"] = 1


            if field["confidence"] < 0:

                field["confidence"] = 0



    return result




# ==========================================================
# HOME
# ==========================================================

@app.get("/")
def home():

    return {

        "service":
        "Agreement Extraction API",

        "model":
        MODEL_NAME,

        "status":
        "running"

    }




# ==========================================================
# EXTRACTION ENDPOINT
# ==========================================================

@app.post("/extract")
async def extract_agreement(

        file: UploadFile = File(...)

):


    start_time = time.time()


    if not file.filename:

        raise HTTPException(
            400,
            "Filename missing"
        )


    if not file.filename.lower().endswith(".pdf"):

        raise HTTPException(
            400,
            "Only PDF files are supported"
        )



    try:


        # Read PDF

        pdf_bytes = await file.read()



        text, page_count = extract_pdf_text(
            pdf_bytes
        )



        if not text.strip():

            raise HTTPException(

                400,

                "Unable to extract text from PDF"

            )



        # ==================================================
        # LLM PROMPT
        # ==================================================


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
3. Evidence text must come from the document.
4. Page number must be numeric.
5. Confidence must be between 0 and 1.
6. Source must be only:
   explicit
   inferred
7. Dates format:
   YYYY-MM-DD
8. Currency must be ISO 4217.


JSON FORMAT:

{json.dumps(OUTPUT_SCHEMA, indent=2)}


DOCUMENT:

{text}

"""



        response = ollama.chat(

            model=MODEL_NAME,


            messages=[


                {

                    "role":"system",

                    "content":
                    """
You are a legal document extraction API.
Return only valid JSON.
Do not use markdown.
Do not explain.
"""

                },


                {

                    "role":"user",

                    "content":prompt

                }

            ],


            format={
                "type":"object"
            },


            options={

                "temperature":0,

                "num_ctx":16384

            }

        )



        raw_output = response["message"]["content"]



        cleaned = clean_json_response(
            raw_output
        )



        try:

            result = json.loads(
                cleaned
            )


        except json.JSONDecodeError:


            print(
                "MODEL OUTPUT ERROR:"
            )

            print(raw_output)


            raise HTTPException(

                500,

                "LLM returned invalid JSON"

            )



        result = validate_result(
            result
        )



        # Add metadata

        result["model"] = {

            "name":
            MODEL_NAME,

            "version":
            "latest"

        }


        result["processing_ms"] = int(

            (time.time()-start_time)
            *
            1000

        )


        result["document"]["page_count"] = (
            page_count
        )


        return result



    except HTTPException:

        raise



    except Exception as e:


        raise HTTPException(

            500,

            str(e)

        )





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
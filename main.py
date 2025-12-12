from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
import base64
import time
import uuid
import threading
from typing import Dict
import uvicorn

app = FastAPI(title="Temporary PDF Store")

# ----------------------------------------------------
# CONFIG (no external environment variables required)
# ----------------------------------------------------
EXPIRY_SECONDS = 600  # PDF expires after 10 minutes
SCHEME = "http"       # Use https automatically when hosted on Render
BASE_DOMAIN = "https://pdf-to-html-link-generator.onrender.com"      # Will be filled manually after Render deploy if needed

# ----------------------------------------------------
# IN-MEMORY TEMPORARY STORAGE
# ----------------------------------------------------
PDF_STORE: Dict[str, Dict] = {}
LOCK = threading.Lock()


class StoreRequest(BaseModel):
    pdf_base64: str


# ----------------------------------------------------
# BACKGROUND CLEANUP THREAD
# ----------------------------------------------------
def cleanup_worker():
    """Remove expired PDFs every 30 seconds."""
    while True:
        now = time.time()
        expired_keys = []

        with LOCK:
            for key, val in PDF_STORE.items():
                if val["expires"] < now:
                    expired_keys.append(key)

            for key in expired_keys:
                PDF_STORE.pop(key, None)

        time.sleep(30)


threading.Thread(target=cleanup_worker, daemon=True).start()


# ----------------------------------------------------
# STORE PDF AND RETURN SHORT-LIVED URL
# ----------------------------------------------------
@app.post("/store_pdf")
def store_pdf(req: StoreRequest):
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    pdf_id = uuid.uuid4().hex[:8]  # short ID
    expires_at = time.time() + EXPIRY_SECONDS

    with LOCK:
        PDF_STORE[pdf_id] = {
            "pdf": pdf_bytes,
            "expires": expires_at
        }

    # Automatically adjust link based on deployment
    if BASE_DOMAIN:
        pdf_url = f"{SCHEME}://{BASE_DOMAIN}/pdf/{pdf_id}"
    else:
        pdf_url = f"/pdf/{pdf_id}"  # relative path works on Render

    return {
        "pdf_url": pdf_url,
        "expires_at": expires_at
    }


# ----------------------------------------------------
# SERVE PDF INLINE
# ----------------------------------------------------
@app.get("/pdf/{pdf_id}")
def get_pdf(pdf_id: str):
    with LOCK:
        item = PDF_STORE.get(pdf_id)

    if not item:
        return Response(b"Invalid or expired link", media_type="text/plain", status_code=404)

    if time.time() > item["expires"]:
        with LOCK:
            PDF_STORE.pop(pdf_id, None)
        return Response(b"Expired link", media_type="text/plain", status_code=410)

    return Response(
        content=item["pdf"],
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=preview.pdf"}
    )


# ----------------------------------------------------
# ENTRY POINT (local run + Render compatible)
# ----------------------------------------------------
if __name__ == "__main__":
    import os

    # Render requires running on 0.0.0.0
    HOST = "0.0.0.0"

    # Render provides a dynamic port via environment variable
    PORT = int(os.environ.get("PORT", 9000))

    print(f"🚀 PDF Store running at http://{HOST}:{PORT}")

    uvicorn.run(
        "main:app",   # must match this file name: main.py
        host=HOST,
        port=PORT,
        reload=False,
    )

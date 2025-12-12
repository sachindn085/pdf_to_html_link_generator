# # pdf_store_server.py
# from fastapi import FastAPI, HTTPException, Response
# from pydantic import BaseModel
# import base64
# import time
# import uuid
# import threading
# from typing import Dict
# import uvicorn
# import os

# app = FastAPI(title="Temporary PDF Store")

# # In-memory store: id -> {pdf: bytes, expires: timestamp}
# PDF_STORE: Dict[str, Dict] = {}
# LOCK = threading.Lock()

# # expiry seconds (default 300s). Can be overridden via env var PDF_STORE_EXPIRY.
# EXPIRY_SECONDS = int(os.environ.get("PDF_STORE_EXPIRY", "300"))

# class StoreRequest(BaseModel):
#     pdf_base64: str

# def cleanup_worker():
#     """Background thread to remove expired PDFs every 30 seconds."""
#     while True:
#         now = time.time()
#         expired = []
#         with LOCK:
#             for key, val in list(PDF_STORE.items()):
#                 if val["expires"] < now:
#                     expired.append(key)
#             for key in expired:
#                 del PDF_STORE[key]
#         time.sleep(30)

# # start cleanup thread
# thread = threading.Thread(target=cleanup_worker, daemon=True)
# thread.start()

# @app.post("/store_pdf")
# def store_pdf(req: StoreRequest):
#     """
#     Accepts JSON: {"pdf_base64": "<base64>"}
#     Returns: {"pdf_url": "http://host:port/pdf/<id>", "expires_at": <timestamp>}
#     """
#     try:
#         pdf_bytes = base64.b64decode(req.pdf_base64)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

#     pdf_id = uuid.uuid4().hex[:8]
#     expires_at = time.time() + EXPIRY_SECONDS

#     with LOCK:
#         PDF_STORE[pdf_id] = {
#             "pdf": pdf_bytes,
#             "expires": expires_at
#         }

#     host = os.environ.get("PDF_STORE_HOST", "127.0.0.1")
#     port = int(os.environ.get("PDF_STORE_PORT", "9000"))
#     scheme = os.environ.get("PDF_STORE_SCHEME", "http")  # allow https if behind proxy
#     pdf_url = f"{scheme}://{host}:{port}/pdf/{pdf_id}"
#     return {"pdf_url": pdf_url, "expires_at": expires_at}

# @app.get("/pdf/{pdf_id}")
# def get_pdf(pdf_id: str):
#     """
#     Serves PDF if present and not expired; inline disposition for browser view.
#     """
#     with LOCK:
#         item = PDF_STORE.get(pdf_id)

#     if not item:
#         return Response(content=b"Invalid or expired link", media_type="text/plain", status_code=404)

#     if time.time() > item["expires"]:
#         # remove expired item
#         with LOCK:
#             PDF_STORE.pop(pdf_id, None)
#         return Response(content=b"Link expired", media_type="text/plain", status_code=410)

#     return Response(
#         content=item["pdf"],
#         media_type="application/pdf",
#         headers={"Content-Disposition": "inline; filename=preview.pdf"}
#     )

# if __name__ == "__main__":
#     # Local/test run
#     uvicorn.run(
#         "store:app",
#         # host=os.environ.get("PDF_STORE_HOST", "127.0.0.1"),
#         port="9000",
#         reload=True,
#     )








# store.py
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
import base64
import time
import uuid
import threading
from typing import Dict
import uvicorn

app = FastAPI(title="Temporary PDF Store")

# ----------------------------
# FIXED CONFIG (no environment variables)
# ----------------------------
HOST = "127.0.0.1"
PORT = 9000
EXPIRY_SECONDS = 600  # 10 minutes
SCHEME = "http"       # https only when hosted externally
BASE_DOMAIN = ""      # filled only when deployed
                      # (kept empty for local run)

# ----------------------------
# IN-MEMORY TEMPORARY STORAGE
# ----------------------------
PDF_STORE: Dict[str, Dict] = {}
LOCK = threading.Lock()


class StoreRequest(BaseModel):
    pdf_base64: str


def cleanup_worker():
    """Background thread to remove expired PDFs every 30 seconds."""
    while True:
        now = time.time()
        expired = []
        with LOCK:
            for key, val in list(PDF_STORE.items()):
                if val["expires"] < now:
                    expired.append(key)
            for key in expired:
                PDF_STORE.pop(key, None)
        time.sleep(30)


# Start background cleanup thread
threading.Thread(target=cleanup_worker, daemon=True).start()


# ----------------------------
# STORE PDF AND RETURN SHORT URL
# ----------------------------
@app.post("/store_pdf")
def store_pdf(req: StoreRequest):
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    pdf_id = uuid.uuid4().hex[:8]
    expires_at = time.time() + EXPIRY_SECONDS

    with LOCK:
        PDF_STORE[pdf_id] = {
            "pdf": pdf_bytes,
            "expires": expires_at
        }

    # Local preview URL
    if BASE_DOMAIN:
        pdf_url = f"{SCHEME}://{BASE_DOMAIN}/pdf/{pdf_id}"
    else:
        pdf_url = f"http://{HOST}:{PORT}/pdf/{pdf_id}"

    return {"pdf_url": pdf_url, "expires_at": expires_at}


# ----------------------------
# SERVE PDF INLINE
# ----------------------------
@app.get("/pdf/{pdf_id}")
def get_pdf(pdf_id: str):
    with LOCK:
        item = PDF_STORE.get(pdf_id)

    if not item:
        return Response(content=b"Invalid or expired link", media_type="text/plain", status_code=404)

    if time.time() > item["expires"]:
        with LOCK:
            PDF_STORE.pop(pdf_id, None)
        return Response(content=b"Expired link", media_type="text/plain", status_code=410)

    return Response(
        content=item["pdf"],
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=preview.pdf"}
    )


# ----------------------------
# FORCE LOCAL RUN USING python store.py
# ----------------------------
if __name__ == "__main__":
    print(f"🚀 PDF Store running at http://{HOST}:{PORT}")
    uvicorn.run(
        "store:app",   # MUST MATCH CURRENT FILENAME: store.py → store:app
        host=HOST,
        port=PORT,
        reload=False,
    )

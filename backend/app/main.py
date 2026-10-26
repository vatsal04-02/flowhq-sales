from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import router
from app.api.routes_campaigns import router as campaigns_router
from app.api.routes_inbox import router as inbox_router
from app.core.logging import configure_logging
from app.db import get_engine

configure_logging()
app = FastAPI(title="FlowHQ Outreach OS", version="0.1.0", openapi_url="/api/v1/openapi.json",
              docs_url="/api/v1/docs")
app.include_router(router, prefix="/api/v1")
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(inbox_router, prefix="/api/v1")


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail
    if not (isinstance(detail, dict) and "error" in detail):
        detail = {"error": {"code": "http_error", "message": str(detail), "details": {}}}
    return JSONResponse(detail, status_code=exc.status_code)


@app.get("/healthz")
def healthz():
    with get_engine().connect() as c:
        c.execute(text("select 1"))
    return {"status": "ok"}

"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000   (from ./backend)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, settings as default_settings
from app.services.recommendation_service import RecommendationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Optional[Settings] = None, engine: Optional[RecommendationEngine] = None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Build once: catalog, embeddings and the FAISS index are reused by every request.
        app.state.engine = engine or RecommendationEngine.build(settings)
        yield

    app = FastAPI(
        title="Occasion-Based Product Recommendation API",
        version="1.0.0",
        description="Hybrid semantic (MiniLM + FAISS) and lexical recommendations from the supplied catalog.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body" and not isinstance(p, int)),
             "message": str(e.get("msg", "Invalid value")).removeprefix("Value error, ")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": "; ".join(e["message"] for e in errors),
                                                      "errors": errors})

    app.include_router(router)
    return app


app = create_app()

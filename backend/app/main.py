from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .db import Base, engine
from .config import settings
from .routes import auth, documents, chat, timeline, properties
from .rate_limit import limiter

Base.metadata.create_all(bind=engine)

app = FastAPI(title="NDIAH MVP")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Zu viele Anfragen. Limit: {exc.detail}. Bitte eine Minute warten."},
    )


@app.on_event("startup")
def validate_settings():
    if not settings.OPENAI_API_KEY.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Set it in backend/.env before starting the API."
        )


app.include_router(auth.router)
app.include_router(properties.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(timeline.router)


@app.get("/health")
def health():
    return {"ok": True}

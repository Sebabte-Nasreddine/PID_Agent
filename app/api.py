from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

from app.routers.extraction import router as extraction_router

app = FastAPI(
    title="PID Extraction API",
    description="Extraction d'équipements, instruments et pipelines depuis des P&ID.",
    version="0.1.0",
)

app.include_router(extraction_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
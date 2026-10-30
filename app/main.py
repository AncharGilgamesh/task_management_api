from fastapi import FastAPI

app = FastAPI(
    title="Task Management API",
    description="REST API для управления проектами и задачами.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Welcome to Task Management API"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

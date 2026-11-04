from fastapi import FastAPI

from app.routers import categories, users

app = FastAPI(title="Teleiosis API")
app.include_router(users.router)
app.include_router(categories.router)


@app.get("/health")
def health():
    return {"status": "ok"}
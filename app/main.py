from fastapi import FastAPI

from app.routers import categories, contents, users

app = FastAPI(title="Teleiosis API")
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(contents.router)


@app.get("/health")
def health():
    return {"status": "ok"}
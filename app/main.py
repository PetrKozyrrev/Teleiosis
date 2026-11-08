from fastapi import FastAPI

from app.routers import auth, categories, contents, password_reset, users

app = FastAPI(title="Teleiosis API")
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(categories.router)
app.include_router(contents.router)


@app.get("/health")
def health():
    return {"status": "ok"}
from fastapi import FastAPI

app = FastAPI(title="Teleiosis API")


@app.get("/health")
def health():
    return {"status": "ok"}
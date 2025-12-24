from app.main import app

# Allows: python -m app
if __name__ == "__main__":
    import uvicorn

    from app.settings import settings

    uvicorn.run(app, host=settings.host, port=settings.port)

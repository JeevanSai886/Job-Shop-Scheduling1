"""Cloud entry point: serve the built React app and existing FastAPI routes on one port."""

from fastapi.staticfiles import StaticFiles

from backend.main import app

# Keep /api/... and /docs routes registered in main.py before the catch-all mount.
# The frontend uses same-origin /api requests, so it needs no public CORS settings.
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

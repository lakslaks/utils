from api_server import app
import funcs  # noqa: F401 — import triggers @api decorators, registering routes

# uvicorn main:app --reload
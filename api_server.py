#api_server.py

from fastapi import FastAPI
from pydantic import create_model
import inspect
import asyncio
import requests
from threading import Lock

app = FastAPI()
_call_counts: dict[str, int] = {}
_lock = Lock()


def api(available: bool = True):
    """Decorator that exposes a function as a POST endpoint."""
    def wrapper(func):
        name = func.__name__
        _call_counts[name] = 0

        if not available:
            return func

        Model = create_model(
            f"{name}_model",
            **{p: (param.annotation, ...) for p, param in inspect.signature(func).parameters.items()}
        )

        @app.post(f"/{name}")
        async def _endpoint(payload: Model):
            kwargs = payload.dict()
            with _lock:
                _call_counts[name] += 1
                count = _call_counts[name]

            if inspect.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: func(**kwargs))

            return {"result": result, "call_count": count}

        return func
    return wrapper


def simulate(func: callable, payload: dict, base_url: str = "http://localhost:8000"):
    """Call a registered API endpoint by its function reference."""
    url = f"{base_url}/{func.__name__}"
    resp = requests.post(url, json=payload)
    return resp.json()
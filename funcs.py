from api_server import api, simulate

@api(available=True)      # was @app — wrong object entirely
def total(x: int, y: int) -> int:
    """Add two integers."""
    return x + y
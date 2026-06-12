"""FastAPI serving layer for the DataOps Knowledge Hub.

Submodules are intentionally NOT eagerly imported here — `create_app` lives in
`src.api.app` and the uvicorn entry point is `src.api.main:app`. Importing
this package shouldn't pull in the full LlamaIndex stack.
"""
__all__ = ["create_app"]

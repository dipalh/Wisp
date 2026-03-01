"""
Root folder registry — REST API.

Routes
------
  POST   /api/v1/roots        Register a new root folder
  GET    /api/v1/roots        List all registered roots
  DELETE /api/v1/roots        Clear all registered roots
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import services.roots as roots_store

router = APIRouter()


class RootAdd(BaseModel):
    path: str


@router.post("", summary="Register a root folder")
async def add_root(body: RootAdd):
    """Resolve and register *path* as a watched root.

    Returns the resolved path and the full list of current roots.
    """
    p = Path(body.path)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {body.path}")
    resolved = roots_store.add_root(str(p))
    return {"root": resolved, "roots": roots_store.get_roots()}


@router.get("", summary="List registered root folders")
async def list_roots():
    return {"roots": roots_store.get_roots()}


@router.delete("", summary="Clear all registered roots")
async def clear_roots():
    roots_store.clear()
    return {"roots": []}

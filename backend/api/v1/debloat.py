"""
Debloat API routes.

Endpoints for debloating Windows.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncio

from services.debloat.executor import (
    get_available_options,
    execute_debloat,
    ExecutionEnvironment,
)

router = APIRouter()

# In-memory task storage (in production, use a database)
_tasks = {}


class DebloatRequest(BaseModel):
    """Request to start a debloat task."""
    option_ids: list[str]
    environment: str = "auto"  # auto, wsl, powershell, cmd


class DebloatResponse(BaseModel):
    """Response for a debloat task."""
    id: str
    environment: str
    options: list[str]
    status: str
    output: str = ""
    error: str = ""
    progress: int = 0


@router.get("/options", summary="Get available debloat options")
async def get_debloat_options():
    """Return all available debloat options grouped by category."""
    return {"options": get_available_options()}


@router.post("/execute", summary="Start a debloat task")
async def start_debloat(request: DebloatRequest, background_tasks: BackgroundTasks):
    """
    Start a debloat task with selected options.
    
    Returns a task ID that can be used to check status.
    """
    try:
        environment = ExecutionEnvironment(request.environment)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid environment: {request.environment}. Must be: auto, wsl, powershell, cmd",
        )
    
    if not request.option_ids:
        raise HTTPException(status_code=400, detail="Must select at least one option")
    
    # Create a placeholder task ID first
    from uuid import uuid4
    task_id = str(uuid4())
    _tasks[task_id] = {
        'id': task_id,
        'environment': environment.value,
        'options': request.option_ids,
        'status': 'pending',
        'output': '',
        'error': '',
        'progress': 0,
    }

    # Execute in background and update the same task ID the frontend polls
    async def run_debloat(target_task_id: str):
        completed_task = await execute_debloat(request.option_ids, environment)
        _tasks[target_task_id] = {
            'id': target_task_id,
            'environment': completed_task.environment.value,
            'options': completed_task.options,
            'status': completed_task.status,
            'output': completed_task.output,
            'error': completed_task.error,
            'progress': completed_task.progress,
        }

    # Queue the background task
    background_tasks.add_task(run_debloat, task_id)
    
    return DebloatResponse(
        id=task_id,
        environment=environment.value,
        options=request.option_ids,
        status='pending',
    )


@router.get("/status/{task_id}", summary="Get debloat task status")
async def get_debloat_status(task_id: str):
    """Get the status of a debloat task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Handle both dict and object responses
    if isinstance(task, dict):
        return DebloatResponse(**task)
    
    return DebloatResponse(
        id=task.id,
        environment=task.environment.value,
        options=task.options,
        status=task.status,
        output=task.output,
        error=task.error,
        progress=task.progress,
    )


@router.post("/tasks/{task_id}/cancel", summary="Cancel a debloat task")
async def cancel_debloat(task_id: str):
    """Cancel a running debloat task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    if isinstance(task, dict):
        if task['status'] == 'running' or task['status'] == 'pending':
            task['status'] = 'cancelled'
            task['error'] = 'Task cancelled by user'
    else:
        if task.status == "running" or task.status == "pending":
            task.status = "cancelled"
            task.error = "Task cancelled by user"
    
    return {"status": "cancelled"}

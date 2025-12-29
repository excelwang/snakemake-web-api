import logging
import os
import json
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Request
from ...schemas import WorkflowMetaResponse, WorkflowDemo

logger = logging.getLogger(__name__)
router = APIRouter()

def load_workflow_metadata(workflow_id: str) -> dict:
    """
    Load metadata for a specific workflow from the pre-parsed cache.
    """
    cache_dir = Path.home() / ".swa" / "cache" / "workflows"
    cache_file = cache_dir / f"{workflow_id}.json"

    if not cache_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Workflow metadata cache not found for: {workflow_id}. Run 'swa parse' to generate it."
        )
    try:
        with open(cache_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading cached metadata for {workflow_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading cached metadata: {str(e)}")

def get_all_cached_workflows() -> List[dict]:
    """
    Load all cached workflow metadata.
    """
    cache_dir = Path.home() / ".swa" / "cache" / "workflows"
    if not cache_dir.exists():
        logger.warning(f"Workflow cache directory not found at '{cache_dir}'. No workflows will be loaded. Run 'swa parse' to generate the cache.")
        return []

    workflows = []
    for file in cache_dir.glob("*.json"):
        try:
            with open(file, 'r') as f:
                workflows.append(json.load(f))
        except Exception as e:
            logger.error(f"Failed to load cached workflow from {file}: {e}")
    return workflows

@router.get("/workflows", response_model=List[WorkflowMetaResponse], operation_id="list_workflows")
async def list_workflows(request: Request):
    """
    Get a summary of all available workflows from the pre-parsed cache.
    """
    cached_workflows = get_all_cached_workflows()
    return [WorkflowMetaResponse(**wf) for wf in cached_workflows]

@router.get("/workflows/demos/{workflow_id:path}", response_model=List[WorkflowDemo], operation_id="get_workflow_demos")
async def get_workflow_demos(workflow_id: str, request: Request):
    """
    Get demos for a specific workflow from the pre-parsed cache.
    """
    metadata = load_workflow_metadata(workflow_id)
    demos = metadata.get('demos', [])
    return [WorkflowDemo(**demo) for demo in demos]

@router.get("/workflows/{workflow_name:path}", response_model=WorkflowMetaResponse, operation_id="get_workflow_meta")
async def get_workflow_meta(workflow_name: str, request: Request):
    """
    Get full metadata for a specific workflow from the cache.
    """
    return WorkflowMetaResponse(**load_workflow_metadata(workflow_name))

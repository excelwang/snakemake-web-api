import logging
import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from ...schemas import DemoCall
from .tools import load_wrapper_metadata

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/demos/{wrapper_id:path}", response_model=list[DemoCall], operation_id="get_wrapper_demos")
async def get_wrapper_demos(wrapper_id: str, request: Request):
    """
    Get demos for a specific wrapper from the pre-parsed cache.
    """
    logger.info(f"Received request to get demos for wrapper: {wrapper_id}")

    cache_dir = Path.home() / ".swa" / "cache" / "wrappers"
    if not cache_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Parser cache directory not found at '{cache_dir}'. Run 'swa parse' to generate the cache."
        )

    cache_file = cache_dir / f"{wrapper_id}.json"

    if not cache_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Wrapper metadata cache not found for: {wrapper_id}. Run 'swa parse' to generate it."
        )

    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        
        # Extract demos from the loaded wrapper metadata
        demos = data.get('demos', [])
        if demos is None:
            demos = []
        
        # Return the demos as a list of DemoCall objects
        return [DemoCall(**demo) for demo in demos]
    except Exception as e:
        logger.error(f"Error loading cached demos for {wrapper_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading cached demos: {str(e)}")
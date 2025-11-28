import logging
import os
import json
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Request
from ...schemas import ListWrappersResponse, WrapperMetadata, WrapperMetadataResponse, WrapperInfo, UserProvidedParams

router = APIRouter()
logger = logging.getLogger(__name__)

def load_wrapper_metadata(wrappers_dir: str) -> List[WrapperMetadata]:
    """
    Load metadata for all available wrappers from the pre-parsed cache.
    """
    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logger.warning(f"Parser cache directory not found at '{cache_dir}'. No tools will be loaded. Run 'swa parse' to generate the cache.")
        return []

    wrappers = []
    for root, _, files in os.walk(cache_dir):
        for file in files:
            if file.endswith(".json"):
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        data = json.load(f)
                        wrappers.append(WrapperMetadata(**data))
                except Exception as e:
                    logger.error(f"Failed to load cached wrapper from {file}: {e}")
    return wrappers

@router.get("/tools", response_model=ListWrappersResponse, operation_id="list_tools")
async def get_tools(request: Request):
    """
    Get a summary of all available tools from the pre-parsed cache.
    """
    logger.info("Received request to get tools from cache")

    try:
        wrappers = load_wrapper_metadata(request.app.state.wrappers_path)
        logger.info(f"Found {len(wrappers)} tools in cache")

        # Create a lightweight summary and transform to response model
        response_wrappers = []
        for wrapper in wrappers:
            # Create a simplified version for API response
            simplified_wrapper = WrapperMetadataResponse(
                id=wrapper.id,
                info=WrapperInfo(
                    name=wrapper.info.name,
                    description=wrapper.info.description,
                    url=wrapper.info.url,
                    authors=wrapper.info.authors,
                    notes=wrapper.info.notes
                ),
                user_params=UserProvidedParams(
                    inputs=wrapper.user_params.inputs,
                    outputs=wrapper.user_params.outputs,
                    params=wrapper.user_params.params
                )
            )
            response_wrappers.append(simplified_wrapper)

        return ListWrappersResponse(
            wrappers=response_wrappers,
            total_count=len(response_wrappers)
        )
    except Exception as e:
        logger.error(f"Error getting tools from cache: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting tools from cache: {str(e)}")

@router.get("/tools/{tool_name:path}", response_model=WrapperMetadataResponse, operation_id="get_tool_meta")
async def get_tool_meta(tool_name: str, request: Request):
    """
    Get full metadata for a specific tool, including demos, from the cache.
    """
    logger.info(f"Received request to get metadata for tool from cache: {tool_name}")

    cache_dir = Path.home() / ".swa" / "parser"
    cache_file = cache_dir / f"{tool_name}.json"

    if not cache_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Tool metadata cache not found for: {tool_name}. Run 'swa parse' to generate it."
        )

    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        full_wrapper = WrapperMetadata(**data)

        # Create a simplified version for API response
        simplified_wrapper = WrapperMetadataResponse(
            id=full_wrapper.id,
            info=WrapperInfo(
                name=full_wrapper.info.name,
                description=full_wrapper.info.description,
                url=full_wrapper.info.url,
                authors=full_wrapper.info.authors,
                notes=full_wrapper.info.notes
            ),
            user_params=UserProvidedParams(
                inputs=full_wrapper.user_params.inputs,
                outputs=full_wrapper.user_params.outputs,
                params=full_wrapper.user_params.params
            )
        )
        return simplified_wrapper
    except Exception as e:
        logger.error(f"Error loading cached metadata for {tool_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading cached metadata: {str(e)}")

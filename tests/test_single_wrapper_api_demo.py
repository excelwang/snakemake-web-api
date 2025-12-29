"""
A fast, focused integration test for the asynchronous API flow.
"""
import pytest
from fastapi.testclient import TestClient
import logging
import json
import os
from pathlib import Path
from snakemake_mcp_server.api.main import create_native_fastapi_app

@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application."""
    snakebase_dir_env = os.environ.get("SNAKEBASE_DIR")
    if not snakebase_dir_env:
        pytest.fail("SNAKEBASE_DIR environment variable not set.")
    snakebase_dir = Path(snakebase_dir_env).resolve()
    wrappers_path = str(snakebase_dir / "snakemake-wrappers")
    workflows_dir = str(snakebase_dir / "snakemake-workflows")
    
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    return TestClient(app)

@pytest.mark.asyncio
async def test_single_demo_api_flow(rest_client):
    """
    Tests if the API correctly returns demo information for a specific wrapper.
    """
    logging.info("Starting simplified demo API test...")

    # Directly test a wrapper known to have a demo
    wrapper_path = "bio/snpsift/varType"
    
    # Fetch the full metadata for this specific wrapper
    metadata_response = rest_client.get(f"/tools/{wrapper_path}")
    assert metadata_response.status_code == 200, f"Failed to get metadata for {wrapper_path}"
    
    metadata = metadata_response.json()
    logging.info(f"Received metadata for {wrapper_path}: {metadata.get('id')}")
    
    # Fetch demos from the separate endpoint
    demos_response = rest_client.get(f"/demos/{wrapper_path}")
    assert demos_response.status_code == 200, f"Failed to get demos for {wrapper_path}"
    
    demos = demos_response.json()
    
    # Print the received demos for debugging
    logging.info(f"Received demos for {wrapper_path}:\n{json.dumps(demos, indent=2)}")
    
    assert demos is not None, "The demos response is None."
    assert isinstance(demos, list), "The demos response is not a list."
    assert len(demos) > 0, "The demos list is empty, but was expected to have content."

    logging.info(f"Successfully found {len(demos)} demo(s) for wrapper {wrapper_path}.")
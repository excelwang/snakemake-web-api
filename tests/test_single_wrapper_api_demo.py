"""
A fast, focused integration test for the asynchronous API flow.
"""
import pytest
from fastapi.testclient import TestClient
import logging
import json
from snakemake_mcp_server.api.main import create_native_fastapi_app
from snakemake_mcp_server.schemas import DemoCall

@pytest.fixture
def rest_client(wrappers_path, workflows_dir):
    """Create a TestClient for the FastAPI application."""
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    with TestClient(app) as client:
        yield client

@pytest.mark.asyncio
async def test_single_demo_api_flow(rest_client):
    """
    Tests if the API correctly returns demo information for a specific wrapper.
    """
    logging.info("Starting simplified demo API test...")

    # Directly test a wrapper known to have a demo
    wrapper_id = "phys/root/filter" # Use wrapper_id consistently
    
    # Fetch demos for this specific wrapper
    demos_response = rest_client.get(f"/demos/{wrapper_id}")
    assert demos_response.status_code == 200, f"Failed to get demos for {wrapper_id}"
    
    demos_data = demos_response.json()
    
    # Print the received demos for debugging
    logging.info(f"Received demos for {wrapper_id}:\n{json.dumps(demos_data, indent=2)}")
    
    # The endpoint should return a list of DemoCall objects
    assert isinstance(demos_data, list), "The response should be a list of demos."
    assert len(demos_data) > 0, "The 'demos' list is empty, but was expected to have content."

    # Validate the structure of the first demo
    first_demo = DemoCall(**demos_data[0]) # Use the Pydantic model for validation
    assert first_demo.method == "POST"
    assert first_demo.endpoint == "/tool-processes"
    assert first_demo.payload.wrapper_id == wrapper_id

    logging.info(f"Successfully found {len(demos_data)} demo(s) for wrapper {wrapper_id}.")
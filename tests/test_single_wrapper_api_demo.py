"""
A fast, focused integration test for the asynchronous API flow.

This test validates the end-to-end process for a single wrapper demo:
1. Fetches the list of tools.
2. Gets the metadata for the first tool.
3. Submits the first demo for execution.
4. Polls the status endpoint until the job is complete.
5. Verifies the final status and logs.
"""
import pytest
from fastapi.testclient import TestClient
import logging
import time
from snakemake_mcp_server.fastapi_app import create_native_fastapi_app

# Helper functions copied from the original test file
def _value_is_valid(value):
    if value is None: return False
    if isinstance(value, str) and value in ("<callable>",): return False
    if isinstance(value, list) and len(value) == 0: return False
    if isinstance(value, dict) and len(value) == 0: return False
    return True

def _convert_snakemake_io(io_value):
    if isinstance(io_value, dict): return {k: v for k, v in io_value.items() if _value_is_valid(v)}
    elif isinstance(io_value, (list, tuple)): return [v for v in io_value if _value_is_valid(v)]
    elif _value_is_valid(io_value): return [io_value]
    else: return []

def _convert_snakemake_params(params_value):
    if isinstance(params_value, dict): return {k: v for k, v in params_value.items() if _value_is_valid(v)}
    elif isinstance(params_value, (list, tuple)):
        result = {}
        for idx, val in enumerate(params_value):
            if _value_is_valid(val): result[f'param_{idx}'] = val
        return result
    elif _value_is_valid(params_value): return params_value
    else: return {}

@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application."""
    app = create_native_fastapi_app("./snakebase/snakemake-wrappers", "./snakebase/snakemake-workflows")
    return TestClient(app)

@pytest.mark.asyncio
async def test_single_demo_api_flow(rest_client):
    """
    Tests the full asynchronous API flow for the first available wrapper demo.
    """
    logging.info("Starting single demo API flow test...")

    # 1. Get the first available wrapper
    response = rest_client.get("/tools")
    assert response.status_code == 200, "Failed to get wrapper list"
    
    wrappers = response.json().get("wrappers", [])
    if not wrappers:
        pytest.skip("No wrappers found, skipping single demo API test.")
    
    first_wrapper = wrappers[0]
    wrapper_path = first_wrapper.get("path")
    assert wrapper_path, "First wrapper has no path."

    logging.info(f"Found wrapper: {wrapper_path}. Getting its metadata.")

    # 2. Get the first available demo for that wrapper
    metadata_response = rest_client.get(f"/tools/{wrapper_path}")
    assert metadata_response.status_code == 200, f"Failed to get metadata for {wrapper_path}"
    
    demos = metadata_response.json().get("demos", [])
    if not demos:
        pytest.skip(f"No demos found for wrapper {wrapper_path}, skipping.")

    first_demo = demos[0]
    logging.info(f"Found demo for {wrapper_path}. Preparing to execute.")

    # 3. Prepare and submit the job
    endpoint = first_demo.get("endpoint")
    payload = first_demo.get("payload", {})
    assert endpoint == "/tool-processes", "This test is designed for /tool-processes endpoint."

    # Transform payload from Snakefile rule format to API format
    api_payload = { "wrapper_name": payload.get('wrapper', '').replace('file://', '') }
    if 'input' in payload and _value_is_valid(payload['input']): api_payload['inputs'] = _convert_snakemake_io(payload['input'])
    if 'output' in payload and _value_is_valid(payload['output']): api_payload['outputs'] = _convert_snakemake_io(payload['output'])
    if 'params' in payload and _value_is_valid(payload['params']): api_payload['params'] = _convert_snakemake_params(payload['params'])
    if 'log' in payload and _value_is_valid(payload['log']): api_payload['log'] = _convert_snakemake_io(payload['log'])
    if 'threads' in payload: api_payload['threads'] = payload['threads']
    elif 'resources' in payload and '_cores' in payload['resources']: api_payload['threads'] = payload['resources']['_cores']
    if 'workdir' in payload and payload['workdir'] is not None: api_payload['workdir'] = payload['workdir']
    
    # Submit the job
    start_time = time.time()
    timeout = 300  # 5 minutes

    demo_response = rest_client.post(endpoint, json=api_payload)
    assert demo_response.status_code == 202, f"Expected 202 Accepted, got {demo_response.status_code}"
    
    status_url = demo_response.json().get("status_url")
    assert status_url, "Response is missing status_url"
    
    logging.info(f"Job submitted. Polling status at {status_url}")

    # 4. Poll for completion
    final_job_data = None
    while time.time() - start_time < timeout:
        status_response = rest_client.get(status_url)
        assert status_response.status_code == 200, f"Polling failed with status {status_response.status_code}"
        
        job_data = status_response.json()
        current_status = job_data.get("status")
        logging.info(f"Polling... current status is '{current_status}'")

        if current_status in ["completed", "failed"]:
            final_job_data = job_data
            break
        
        time.sleep(5)

    assert final_job_data is not None, f"Job did not complete within {timeout} seconds."

    # 5. Verify the result
    final_status = final_job_data.get("status")
    logging.info(f"Job finished with final status '{final_status}'")

    result_data = final_job_data.get("result", {})
    stdout = result_data.get("stdout", "")
    stderr = result_data.get("stderr", "")
    
    if stdout: logging.info(f"Final stdout:\n---\n{stdout}\n---")
    if stderr: logging.error(f"Final stderr:\n---\n{stderr}\n---")

    assert final_status == "completed", f"Job failed with status '{final_status}'"
    logging.info("Single demo API flow test completed successfully.")
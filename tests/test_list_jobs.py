import pytest
from fastapi.testclient import TestClient
import logging
import json
from pathlib import Path
from snakemake_mcp_server.api.main import create_native_fastapi_app
from snakemake_mcp_server.schemas import UserWrapperRequest

@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application."""
    snakebase_dir = Path("/root/snakemake-mcp-server/snakebase").resolve()
    wrappers_path = str(snakebase_dir / "snakemake-wrappers")
    workflows_dir = str(snakebase_dir / "snakemake-workflows")
    
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    return TestClient(app)

def test_list_jobs_empty(rest_client: TestClient):
    """
    Tests if the API correctly returns an empty list of jobs when no jobs have been submitted.
    """
    logging.info("Starting test for listing empty jobs...")

    response = rest_client.get("/tool-processes/")
    assert response.status_code == 200, "Failed to get empty list of jobs"
    
    data = response.json()
    assert "jobs" in data, "The 'jobs' field is missing from the response."
    assert isinstance(data["jobs"], list), "The 'jobs' field is not a list."
    assert len(data["jobs"]) == 0, "The 'jobs' list is not empty."

    logging.info("Successfully received empty list of jobs.")

@pytest.mark.asyncio
async def test_list_jobs_with_one_job(rest_client: TestClient):
    """
    Tests if the API correctly returns a list of jobs with one job after submitting a job.
    """
    logging.info("Starting test for listing jobs with one job...")

    # 1. Submit a job
    # Using a known wrapper with a demo from previous tests
    request = UserWrapperRequest(
        wrapper_id="bio/samtools/faidx",
        inputs={"ref": "ref.fa"},
        outputs={"fai": "ref.fa.fai"},
        params={}
    )
    
    response = rest_client.post("/tool-processes", json=request.dict())
    assert response.status_code == 202, "Failed to submit job"
    job_submission_response = response.json()
    job_id = job_submission_response["job_id"]

    # 2. Get the list of jobs
    response = rest_client.get("/tool-processes/")
    assert response.status_code == 200, "Failed to get list of jobs"
    
    data = response.json()
    assert "jobs" in data, "The 'jobs' field is missing from the response."
    assert isinstance(data["jobs"], list), "The 'jobs' field is not a list."
    assert len(data["jobs"]) > 0, "The 'jobs' list is empty."

    # 3. Check if the submitted job is in the list
    job_ids = [job["job_id"] for job in data["jobs"]]
    assert job_id in job_ids, "The submitted job is not in the list of jobs."

    logging.info("Successfully listed jobs with one job.")

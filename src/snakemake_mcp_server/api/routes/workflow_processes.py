import logging
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status, Request
from ...workflow_runner import run_workflow
from ...schemas import UserWorkflowRequest, Job, JobList, JobStatus, JobSubmissionResponse
from ...jobs import job_store, run_and_update_job, active_processes

logger = logging.getLogger(__name__)
router = APIRouter()

async def run_workflow_in_background(job_id: str, request: UserWorkflowRequest, workflows_dir: str):
    """
    A wrapper function to run the synchronous 'run_workflow' function in the background
    and update the job store with the result.
    """
    # Now that run_workflow is async, we can call it directly
    await run_and_update_job(job_id, lambda: run_workflow(
        workflow_id=request.workflow_id,
        workflows_dir=workflows_dir,
        config_overrides=request.config,
        target_rule=request.target_rule,
        cores=request.cores,
        use_conda=request.use_conda,
        job_id=job_id
    ))


@router.post(
    "/workflow-processes",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="create_workflow_process"
)
async def create_workflow_process(
    request: UserWorkflowRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    http_request: Request
):
    """
    Submit a Snakemake workflow for asynchronous execution.
    """
    logger.info(f"Received request to run workflow: {request.workflow_id}")

    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, status=JobStatus.ACCEPTED, created_time=datetime.now(timezone.utc))
    job_store[job_id] = job

    background_tasks.add_task(
        run_workflow_in_background,
        job_id,
        request,
        http_request.app.state.workflows_dir
    )
    
    status_url = f"/workflow-processes/{job_id}"
    response.headers["Location"] = status_url
    return JobSubmissionResponse(job_id=job_id, status_url=status_url)


@router.get("/workflow-processes/{job_id}", response_model=Job, operation_id="get_workflow_process_status")
async def get_workflow_process_status(job_id: str):
    """
    Get the status of a submitted Snakemake workflow job.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/workflow-processes/{job_id}", operation_id="cancel_workflow_process")
async def cancel_workflow_process(job_id: str):
    """
    Cancel a running Snakemake workflow process.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.ACCEPTED, JobStatus.RUNNING]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in {job.status} status")
    
    process = active_processes.get(job_id)
    if process:
        logger.info(f"Terminating workflow process for job {job_id}")
        process.terminate()
        return {"message": "Cancellation request submitted"}
    else:
        # If it's in ACCEPTED but no process yet, just mark as failed
        job.status = JobStatus.FAILED
        job.result = {"status": "failed", "error_message": "Cancelled before execution started"}
        return {"message": "Job cancelled before starting"}


@router.get("/workflow-processes", response_model=JobList, operation_id="get_all_workflow_processes")
async def get_all_workflow_processes():
    """
    Get a list of all submitted Snakemake workflow jobs.
    """
    jobs = list(job_store.values())
    total_count = len(jobs)
    return JobList(jobs=jobs, total_count=total_count)

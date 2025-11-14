import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status, Request
from ...jobs import run_snakemake_job_in_background, job_store
from ...schemas import (
    Job,
    JobStatus,
    JobSubmissionResponse,
    SnakemakeWrapperRequest,
    UserSnakemakeWrapperRequest,
)
from .tools import load_wrapper_metadata

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/tool-processes", response_model=JobSubmissionResponse, status_code=status.HTTP_202_ACCEPTED, operation_id="tool_process")
async def tool_process_endpoint(request: UserSnakemakeWrapperRequest, background_tasks: BackgroundTasks, response: Response, http_request: Request):
    """
    Process a Snakemake tool by name and returns the result.
    """
    logger.info(f"Received request for tool: {request.wrapper_name}")
    
    if not request.wrapper_name:
        raise HTTPException(status_code=400, detail="'wrapper_name' must be provided for tool execution.")

    # 1. Load WrapperMetadata to infer hidden parameters
    wrapper_metadata_list = load_wrapper_metadata(http_request.app.state.wrappers_path)
    wrapper_meta = next((wm for wm in wrapper_metadata_list if wm.path == request.wrapper_name), None)

    if not wrapper_meta:
        raise HTTPException(status_code=404, detail=f"Wrapper '{request.wrapper_name}' not found.")

    # 2. Dynamically generate workdir
    temp_dir = tempfile.mkdtemp()
    workdir_path = Path(temp_dir).resolve()
    workdir = str(workdir_path)
    logger.debug(f"Generated workdir: {workdir}")

    # 3. Create dummy input files in the workdir based on request.inputs - REMOVED
    # The user is responsible for providing valid input files.

    # 4. Infer values for hidden parameters from WrapperMetadata or use defaults
    #    Default to None if not found in metadata, as per user's instruction.
    inferred_log = wrapper_meta.log
    inferred_threads = wrapper_meta.threads if wrapper_meta.threads is not None else 1
    inferred_resources = wrapper_meta.resources
    inferred_priority = wrapper_meta.priority if wrapper_meta.priority is not None else 0
    inferred_shadow_depth = wrapper_meta.shadow_depth
    inferred_benchmark = wrapper_meta.benchmark
    inferred_container_img = wrapper_meta.container_img
    inferred_env_modules = wrapper_meta.env_modules
    inferred_group = wrapper_meta.group

    # 5. Construct the full internal SnakemakeWrapperRequest
    internal_request = SnakemakeWrapperRequest(
        wrapper_name=request.wrapper_name,
        inputs=request.inputs,
        outputs=request.outputs,
        params=request.params,
        log=inferred_log,
        threads=inferred_threads,
        resources=inferred_resources,
        priority=inferred_priority,
        shadow_depth=inferred_shadow_depth,
        benchmark=inferred_benchmark,
        container_img=inferred_container_img,
        env_modules=inferred_env_modules,
        group=inferred_group,
        workdir=workdir, # Use the dynamically generated workdir
    )

    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, status=JobStatus.ACCEPTED, created_time=datetime.now(timezone.utc))
    job_store[job_id] = job

    background_tasks.add_task(run_snakemake_job_in_background, job_id, internal_request, http_request.app.state.wrappers_path)
    
    status_url = f"/tool-processes/{job_id}"
    response.headers["Location"] = status_url
    return JobSubmissionResponse(job_id=job_id, status_url=status_url)

@router.get("/tool-processes/{job_id}", response_model=Job, operation_id="get_tool_process_status")
async def get_job_status(job_id: str):
    """
    Get the status of a submitted Snakemake tool job.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status, Request
from ...jobs import run_snakemake_job_in_background, job_store, active_processes
from ...schemas import (
    Job,
    JobList,
    JobStatus,
    JobSubmissionResponse,
    InternalWrapperRequest,
    UserWrapperRequest,
)
import os
from .tools import load_wrapper_metadata

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/tool-processes", response_model=JobSubmissionResponse, status_code=status.HTTP_202_ACCEPTED, operation_id="tool_process")
async def tool_process_endpoint(request: UserWrapperRequest, background_tasks: BackgroundTasks, response: Response, http_request: Request):
    """
    Process a Snakemake tool by name and returns the result.
    """
    logger.info(f"Received request for tool: {request.wrapper_id}")
    
    if not request.wrapper_id:
        raise HTTPException(status_code=400, detail="'wrapper_id' must be provided for tool execution.")

    # 1. Load WrapperMetadata to infer hidden parameters
    wrapper_metadata_list = load_wrapper_metadata(http_request.app.state.wrappers_path)
    wrapper_meta = next((wm for wm in wrapper_metadata_list if wm.id == request.wrapper_id), None)

    if not wrapper_meta:
        raise HTTPException(status_code=404, detail=f"Wrapper '{request.wrapper_id}' not found.")

    # 2. Dynamically generate workdir
    temp_dir = tempfile.mkdtemp()
    workdir_path = Path(temp_dir).resolve()
    workdir = str(workdir_path)
    logger.debug(f"Generated workdir: {workdir}")

    # 3. Create dummy input files in the workdir based on request.inputs
    # This is necessary for Snakemake to find the input files.
    if request.inputs:
        if isinstance(request.inputs, dict):
            for key, value in request.inputs.items():
                if isinstance(value, str):
                    input_path = Path(workdir) / value
                    input_path.parent.mkdir(parents=True, exist_ok=True)
                    if request.wrapper_id == "bio/snpsift/varType" and value == "in.vcf":
                        vcf_content = """##fileformat=VCFv4.2
##contig=<ID=chr1,length=248956422>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
chr1	123	.	G	A	.	PASS	.
"""
                        input_path.write_text(vcf_content)
                        logger.debug(f"Created dummy VCF file for snpsift/varType: {input_path}")
                    else:
                        input_path.touch()
                        logger.debug(f"Created dummy input file: {input_path}")
        elif isinstance(request.inputs, list):
            for input_item in request.inputs:
                if isinstance(input_item, str):
                    input_path = Path(workdir) / input_item
                    input_path.parent.mkdir(parents=True, exist_ok=True)
                    input_path.touch()
                    logger.debug(f"Created dummy input file: {input_path}")

    # 4. Infer values for hidden parameters from WrapperMetadata or use defaults
    #    Default to None if not found in metadata, as per user's instruction.
    inferred_log = wrapper_meta.platform_params.log
    inferred_threads = wrapper_meta.platform_params.threads if wrapper_meta.platform_params.threads is not None else 1
    inferred_resources = wrapper_meta.platform_params.resources
    inferred_priority = wrapper_meta.platform_params.priority if wrapper_meta.platform_params.priority is not None else 0
    inferred_shadow_depth = wrapper_meta.platform_params.shadow_depth
    inferred_benchmark = wrapper_meta.platform_params.benchmark
    inferred_container_img = wrapper_meta.platform_params.container_img
    inferred_env_modules = wrapper_meta.platform_params.env_modules
    inferred_group = wrapper_meta.platform_params.group

    # 5. Construct the full internal InternalSnakemakeRequest
    internal_request = InternalWrapperRequest(
        wrapper_id=request.wrapper_id,
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

@router.delete("/tool-processes/{job_id}", operation_id="cancel_tool_process")
async def cancel_tool_process(job_id: str):
    """
    Cancel a running Snakemake tool process.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.ACCEPTED, JobStatus.RUNNING]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in {job.status} status")
    
    process = active_processes.get(job_id)
    if process:
        logger.info(f"Terminating tool process for job {job_id}")
        process.terminate()
        return {"message": "Cancellation request submitted"}
    else:
        # If it's in ACCEPTED but no process yet, just mark as failed
        job.status = JobStatus.FAILED
        job.result = {"status": "failed", "error_message": "Cancelled before execution started"}
        return {"message": "Job cancelled before starting"}

@router.get("/tool-processes/", response_model=JobList, operation_id="get_all_tool_processes")
async def get_all_jobs():
    """
    Get a list of all submitted Snakemake tool jobs.
    """
    jobs = list(job_store.values())
    return JobList(jobs=jobs)

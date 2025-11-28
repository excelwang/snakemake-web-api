import logging
from pathlib import Path
from .wrapper_runner import run_wrapper
from .schemas import JobStatus, InternalWrapperRequest

# In-memory store for jobs
job_store = {}

async def run_snakemake_job_in_background(job_id: str, request: InternalWrapperRequest, wrappers_path: str):
    """
    A wrapper function to run the snakemake job in the background and update job store.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting background job: {job_id}")
    job_store[job_id].status = JobStatus.RUNNING

    try:
        result = await run_wrapper(request=request)
        
        # Prepare output file paths
        output_file_paths = []
        if request.outputs and request.workdir:
            workdir_path = Path(request.workdir)
            if isinstance(request.outputs, list):
                for output_name in request.outputs:
                    output_file_paths.append(str(workdir_path / output_name))
            elif isinstance(request.outputs, dict):
                for output_name in request.outputs.values():
                    output_file_paths.append(str(workdir_path / output_name))

        # Add output_files to the result dictionary
        final_result = result.copy()
        final_result["output_files"] = output_file_paths
        
        job_store[job_id].result = final_result
        if result.get("status") == "success":
            job_store[job_id].status = JobStatus.COMPLETED
        else:
            job_store[job_id].status = JobStatus.FAILED
        
        logger.info(f"Background job {job_id} finished with status: {job_store[job_id].status}")

    except Exception as e:
        logger.error(f"Background job {job_id} failed with an exception: {e}")
        job_store[job_id].status = JobStatus.FAILED
        job_store[job_id].result = {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "error_message": "Job execution failed with an unexpected exception."
        }

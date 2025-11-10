from fastapi import FastAPI, HTTPException, BackgroundTasks, Response, status
from pydantic import BaseModel
from typing import Union, Dict, List, Optional, Any
import asyncio
import logging
import os
import yaml
from pathlib import Path
from .wrapper_runner import run_wrapper
from .workflow_runner import run_workflow
import uuid
from datetime import datetime
from enum import Enum
import json


# In-memory store for jobs
job_store = {}


# Define new Pydantic models for async job handling
class JobStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    job_id: str
    status: JobStatus
    created_time: datetime
    result: Optional[Dict] = None


class JobSubmissionResponse(BaseModel):
    job_id: str
    status_url: str


# Define Pydantic models for request/response
class SnakemakeWrapperRequest(BaseModel):
    wrapper_name: str
    inputs: Optional[Union[Dict, List]] = None
    outputs: Optional[Union[Dict, List]] = None
    params: Optional[Dict] = None
    log: Optional[Union[Dict, List]] = None
    threads: int = 1
    resources: Optional[Dict] = None
    priority: int = 0
    shadow_depth: Optional[str] = None
    benchmark: Optional[str] = None
    conda_env: Optional[str] = None
    container_img: Optional[str] = None
    env_modules: Optional[List[str]] = None
    group: Optional[str] = None
    workdir: Optional[str] = None


class SnakemakeWorkflowRequest(BaseModel):
    workflow_name: str
    inputs: Optional[Union[Dict, List]] = None
    outputs: Optional[Union[Dict, List]] = None
    params: Optional[Dict] = None
    threads: int = 1
    log: Optional[Union[Dict, List]] = None
    extra_snakemake_args: str = ""
    container: Optional[str] = None
    benchmark: Optional[str] = None
    resources: Optional[Dict] = None
    shadow: Optional[str] = None
    target_rule: Optional[str] = None


class SnakemakeResponse(BaseModel):
    status: str
    stdout: str
    stderr: str
    exit_code: int
    error_message: Optional[str] = None


class DemoCall(BaseModel):
    method: str
    endpoint: str
    payload: Dict[str, Any]


class WrapperMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    authors: Optional[List[str]] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    params: Optional[Any] = None
    notes: Optional[List[str]] = None
    path: str  # Relative path of the wrapper
    demos: Optional[List[DemoCall]] = None  # Include demo calls in the metadata


class ListWrappersResponse(BaseModel):
    wrappers: List[WrapperMetadata]
    total_count: int


async def run_snakemake_job_in_background(job_id: str, request: SnakemakeWrapperRequest, wrappers_path: str):
    """
    A wrapper function to run the snakemake job in the background and update job store.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting background job: {job_id}")
    job_store[job_id].status = JobStatus.RUNNING

    try:
        result = await run_wrapper(
            wrapper_name=request.wrapper_name,
            wrappers_path=wrappers_path,
            inputs=request.inputs,
            outputs=request.outputs,
            params=request.params,
            log=request.log,
            threads=request.threads,
            resources=request.resources,
            priority=request.priority,
            shadow_depth=request.shadow_depth,
            benchmark=request.benchmark,
            conda_env=request.conda_env,
            container_img=request.container_img,
            env_modules=request.env_modules,
            group=request.group,
            workdir=request.workdir,
        )
        
        job_store[job_id].result = result
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


def create_native_fastapi_app(wrappers_path: str, workflows_dir: str) -> FastAPI:
    """
    Create a native FastAPI application with Snakemake functionality.
    
    This creates a pure FastAPI app with proper Pydantic models that can later
    be converted to MCP tools using FastMCP.from_fastapi().
    """
    logger = logging.getLogger(__name__)
    
    app = FastAPI(
        title="Snakemake Native API",
        description="Native FastAPI endpoints for Snakemake functionality",
        version="1.0.0"
    )
    
    def load_wrapper_metadata(wrappers_dir: str) -> List[WrapperMetadata]:
        """
        Load metadata for all available wrappers from the pre-parsed cache.
        """
        cache_dir = Path(wrappers_dir) / ".parser"
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
    
    # Store workflows_dir and wrappers_path in app.state to make them accessible to the endpoints
    app.state.wrappers_path = wrappers_path
    app.state.workflows_dir = workflows_dir
    
    @app.post("/tool-processes", response_model=JobSubmissionResponse, status_code=status.HTTP_202_ACCEPTED, operation_id="tool_process")
    async def tool_process_endpoint(request: SnakemakeWrapperRequest, background_tasks: BackgroundTasks, response: Response):
        """
        Process a Snakemake tool by name and returns the result.
        """
        logger.info(f"Received request for tool: {request.wrapper_name}")
        
        if not request.wrapper_name:
            raise HTTPException(status_code=400, detail="'wrapper_name' must be provided for tool execution.")

        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, status=JobStatus.ACCEPTED, created_time=datetime.utcnow())
        job_store[job_id] = job

        background_tasks.add_task(run_snakemake_job_in_background, job_id, request, app.state.wrappers_path)
        
        status_url = f"/tool-processes/{job_id}"
        response.headers["Location"] = status_url
        return JobSubmissionResponse(job_id=job_id, status_url=status_url)

    @app.get("/tool-processes/{job_id}", response_model=Job, operation_id="get_tool_process_status")
    async def get_job_status(job_id: str):
        """
        Get the status of a submitted Snakemake tool job.
        """
        job = job_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/workflow-processes", response_model=SnakemakeResponse, operation_id="workflow_process")
    async def workflow_process_endpoint(request: SnakemakeWorkflowRequest):
        """
        Process a Snakemake workflow by name and returns the result.
        """
        logger.info(f"Received request for workflow: {request.workflow_name}")

        if not request.workflow_name:
            raise HTTPException(status_code=400, detail="'workflow_name' must be provided for workflow execution.")

        logger.info(f"Processing workflow request: {request.workflow_name}")

        try:
            # Run in thread to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_workflow(
                    workflow_name=request.workflow_name,
                    inputs=request.inputs,
                    outputs=request.outputs,
                    params=request.params,
                    threads=request.threads,
                    log=request.log,
                    extra_snakemake_args=request.extra_snakemake_args,
                    workflows_dir=app.state.workflows_dir,  # Use app.state for consistency
                    container=request.container,
                    benchmark=request.benchmark,
                    resources=request.resources,
                    shadow=request.shadow,
                    target_rule=request.target_rule,
                    timeout=600  # timeout
                )
            )

            logger.info(f"Workflow execution completed with status: {result['status']}")
            return result

        except Exception as e:
            logger.error(f"Error executing workflow '{request.workflow_name}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    # Health check endpoint
    @app.get("/health")
    def health_check():
        return {"status": "healthy", "service": "snakemake-native-api"}

    @app.get("/tools", response_model=ListWrappersResponse, operation_id="list_tools")
    async def get_tools():
        """
        Get all available tools with their metadata from the pre-parsed cache.
        """
        logger.info("Received request to get tools from cache")
        
        try:
            wrappers = load_wrapper_metadata(wrappers_path)
            logger.info(f"Found {len(wrappers)} tools in cache")
            
            return ListWrappersResponse(
                wrappers=wrappers,
                total_count=len(wrappers)
            )
        except Exception as e:
            logger.error(f"Error getting tools from cache: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error getting tools from cache: {str(e)}")

    @app.get("/tools/{tool_path:path}", response_model=WrapperMetadata, operation_id="get_tool_meta")
    async def get_tool_meta(tool_path: str):
        """
        Get metadata for a specific tool by its path from the pre-parsed cache.
        """
        logger.info(f"Received request to get metadata for tool from cache: {tool_path}")
        
        cache_file = Path(wrappers_path) / ".parser" / f"{tool_path}.json"

        if not cache_file.exists():
            raise HTTPException(
                status_code=404, 
                detail=f"Tool metadata cache not found for: {tool_path}. Run 'swa parse' to generate it."
            )
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            return WrapperMetadata(**data)
        except Exception as e:
            logger.error(f"Error loading cached metadata for {tool_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error loading cached metadata: {str(e)}")

    return app


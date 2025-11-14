from fastapi import FastAPI, HTTPException, BackgroundTasks, Response, status, Request
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
from datetime import datetime, timezone
from enum import Enum
import json
import tempfile
import shutil


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
    params: Optional[Union[Dict, List]] = None
    log: Optional[Union[Dict, List]] = None
    threads: int = 1
    resources: Optional[Dict] = None
    priority: int = 0
    shadow_depth: Optional[str] = None
    benchmark: Optional[str] = None
    container_img: Optional[str] = None
    env_modules: Optional[List[str]] = None
    group: Optional[str] = None
    workdir: Optional[str] = None


class UserSnakemakeWrapperRequest(BaseModel):
    wrapper_name: str
    inputs: Optional[Union[Dict, List]] = None
    outputs: Optional[Union[Dict, List]] = None
    params: Optional[Union[Dict, List]] = None


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
    log: Optional[Union[Dict, List]] = None
    threads: Optional[int] = None
    resources: Optional[Dict] = None
    priority: Optional[int] = None
    shadow_depth: Optional[str] = None
    benchmark: Optional[str] = None
    conda_env: Optional[str] = None
    container_img: Optional[str] = None
    env_modules: Optional[List[str]] = None
    group: Optional[str] = None
    notes: Optional[List[str]] = None
    path: str
    demos: Optional[List[DemoCall]] = None
    demo_count: Optional[int] = 0  # For summary view


class DemoCaseResponse(BaseModel):
    method: str
    endpoint: str
    payload: SnakemakeWrapperRequest
    curl_example: str


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
            workdir=request.workdir,
            inputs=request.inputs,
            outputs=request.outputs,
            params=request.params,
            log=request.log,
            threads=request.threads,
            resources=request.resources,
            priority=request.priority,
            shadow_depth=request.shadow_depth,
            benchmark=request.benchmark,
            container_img=request.container_img,
            env_modules=request.env_modules,
            group=request.group,
        )
        
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


def create_native_fastapi_app(wrappers_path: str, workflows_dir: str) -> FastAPI:
    """
    Create a native FastAPI application with Snakemake functionality.
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
    
    app.state.wrappers_path = wrappers_path
    app.state.workflows_dir = workflows_dir
    
    @app.post("/tool-processes", response_model=JobSubmissionResponse, status_code=status.HTTP_202_ACCEPTED, operation_id="tool_process")
    async def tool_process_endpoint(request: UserSnakemakeWrapperRequest, background_tasks: BackgroundTasks, response: Response):
        """
        Process a Snakemake tool by name and returns the result.
        """
        logger.info(f"Received request for tool: {request.wrapper_name}")
        
        if not request.wrapper_name:
            raise HTTPException(status_code=400, detail="'wrapper_name' must be provided for tool execution.")

        # 1. Load WrapperMetadata to infer hidden parameters
        wrapper_metadata_list = load_wrapper_metadata(app.state.wrappers_path)
        wrapper_meta = next((wm for wm in wrapper_metadata_list if wm.path == request.wrapper_name), None)

        if not wrapper_meta:
            raise HTTPException(status_code=404, detail=f"Wrapper '{request.wrapper_name}' not found.")

        # 2. Dynamically generate workdir
        temp_dir = tempfile.mkdtemp()
        workdir_path = Path(temp_dir).resolve()
        workdir = str(workdir_path)
        logger.debug(f"Generated workdir: {workdir}")

        # 3. Create dummy input files in the workdir based on request.inputs
        if request.inputs:
            if isinstance(request.inputs, list):
                for input_file_name in request.inputs:
                    # Assuming simple file names for dummy creation
                    dummy_input_path = workdir_path / input_file_name
                    dummy_input_path.parent.mkdir(parents=True, exist_ok=True)
                    # Provide a simple dummy FASTA content for testing samtools faidx
                    dummy_input_path.write_text(">chr1\nAGCTAGCTAGCTAGCT\n>chr2\nTCGATCGATCGA\n")
                    logger.debug(f"Created dummy input file: {dummy_input_path}")
            # Add handling for dict inputs if necessary, but for now, list is sufficient for demo
            elif isinstance(request.inputs, dict):
                for input_file_name in request.inputs.values():
                    dummy_input_path = workdir_path / input_file_name
                    dummy_input_path.parent.mkdir(parents=True, exist_ok=True)
                    dummy_input_path.write_text(">chr1\nAGCTAGCTAGCTAGCT\n>chr2\nTCGATCGATCGA\n")
                    logger.debug(f"Created dummy input file: {dummy_input_path}")

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

        background_tasks.add_task(run_snakemake_job_in_background, job_id, internal_request, app.state.wrappers_path)
        
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
                    workflows_dir=app.state.workflows_dir,
                    container=request.container,
                    benchmark=request.benchmark,
                    resources=request.resources,
                    shadow=request.shadow,
                    target_rule=request.target_rule,
                    timeout=600
                )
            )

            logger.info(f"Workflow execution completed with status: {result['status']}")
            return result

        except Exception as e:
            logger.error(f"Error executing workflow '{request.workflow_name}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    def health_check():
        return {"status": "healthy", "service": "snakemake-native-api"}

    @app.get("/tools", response_model=ListWrappersResponse, operation_id="list_tools")
    async def get_tools():
        """
        Get a summary of all available tools from the pre-parsed cache.
        """
        logger.info("Received request to get tools from cache")
        
        try:
            wrappers = load_wrapper_metadata(wrappers_path)
            logger.info(f"Found {len(wrappers)} tools in cache")

            # Create a lightweight summary
            for wrapper in wrappers:
                wrapper.demo_count = len(wrapper.demos) if wrapper.demos else 0
                wrapper.demos = None  # Do not include full demo payload in list view

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
        Get full metadata for a specific tool, including demos, from the cache.
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

    @app.get("/demo-case", response_model=DemoCaseResponse, operation_id="get_samtools_faidx_demo_case")
    async def get_samtools_faidx_demo_case(request: Request):
        """
        Provides a demo case for running the 'bio/samtools/faidx' wrapper via the /tool-processes endpoint,
        including the request payload and a curl example.
        
        The /tool-processes endpoint will be responsible for creating any necessary dummy input files.
        """
        # Define input and output file names relative to the workdir
        input_file_name = "genome.fasta"
        output_file_name = "genome.fasta.fai"

        # Construct the UserSnakemakeWrapperRequest payload
        user_payload = UserSnakemakeWrapperRequest(
            wrapper_name="bio/samtools/faidx",
            inputs=[input_file_name], # Relative to workdir
            outputs=[output_file_name], # Relative to workdir
        )

        # Construct the DemoCaseResponse
        demo_case = DemoCaseResponse(
            method="POST",
            endpoint="/tool-processes",
            payload=user_payload.model_dump(mode="json"), # Pass the Pydantic model's dict representation here
            curl_example="" # Will be filled below
        )

        # Generate curl example using the user_payload and dynamic base URL
        payload_json = user_payload.model_dump_json(indent=2)
        base_url_str = str(request.base_url).rstrip('/') # Ensure no trailing slash
        curl_example = f"""curl -X POST "{base_url_str}/tool-processes" \\
     -H "Content-Type: application/json" \\
     -d '{payload_json}'"""
        
        demo_case.curl_example = curl_example
        
        return demo_case

    return app



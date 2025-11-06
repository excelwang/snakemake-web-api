"""
Native FastAPI implementation for Snakemake functionality.

This module provides native FastAPI endpoints that can be converted to MCP tools
using the FastMCP.from_fastapi() method.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Union, Dict, List, Optional
import asyncio
import logging
from .wrapper_runner import run_wrapper
from .workflow_runner import run_workflow


# Define Pydantic models for request/response
class SnakemakeWrapperRequest(BaseModel):
    wrapper_name: str
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
    conda_env: Optional[str] = None


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
    
    # Store workflows_dir in a way that's accessible to the endpoints
    app.state.workflows_dir = workflows_dir
    app.state.wrappers_path = wrappers_path
    
    @app.post("/run_snakemake_wrapper", response_model=SnakemakeResponse, operation_id="run_snakemake_wrapper")
    async def run_snakemake_wrapper_endpoint(request: SnakemakeWrapperRequest):
        """
        Executes a Snakemake wrapper by name and returns the result.
        """
        logger.info(f"Received request for wrapper: {request.wrapper_name}")
        
        if not request.wrapper_name:
            raise HTTPException(status_code=400, detail="'wrapper_name' must be provided for wrapper execution.")

        logger.info(f"Processing wrapper request: {request.wrapper_name}")
        
        try:
            # Run in thread to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_wrapper(
                    wrapper_name=request.wrapper_name,
                    wrappers_path=app.state.wrappers_path,  # Use the wrappers_path from app state
                    inputs=request.inputs,
                    outputs=request.outputs,
                    params=request.params,
                    threads=request.threads,
                    log=request.log,
                    extra_snakemake_args=request.extra_snakemake_args,
                    container=request.container,
                    benchmark=request.benchmark,
                    resources=request.resources,
                    shadow=request.shadow,
                    conda_env=request.conda_env,
                    timeout=600  # timeout
                )
            )
            
            logger.info(f"Wrapper execution completed with status: {result['status']}")
            return result
                
        except Exception as e:
            logger.error(f"Error executing wrapper '{request.wrapper_name}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/run_snakemake_workflow", response_model=SnakemakeResponse, operation_id="run_snakemake_workflow")
    async def run_snakemake_workflow_endpoint(request: SnakemakeWorkflowRequest):
        """
        Executes a full Snakemake workflow by name and returns the result.
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
                    workflows_dir=app.state.workflows_dir,  # Use the workflows_dir from app state
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

    return app


def create_mcp_from_fastapi(wrappers_path: str, workflows_dir: str):
    """
    Create an MCP server from the native FastAPI application.
    This follows the recommended pattern from FastMCP documentation.
    """
    from fastmcp import FastMCP
    
    # First create the native FastAPI app
    fastapi_app = create_native_fastapi_app(wrappers_path, workflows_dir)
    
    # Convert to MCP server
    mcp = FastMCP.from_fastapi(app=fastapi_app)
    
    return mcp
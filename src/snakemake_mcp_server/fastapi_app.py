from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Union, Dict, List, Optional, Any
import asyncio
import logging
import os
import yaml
from pathlib import Path
from .wrapper_runner import run_wrapper
from .workflow_runner import run_workflow


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
        Load metadata for all available wrappers by scanning meta.yaml files.
        
        Args:
            wrappers_dir: Path to the wrappers directory
            
        Returns:
            List of WrapperMetadata objects
        """
        from .snakefile_parser import generate_demo_calls_for_wrapper
        import json
        wrappers = []
        
        # Walk through the wrapper directory structure, excluding .snakemake and other hidden directories
        for root, dirs, files in os.walk(wrappers_dir):
            # Remove hidden directories (including .snakemake) from dirs to prevent walking into them
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file == "meta.yaml":
                    meta_file_path = os.path.join(root, file)
                    try:
                        with open(meta_file_path, 'r', encoding='utf-8') as f:
                            meta_data = yaml.safe_load(f)
                        
                        # Calculate the relative path from wrappers_dir to get wrapper name
                        wrapper_path = os.path.relpath(root, wrappers_dir)
                        
                        # Handle notes field to ensure it is a list
                        notes_data = meta_data.get('notes')
                        if isinstance(notes_data, str):
                            # Split multi-line string into a list of strings, cleaning each line
                            notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]

                        # Generate demo calls
                        basic_demo_calls = generate_demo_calls_for_wrapper(root)
                        enhanced_demos = []
                        if basic_demo_calls:
                            for basic_demo_call in basic_demo_calls:
                                enhanced_demo = DemoCall(
                                    method='POST',
                                    endpoint='/tool-processes',
                                    payload=basic_demo_call
                                )
                                enhanced_demos.append(enhanced_demo)
                        
                        # Create a WrapperMetadata object
                        wrapper_meta = WrapperMetadata(
                            name=meta_data.get('name', os.path.basename(root)),
                            description=meta_data.get('description'),
                            url=meta_data.get('url'),
                            authors=meta_data.get('authors'),
                            input=meta_data.get('input'),
                            output=meta_data.get('output'),
                            params=meta_data.get('params'),
                            notes=notes_data,
                            path=wrapper_path,
                            demos=enhanced_demos or None
                        )
                        wrappers.append(wrapper_meta)
                    except Exception as e:
                        logger.warning(f"Could not load meta.yaml from {meta_file_path}: {e}")
                        continue
        
        return wrappers
    
    # Store workflows_dir and wrappers_path in app.state to make them accessible to the endpoints
    app.state.wrappers_path = wrappers_path
    app.state.workflows_dir = workflows_dir
    
    @app.post("/tool-processes", response_model=SnakemakeResponse, operation_id="tool_process")
    async def tool_process_endpoint(request: SnakemakeWrapperRequest):
        """
        Process a Snakemake tool by name and returns the result.
        """
        logger.info(f"Received request for tool: {request.wrapper_name}")
        
        if not request.wrapper_name:
            raise HTTPException(status_code=400, detail="'wrapper_name' must be provided for tool execution.")

        logger.info(f"Processing tool request: {request.wrapper_name}")
        
        try:
            # Run in thread to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_wrapper(
                    wrapper_name=request.wrapper_name,
                    wrappers_path=app.state.wrappers_path,
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
            )
            
            logger.info(f"Tool execution completed with status: {result['status']}")
            return result
                
        except Exception as e:
            logger.error(f"Error executing tool '{request.wrapper_name}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

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
        Get all available tools with their metadata from meta.yaml files.
        """
        logger.info("Received request to get tools")
        
        try:
            # Load tool metadata - need to pass the path that was used to create the app
            # Since we use closure variables now, we just pass the wrappers_path variable
            wrappers = load_wrapper_metadata(wrappers_path)
            
            logger.info(f"Found {len(wrappers)} tools")
            
            return ListWrappersResponse(
                wrappers=wrappers,
                total_count=len(wrappers)
            )
        except Exception as e:
            logger.error(f"Error getting tools: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error getting tools: {str(e)}")

    # Import the snakefile parser utility for demo generation
    from .snakefile_parser import generate_demo_calls_for_wrapper
    
    @app.get("/tools/{tool_path:path}", response_model=WrapperMetadata, operation_id="get_tool_meta")
    async def get_tool_meta(tool_path: str):
        """
        Get metadata for a specific tool by its path.
        
        Args:
            tool_path: The relative path of the tool (e.g., "bio/samtools/faidx")
        """
        logger.info(f"Received request to get metadata for tool: {tool_path}")
        
        try:
            # Sanitize the path to prevent directory traversal
            if tool_path.startswith('/') or tool_path.startswith('..'):
                raise HTTPException(status_code=400, detail="Invalid tool path")
            
            # Build the full path by joining with the wrappers_path
            full_path = os.path.join(wrappers_path, tool_path)
            
            # Check if the directory exists
            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                raise HTTPException(status_code=404, detail=f"Tool not found: {tool_path}")
            
            # Look for meta.yaml in the tool directory
            meta_file_path = os.path.join(full_path, "meta.yaml")
            if not os.path.exists(meta_file_path):
                raise HTTPException(status_code=404, detail=f"Meta file not found for tool: {tool_path}")
            
            # Load and return the metadata
            with open(meta_file_path, 'r', encoding='utf-8') as f:
                meta_data = yaml.safe_load(f)
            
            # Generate demo calls from the test Snakefile (returns basic API call structures)
            basic_demo_calls = generate_demo_calls_for_wrapper(full_path)
            
            # Enhance each demo call to include API method and endpoint information
            import json
            enhanced_demos = []
            for basic_demo_call in basic_demo_calls:
                # Create DemoCall objects to ensure FastMCP properly recognizes them
                enhanced_demo = DemoCall(
                    method='POST',
                    endpoint='/tool-processes',
                    payload=basic_demo_call,  # This contains just the API parameters for tool-processes
                )
                enhanced_demos.append(enhanced_demo)
            
            # Handle notes field to ensure it is a list
            notes_data = meta_data.get('notes')
            if isinstance(notes_data, str):
                # Split multi-line string into a list of strings, cleaning each line
                notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]
            
            # Create and return the WrapperMetadata object
            wrapper_meta = WrapperMetadata(
                name=meta_data.get('name', os.path.basename(full_path)),
                description=meta_data.get('description'),
                url=meta_data.get('url'),
                authors=meta_data.get('authors'),
                input=meta_data.get('input'),
                output=meta_data.get('output'),
                params=meta_data.get('params'),
                notes=notes_data,
                path=tool_path,
                demos=enhanced_demos
            )
            
            logger.info(f"Successfully retrieved metadata for tool: {tool_path} with {len(enhanced_demos)} demo calls")
            return wrapper_meta
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting tool metadata for {tool_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error getting tool metadata: {str(e)}")



    return app

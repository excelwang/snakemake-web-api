import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request
from ...workflow_runner import run_workflow
from ...schemas import InternalWorkflowRequest, SnakemakeResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/workflow-processes", response_model=SnakemakeResponse, operation_id="workflow_process")
async def workflow_process_endpoint(request: InternalWorkflowRequest, http_request: Request):
    """
    Process a Snakemake workflow by name and returns the result.
    """
    logger.info(f"Received request for workflow: {request.workflow_id}")

    if not request.workflow_id:
        raise HTTPException(status_code=400, detail="'workflow_id' must be provided for workflow execution.")

    logger.info(f"Processing workflow request: {request.workflow_id}")

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_workflow(
                workflow_name=request.workflow_id,
                inputs=request.inputs,
                outputs=request.outputs,
                params=request.params,
                threads=request.threads,
                log=request.log,
                extra_snakemake_args=request.extra_snakemake_args,
                workflows_dir=http_request.app.state.workflows_dir,
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

from fastapi import FastAPI
import logging
from .routes import health, demo, demos, tools, tool_processes, workflow_processes, workflows

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

    app.state.wrappers_path = wrappers_path
    app.state.workflows_dir = workflows_dir

    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(demos.router)
    app.include_router(tools.router)
    app.include_router(tool_processes.router)
    app.include_router(workflow_processes.router)
    app.include_router(workflows.router)

    return app

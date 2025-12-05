import click
import logging
import os
import sys
import uvicorn
from ..api.main import create_native_fastapi_app

logger = logging.getLogger(__name__)

@click.command(
    help="Start the Snakemake server with native FastAPI endpoints. "
         "This provides standard REST API endpoints with full OpenAPI documentation."
)
@click.option("--host", default="127.0.0.1", help="Host to bind to. Default: 127.0.0.1")
@click.option("--port", default=8082, type=int, help="Port to bind to. Default: 8082")
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.pass_context
def run(ctx, host, port, log_level):
    """Start the Snakemake server with native FastAPI REST endpoints."""
    # Reconfigure logging to respect the user's choice
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # This is crucial to override the initial config
    )
    
    # Get paths from context (already strings now)
    wrappers_path = ctx.obj['WRAPPERS_PATH']
    workflows_dir = ctx.obj['WORKFLOWS_DIR']
    
    logger.setLevel(log_level)
    
    logger.info(f"Starting Snakemake Server with native FastAPI REST API...")
    logger.info(f"FastAPI server will be available at http://{host}:{port}")
    logger.info(f"OpenAPI documentation available at http://{host}:{port}/docs")
    logger.info(f"All endpoints will be available as standard REST endpoints")
    logger.info(f"Using snakebase from: {ctx.obj['SNAKEBASE_DIR']}")
    
    if not os.path.isdir(wrappers_path):
        logger.error(f"Wrappers directory not found at: {wrappers_path}")
        sys.exit(1)
    
    if not os.path.isdir(workflows_dir):
        logger.error(f"Workflows directory not found at: {workflows_dir}")
        sys.exit(1)

    # Create the native FastAPI app
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    
    # Run with uvicorn
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower()
    )

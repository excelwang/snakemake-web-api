import sys
import os
import logging
from typing import Union, Dict, List, Optional
from fastmcp import FastMCP
import anyio

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from .wrapper_runner import run_wrapper
    from .workflow_runner import run_workflow
except ImportError as e:
    logger.error(f"Could not import runner module: {e}")
    sys.exit(1)

# The native FastAPI implementation with proper Pydantic models
# is now in the fastapi_app.py file to maintain consistency
# and follow proper module separation.

def create_mcp_from_fastapi(wrappers_path: str, workflows_dir: str):
    """
    Create an MCP server from the native FastAPI application.
    This follows the recommended pattern from FastMCP documentation.
    """
    from .fastapi_app import create_native_fastapi_app
    from fastmcp import FastMCP
    
    # First create the native FastAPI app
    fastapi_app = create_native_fastapi_app(wrappers_path, workflows_dir)
    
    # Convert to MCP server
    mcp = FastMCP.from_fastapi(app=fastapi_app)
    
    return mcp

import click

@click.group()
def cli():
    pass


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8082, help="Port to bind to")
@click.option("--snakebase-dir", default=os.environ.get("SNAKEBASE_DIR", "./snakebase"), help="Base directory for snakebase.")
def run_fastapi_rest(host, port, snakebase_dir):
    """Starts the Snakemake Wrapper Server as a native FastAPI REST API."""
    import uvicorn
    from .fastapi_app import create_native_fastapi_app
    
    logger.info(f"Starting Snakemake Wrapper Server as native FastAPI REST API...")
    logger.info(f"FastAPI server will be available at http://{host}:{port}")
    logger.info(f"All endpoints will be available as standard REST endpoints")
    
    wrappers_path = os.path.abspath(os.path.join(snakebase_dir, "snakemake-wrappers"))
    workflows_dir = os.path.abspath(os.path.join(snakebase_dir, "snakemake-workflows"))
    
    logger.info(f"Using snakebase from: {os.path.abspath(snakebase_dir)}")
    
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
        log_level="info"
    )


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8083, help="Port to bind to")
@click.option("--log-level", default="INFO", help="Log level")
@click.option("--snakebase-dir", default=os.environ.get("SNAKEBASE_DIR", "./snakebase"), help="Base directory for snakebase.")
def run_mcp_from_fastapi(host, port, log_level, snakebase_dir):
    """Starts the Snakemake Wrapper MCP Server converted from FastAPI endpoints."""
    from .fastapi_app import create_mcp_from_fastapi
    
    logger.info(f"Starting Snakemake Wrapper MCP Server (converted from FastAPI)...")
    logger.info(f"Server will be available at http://{host}:{port}")
    
    wrappers_path = os.path.abspath(os.path.join(snakebase_dir, "snakemake-wrappers"))
    workflows_dir = os.path.abspath(os.path.join(snakebase_dir, "snakemake-workflows"))
    
    logger.info(f"Using snakebase from: {os.path.abspath(snakebase_dir)}")
    
    if not os.path.isdir(wrappers_path):
        logger.error(f"Wrappers directory not found at: {wrappers_path}")
        sys.exit(1)
    
    if not os.path.isdir(workflows_dir):
        logger.error(f"Workflows directory not found at: {workflows_dir}")
        sys.exit(1)

    mcp = create_mcp_from_fastapi(wrappers_path, workflows_dir)

    try:
        mcp.run(
            transport="http",
            host=host,
            port=port,
            log_level=log_level
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)


def main():
    cli()

if __name__ == "__main__":
    main()
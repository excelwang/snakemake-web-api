import sys
import os
import logging
import dotenv
from pathlib import Path
from typing import Union, Dict, List, Optional
from fastmcp import FastMCP
import anyio

# Load environment variables from ~/.swa/.env if file exists
config_dir = Path.home() / ".swa"
env_file = config_dir / ".env"

if env_file.exists():
    dotenv.load_dotenv(env_file)

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
import sys
import os
from pathlib import Path

def validate_paths(snakebase_dir):
    """Validate the snakebase directory structure."""
    snakebase_path = Path(snakebase_dir).resolve()
    if not snakebase_path.exists():
        click.echo(f"Error: snakebase directory does not exist: {snakebase_path}", err=True)
        sys.exit(1)
    
    wrappers_path = snakebase_path / "snakemake-wrappers"
    workflows_dir = snakebase_path / "snakemake-workflows"
    
    return str(wrappers_path), str(workflows_dir)

@click.group(
    help="Snakemake MCP Server - A server for running Snakemake wrappers and workflows via MCP protocol."
)
@click.option(
    '--snakebase-dir', 
    default=lambda: os.environ.get("SNAKEBASE_DIR", "./snakebase"),
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Base directory for snakebase containing snakemake-wrappers and snakemake-workflows subdirectories. "
         "Defaults to SNAKEBASE_DIR environment variable or './snakebase'."
)
@click.pass_context
def cli(ctx, snakebase_dir):
    """Main CLI group for Snakemake MCP Server."""
    ctx.ensure_object(dict)
    wrappers_path, workflows_dir = validate_paths(snakebase_dir)
    
    # Add paths to context
    ctx.obj['SNAKEBASE_DIR'] = Path(snakebase_dir).resolve()
    ctx.obj['WRAPPERS_PATH'] = wrappers_path
    ctx.obj['WORKFLOWS_DIR'] = workflows_dir


# Note: The original direct MCP server is no longer supported as we're using the FastAPI-first approach
# Only the two new command variants are available: rest and mcp


@cli.command(
    help="Start the Snakemake server with native FastAPI REST endpoints. "
         "This provides standard REST API endpoints with full OpenAPI documentation."
)
@click.option("--host", default="127.0.0.1", help="Host to bind to. Default: 127.0.0.1")
@click.option("--port", default=8082, type=int, help="Port to bind to. Default: 8082")
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.pass_context
def rest(ctx, host, port, log_level):
    """Start the Snakemake server with native FastAPI REST endpoints."""
    import uvicorn
    from .fastapi_app import create_native_fastapi_app

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


@cli.command(
    help="Start the Snakemake server with MCP protocol support. "
         "This provides MCP protocol endpoints derived from FastAPI definitions."
)
@click.option("--host", default="127.0.0.1", help="Host to bind to. Default: 127.0.0.1")
@click.option("--port", default=8083, type=int, help="Port to bind to. Default: 8083")
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.pass_context
def mcp(ctx, host, port, log_level):
    """Start the Snakemake server with MCP protocol support."""
    from .fastapi_app import create_mcp_from_fastapi

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
    
    logger.info(f"Starting Snakemake Server with MCP protocol support...")
    logger.info(f"Server will be available at http://{host}:{port}")
    logger.info(f"MCP endpoints will be available at http://{host}:{port}/mcp")
    logger.info(f"Using snakebase from: {ctx.obj['SNAKEBASE_DIR']}")
    
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
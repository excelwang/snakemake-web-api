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


@cli.command(
    help="Parse all wrappers and cache the metadata to JSON files for faster server startup."
)
@click.pass_context
def parse(ctx):
    """Parses all wrapper metadata and caches it."""
    import json
    import yaml
    from .snakefile_parser import generate_demo_calls_for_wrapper
    from .fastapi_app import WrapperMetadata, DemoCall

    wrappers_path_str = ctx.obj['WRAPPERS_PATH']
    wrappers_path = Path(wrappers_path_str)
    cache_dir = wrappers_path / ".parser"
    
    click.echo(f"Starting parser cache generation for wrappers in: {wrappers_path}")
    
    # Create or clear the cache directory
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        click.echo(f"Cleared existing cache directory: {cache_dir}")
    cache_dir.mkdir()

    wrapper_count = 0
    for root, dirs, files in os.walk(wrappers_path):
        # Skip hidden directories, including the cache dir itself
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if "meta.yaml" in files:
            wrapper_count += 1
            meta_file_path = os.path.join(root, "meta.yaml")
            click.echo(f"Parsing wrapper {wrapper_count}: {os.path.relpath(root, wrappers_path)}")
            
            try:
                with open(meta_file_path, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
                
                wrapper_rel_path = os.path.relpath(root, wrappers_path)
                
                notes_data = meta_data.get('notes')
                if isinstance(notes_data, str):
                    notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]

                basic_demo_calls = generate_demo_calls_for_wrapper(root)
                enhanced_demos = [
                    DemoCall(method='POST', endpoint='/tool-processes', payload=call)
                    for call in basic_demo_calls
                ] if basic_demo_calls else None
                
                wrapper_meta = WrapperMetadata(
                    name=meta_data.get('name', os.path.basename(root)),
                    description=meta_data.get('description'),
                    url=meta_data.get('url'),
                    authors=meta_data.get('authors'),
                    input=meta_data.get('input'),
                    output=meta_data.get('output'),
                    params=meta_data.get('params'),
                    notes=notes_data,
                    path=wrapper_rel_path,
                    demos=enhanced_demos
                )
                
                # Save to cache
                cache_file_path = cache_dir / f"{wrapper_rel_path}.json"
                cache_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file_path, 'w') as f:
                    # Use .model_dump(mode="json") for Pydantic v2
                    json.dump(wrapper_meta.model_dump(mode="json"), f, indent=2)

            except Exception as e:
                click.echo(f"  [ERROR] Failed to parse or cache {os.path.relpath(root, wrappers_path)}: {e}", err=True)

    click.echo(f"\nSuccessfully parsed and cached {wrapper_count} wrappers in {cache_dir}")


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
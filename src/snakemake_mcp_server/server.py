import anyio
import click
import sys
import os
import logging
import dotenv
from pathlib import Path
from typing import Union, Dict, List, Optional
import requests
import time
from fastmcp import FastMCP

# Load environment variables from ~/.swa/.env if file exists
config_dir = Path.home() / ".swa"
env_file = config_dir / ".env"

if env_file.exists():
    dotenv.load_dotenv(env_file)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
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
    default=lambda: os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase")),
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Base directory for snakebase containing snakemake-wrappers and snakemake-workflows subdirectories. "
         "Defaults to SNAKEBASE_DIR environment variable or '~/snakebase'."
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
    """Parses all wrapper metadata and demos, then caches them."""
    import json
    import yaml
    from .snakefile_parser import generate_demo_calls_for_wrapper
    from .fastapi_app import WrapperMetadata, DemoCall

    wrappers_path_str = ctx.obj['WRAPPERS_PATH']
    wrappers_path = Path(wrappers_path_str)
    cache_dir = Path.home() / ".swa" / "parser"
    
    click.echo(f"Starting parser cache generation for wrappers in: {wrappers_path}")
    
    # Create or clear the cache directory
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        click.echo(f"Cleared existing cache directory: {cache_dir}")
    cache_dir.mkdir()

    wrapper_count = 0
    total_demo_count = 0
    for root, dirs, files in os.walk(wrappers_path):
        # Skip hidden directories, including the cache dir itself
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if "meta.yaml" in files:
            wrapper_count += 1
            meta_file_path = os.path.join(root, "meta.yaml")
            wrapper_rel_path = os.path.relpath(root, wrappers_path)
            click.echo(f"Parsing wrapper {wrapper_count}: {wrapper_rel_path}")
            
            try:
                with open(meta_file_path, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
                
                notes_data = meta_data.get('notes')
                if isinstance(notes_data, str):
                    notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]

                # Pre-parse demos using the robust DAG-based parser
                basic_demo_calls = generate_demo_calls_for_wrapper(root, wrappers_path_str)
                num_demos = len(basic_demo_calls) if basic_demo_calls else 0
                if num_demos > 0:
                    total_demo_count += num_demos
                    enhanced_demos = [
                        DemoCall(method='POST', endpoint='/tool-processes', payload=call).model_dump(mode="json")
                        for call in basic_demo_calls
                    ]
                else:
                    enhanced_demos = None
                
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
                    demos=enhanced_demos,
                    demo_count=num_demos
                )
                
                # Save to cache
                cache_file_path = cache_dir / f"{wrapper_rel_path}.json"
                cache_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file_path, 'w') as f:
                    f.write(wrapper_meta.model_dump_json(indent=2))

            except Exception as e:
                click.echo(f"  [ERROR] Failed to parse or cache {wrapper_rel_path}: {e}", err=True)
                import traceback
                traceback.print_exc() # Print full traceback for debugging

    click.echo(f"\nSuccessfully parsed and cached {wrapper_count} wrappers and {total_demo_count} demos in {cache_dir}")


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


@cli.command(
    help="Verify all cached wrapper demos by executing them with appropriate test data."
)
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.option("--dry-run", is_flag=True, help="Show what would be executed without running it.")
@click.option("--by-api", default=None, help="Verify using the /tool-processes API endpoint with the specified server URL (e.g., http://127.0.0.1:8082). If not provided, will use direct demo runner.")
@click.pass_context
def verify(ctx, log_level, dry_run, by_api):
    """Verify all cached wrapper demos by executing them with appropriate test data."""
    import asyncio
    import json
    import tempfile
    import shutil
    from pathlib import Path
    from .fastapi_app import WrapperMetadata
    from .demo_runner import run_demo

    # Reconfigure logging to respect the user's choice
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # This is crucial to override the initial config
    )

    wrappers_path = ctx.obj['WRAPPERS_PATH']
    logger.setLevel(log_level)

    logger.info(f"Starting verification of cached wrapper demos...")
    logger.info(f"Using wrappers from: {wrappers_path}")
    
    if by_api:
        logger.info(f"API mode enabled: using {by_api}/tool-processes endpoint for verification")

    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logger.error(f"Parser cache directory not found at: {cache_dir}. Run 'swa parse' first.")
        sys.exit(1)

    # Load all cached wrapper metadata
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
                    continue

    logger.info(f"Found {len(wrappers)} cached wrappers with metadata.")

    # Count total demos
    total_demos = 0
    for wrapper in wrappers:
        if wrapper.demos:
            total_demos += len(wrapper.demos)

    if total_demos == 0:
        logger.warning("No demos found in cached wrapper metadata.")
        return

    logger.info(f"Found {total_demos} demos to verify.")

    if dry_run:
        logger.info("DRY RUN MODE: Would execute all demos but not actually run them.")
        for wrapper in wrappers:
            if wrapper.demos:
                for demo in wrapper.demos:
                    payload = demo.payload
                    wrapper_name = payload.get('wrapper', '').replace('file://', '')
                    if wrapper_name.startswith("master/"):
                        wrapper_name = wrapper_name[len("master/"):]
                    logger.info(f"  Would execute demo for wrapper: {wrapper_name}")
        return

    # Execute all demos
    successful_demos = 0
    failed_demos = 0

    for wrapper in wrappers:
        if not wrapper.demos:
            continue

        logger.info(f"Verifying demos for wrapper: {wrapper.path}")
        for i, demo in enumerate(wrapper.demos):
            payload = demo.payload
            logger.info(f"  - Processing Demo {i+1}...")

            if by_api:
                # Use the API endpoint to execute the demo
                logger.info(f"    Demo {i+1}: Executing via API...")
                
                try:
                    # Prepare the API payload by using only the fields that are compatible with the API
                    # The API expects: wrapper_name, inputs, outputs, params
                    api_payload = {
                        "wrapper_name": payload.get('wrapper', '').replace('file://', '').replace('master/', ''),
                        "inputs": payload.get('input', {}),
                        "outputs": payload.get('output', {}),
                        "params": payload.get('params', {})
                    }
                    
                    # Make request to the API endpoint
                    api_url = f"{by_api.rstrip('/')}/tool-processes"
                    
                    response = requests.post(api_url, json=api_payload)
                    
                    if response.status_code == 202:  # Accepted
                        # Get job ID from response
                        job_response = response.json()
                        job_id = job_response.get('job_id')
                        
                        # Poll for job status
                        status_url = f"{by_api.rstrip('/')}{job_response.get('status_url')}"
                        
                        # Wait for job completion (with timeout)
                        max_attempts = 30  # 5 min timeout if each poll waits 10 seconds
                        attempts = 0
                        
                        while attempts < max_attempts:
                            status_response = requests.get(status_url)
                            
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                status = status_data.get('status')
                                
                                if status == 'COMPLETED':
                                    logger.info(f"    Demo {i+1}: SUCCESS (API)")
                                    successful_demos += 1
                                    break
                                elif status == 'FAILED':
                                    logger.error(f"    Demo {i+1}: FAILED (API)")
                                    logger.error(f"      Status: {status}")
                                    failed_demos += 1
                                    break
                                else:
                                    # Still running, wait before polling again
                                    logger.debug(f"      Job status: {status}, waiting...")
                                    time.sleep(10)  # Wait 10 seconds before polling again
                                    attempts += 1
                            else:
                                logger.error(f"    Demo {i+1}: FAILED to get job status (HTTP {status_response.status_code})")
                                failed_demos += 1
                                break
                        else:
                            # Timeout reached
                            logger.error(f"    Demo {i+1}: TIMEOUT waiting for job completion")
                            failed_demos += 1
                    else:
                        logger.error(f"    Demo {i+1}: FAILED to submit job to API (HTTP {response.status_code})")
                        logger.error(f"      Response: {response.text}")
                        failed_demos += 1
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"    Demo {i+1}: FAILED due to connection error: {e}")
                    failed_demos += 1
                except Exception as e:
                    logger.error(f"    Demo {i+1}: FAILED with exception: {e}")
                    failed_demos += 1
            else:
                # Use the original logic (direct demo runner)
                wrapper_name = payload.get('wrapper', '').replace('file://', '')
                if wrapper_name.startswith("master/"):
                    wrapper_name = wrapper_name[len("master/"):]

                inputs = payload.get('input', {})
                outputs = payload.get('output', {})
                params = payload.get('params', {})

                # Skip if wrapper name is empty
                if not wrapper_name:
                    logger.warning(f"    Demo {i+1}: SKIPPED because wrapper name is empty.")
                    continue

                # Execute the wrapper using run_demo which handles input file copying
                logger.info(f"    Demo {i+1}: Executing demo...")
                demo_workdir = payload.get('workdir')
                result = asyncio.run(run_demo(
                    wrapper_name=wrapper_name,
                    inputs=inputs,
                    outputs=outputs,
                    params=params,
                    demo_workdir=demo_workdir  # Pass the demo workdir for input file copying
                ))

                if result.get("status") == "success":
                    logger.info(f"    Demo {i+1}: SUCCESS")
                    successful_demos += 1
                else:
                    logger.error(f"    Demo {i+1}: FAILED")
                    logger.error(f"      Exit Code: {result.get('exit_code')}")
                    logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                    failed_demos += 1

    logger.info("="*60)
    logger.info("Verification Summary")
    logger.info(f"Successful demos: {successful_demos}")
    logger.info(f"Failed demos: {failed_demos}")
    logger.info(f"Total demos: {successful_demos + failed_demos}")
    logger.info("="*60)

    logger.info(f"Verification completed with {failed_demos} failed demos out of {successful_demos + failed_demos} total demos.")
    if failed_demos > 0:
        logger.error(f"Verification failed with {failed_demos} demo(s) not executing successfully.")
        sys.exit(1)
    else:
        logger.info("All demos executed successfully!")


def main():
    cli()

if __name__ == "__main__":
    main()
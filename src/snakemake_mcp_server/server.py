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

def create_app(wrappers_path: str, workflow_base_dir: str) -> FastMCP:
    """Create the FastMCP application."""
    mcp = FastMCP("Snakemake Wrapper Server")

    @mcp.tool
    async def run_snakemake_wrapper(
        wrapper_name: str,
        inputs: Optional[Union[Dict, List]] = None,
        outputs: Optional[Union[Dict, List]] = None,
        params: Optional[Dict] = None,
        threads: int = 1,
        log: Optional[Union[Dict, List]] = None,
        extra_snakemake_args: str = "",
        container: Optional[str] = None,
        benchmark: Optional[str] = None,
        resources: Optional[Dict] = None,
        shadow: Optional[str] = None,
        conda_env: Optional[str] = None,
    ) -> Dict:
        """
        Executes a Snakemake wrapper by name and returns the result.
        """
        logger.info(f"Received request for wrapper: {wrapper_name}")
        
        if not wrapper_name:
            raise ValueError("'wrapper_name' must be provided for wrapper execution.")

        logger.info(f"Processing wrapper request: {wrapper_name}")
        
        try:
            result = await anyio.to_thread.run_sync(
                lambda: run_wrapper(
                    wrapper_name=wrapper_name,
                    inputs=inputs,
                    outputs=outputs,
                    params=params,
                    threads=threads,
                    log=log,
                    extra_snakemake_args=extra_snakemake_args,
                    wrappers_path=wrappers_path,
                    container=container,
                    benchmark=benchmark,
                    resources=resources,
                    shadow=shadow,
                    conda_env=conda_env,
                )
            )
            
            logger.info(f"Wrapper execution completed with status: {result['status']}")
            
            if result['status'] == 'success':
                return result
            else:
                error_msg = f"Wrapper '{wrapper_name}' failed: {result.get('error_message', 'Unknown error')}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Error executing wrapper '{wrapper_name}': {str(e)}")
            raise

    @mcp.tool
    async def run_snakemake_workflow(
        workflow_name: str,
        inputs: Optional[Union[Dict, List]] = None,
        outputs: Optional[Union[Dict, List]] = None,
        params: Optional[Dict] = None,
        threads: int = 1,
        log: Optional[Union[Dict, List]] = None,
        extra_snakemake_args: str = "",
        container: Optional[str] = None,
        benchmark: Optional[str] = None,
        resources: Optional[Dict] = None,
        shadow: Optional[str] = None,
        conda_env: Optional[str] = None,
        target_rule: Optional[str] = None,
    ) -> Dict:
        """
        Executes a full Snakemake workflow by name and returns the result.
        """
        logger.info(f"Received request for workflow: {workflow_name}")

        if not workflow_name:
            raise ValueError("'workflow_name' must be provided for workflow execution.")

        logger.info(f"Processing workflow request: {workflow_name}")

        try:
            result = await anyio.to_thread.run_sync(
                lambda: run_workflow(
                    workflow_name=workflow_name,
                    inputs=inputs,
                    outputs=outputs,
                    params=params,
                    threads=threads,
                    log=log,
                    extra_snakemake_args=extra_snakemake_args,
                    workflow_base_dir=workflow_base_dir, # Pass workflow_base_dir
                    container=container,
                    benchmark=benchmark,
                    resources=resources,
                    shadow=shadow,
                    conda_env=conda_env,
                    target_rule=target_rule,
                )
            )

            logger.info(f"Workflow execution completed with status: {result['status']}")

            if result['status'] == 'success':
                return result
            else:
                error_msg = f"Workflow '{workflow_name}' failed: {result.get('error_message', 'Unknown error')}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error executing workflow '{workflow_name}': {str(e)}")
            raise

    return mcp

import click

@click.group()
def cli():
    pass

@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8081, help="Port to bind to")
@click.option("--log-level", default="INFO", help="Log level")
@click.option("--wrappers-path", default=".", help="Path to the snakemake-wrappers repository.")
@click.option("--workflow-base-dir", default=".", help="Base directory for Snakemake workflows.")
def run(host, port, log_level, wrappers_path, workflow_base_dir):
    """Starts the Snakemake Wrapper MCP Server."""
    logger.info(f"Starting Snakemake Wrapper MCP Server...")
    logger.info(f"Server will be available at http://{host}:{port}")
    logger.info(f"Using snakemake-wrappers from: {os.path.abspath(wrappers_path)}")
    logger.info(f"Using snakemake workflows from: {os.path.abspath(workflow_base_dir)}")

    mcp = create_app(wrappers_path, workflow_base_dir)

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
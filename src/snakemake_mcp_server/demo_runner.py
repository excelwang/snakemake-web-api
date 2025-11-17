"""
Module for running Snakemake wrapper demos by copying necessary input files
and executing the wrapper with proper work directory setup.
"""
import asyncio
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import Union, Dict, List, Optional
from .wrapper_runner import run_wrapper
# from .utils import setup_demo_workdir # No longer needed

logger = logging.getLogger(__name__)


async def run_demo(
    # Same parameters as run_wrapper
    wrapper_name: str,
    inputs: Optional[Union[Dict, List]] = None,
    outputs: Optional[Union[Dict, List]] = None,
    params: Optional[List] = None,
    log: Optional[Union[Dict, List]] = None,
    threads: Optional[int] = None,
    resources: Optional[Dict] = None,
    priority: Optional[int] = None,
    shadow_depth: Optional[str] = None,
    benchmark: Optional[str] = None,
    container_img: Optional[str] = None,
    env_modules: Optional[List[str]] = None,
    group: Optional[str] = None,
    # Additional parameters for demo execution
    demo_workdir: Optional[str] = None,
    custom_workdir: Optional[str] = None,
    timeout: int = 600,
) -> Dict:
    """
    Runs a Snakemake wrapper demo by preparing the necessary input files
    and executing the wrapper with appropriate work directory setup.
    
    Args:
        Same as run_wrapper plus:
        demo_workdir: Directory containing the demo input files (copied to workdir)
        custom_workdir: Custom workdir to use (instead of creating a temporary one)
        timeout: Execution timeout in seconds
        
    Returns:
        Dictionary with execution result
    """
    
    temp_symlink_dir = None
    workdir_to_use = custom_workdir
    
    try:
        if not demo_workdir:
            return {"status": "failed", "stdout": "", "stderr": "demo_workdir must be provided.", "exit_code": -1, "error_message": "demo_workdir not provided."}

        # If no custom workdir, create a temporary directory and symlink demo_workdir into it
        if not workdir_to_use:
            temp_symlink_dir = tempfile.mkdtemp()
            # Create a symlink inside the temporary directory pointing to the actual demo_workdir
            # This allows Snakemake to operate as if it's in the demo_workdir,
            # but within a temporary, cleanable context.
            symlink_target_name = Path(demo_workdir).name
            os.symlink(demo_workdir, Path(temp_symlink_dir) / symlink_target_name, target_is_directory=True)
            workdir_to_use = Path(temp_symlink_dir) / symlink_target_name
        else:
            workdir_to_use = Path(workdir_to_use).resolve()
            os.makedirs(workdir_to_use, exist_ok=True)
            # If custom_workdir is provided, we assume it's already set up or will be set up externally.
            # For now, we'll just ensure it exists.
        
        # Execute the wrapper in the prepared workdir
        result = await run_wrapper(
            wrapper_name=wrapper_name,
            workdir=workdir_to_use,
            inputs=inputs,
            outputs=outputs,
            params=params,
            log=log,
            threads=threads,
            resources=resources,
            priority=priority,
            shadow_depth=shadow_depth,
            benchmark=benchmark,
            container_img=container_img,
            env_modules=env_modules,
            group=group,
            timeout=timeout
        )
        
        return result
    finally:
        # Clean up temporary directory if we created one
        if temp_symlink_dir and os.path.exists(temp_symlink_dir):
            try:
                shutil.rmtree(temp_symlink_dir)
            except Exception as e:
                logger.warning(f"Could not remove temporary symlink directory {temp_symlink_dir}: {e}")
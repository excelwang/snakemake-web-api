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
from .schemas import UserWrapperRequest, InternalWrapperRequest, PlatformRunParams

logger = logging.getLogger(__name__)


async def run_demo(
    user_request: UserWrapperRequest,
    platform_params: PlatformRunParams,
    demo_workdir: Optional[str] = None,
    custom_workdir: Optional[str] = None,
    timeout: int = 600,
) -> Dict:
    """
    Runs a Snakemake wrapper demo by preparing the necessary input files
    and executing the wrapper with appropriate work directory setup.
    
    Args:
        user_request: The user's request containing wrapper_id, inputs, outputs, and params.
        platform_params: Platform-specific run parameters.
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

        if not workdir_to_use:
            temp_symlink_dir = tempfile.mkdtemp()
            symlink_target_name = Path(demo_workdir).name
            os.symlink(demo_workdir, Path(temp_symlink_dir) / symlink_target_name, target_is_directory=True)
            workdir_to_use = Path(temp_symlink_dir) / symlink_target_name
        else:
            workdir_to_use = Path(workdir_to_use).resolve()
            os.makedirs(workdir_to_use, exist_ok=True)
        
        # Combine user request and platform params into an internal request
        internal_request = InternalWrapperRequest(
            **user_request.model_dump(),
            **platform_params.model_dump(),
            workdir=str(workdir_to_use)
        )
        
        # Execute the wrapper in the prepared workdir
        result = await run_wrapper(
            request=internal_request,
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
import asyncio
import tempfile
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Union
import yaml
import collections.abc

logger = logging.getLogger(__name__)

def deep_merge(source, destination):
    """
    Recursively merges source dict into destination dict.
    """
    for key, value in source.items():
        if isinstance(value, collections.abc.Mapping):
            destination[key] = deep_merge(value, destination.get(key, {}))
        else:
            destination[key] = value
    return destination

async def run_workflow(
    workflow_id: str,
    workflows_dir: str,
    config_overrides: dict,
    target_rule: Optional[str] = None,
    cores: Union[int, str] = "all",
    use_conda: bool = True,
    timeout: int = 3600,
    job_id: Optional[str] = None,
) -> Dict:
    """
    Executes a Snakemake workflow by merging a config object with the base
    config.yaml and running Snakemake via asyncio.create_subprocess_exec.
    """
    temp_config_path = None
    try:
        if not workflow_id or not isinstance(workflow_id, str):
            raise ValueError("workflow_id must be a non-empty string")

        workflow_base_path = Path(workflows_dir)
        workflow_path = workflow_base_path / workflow_id
        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow not found at: {workflow_path}")
        
        workflow_path = workflow_path.resolve()
        
        main_snakefile = workflow_path / "workflow" / "Snakefile"
        if not main_snakefile.exists():
            # Fallback for workflows that might have Snakefile at the root
            main_snakefile_root = workflow_path / "Snakefile"
            if not main_snakefile_root.exists():
                raise FileNotFoundError(f"Main Snakefile not found for workflow at: {main_snakefile} or {main_snakefile_root}")
            main_snakefile = main_snakefile_root

        original_config_path = workflow_path / "config" / "config.yaml"
        if not original_config_path.exists():
            logger.warning(f"Original config.yaml not found for workflow at: {original_config_path}. Starting with an empty config.")
            base_config = {}
        else:
            with open(original_config_path, 'r') as f:
                base_config = yaml.safe_load(f) or {}
        
        # Deep merge the user's config overrides into the base config
        merged_config = deep_merge(config_overrides, base_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, dir=workflow_path) as tmp_config_file:
            yaml.dump(merged_config, tmp_config_file)
            temp_config_path = Path(tmp_config_file.name)
        
        logger.debug(f"Generated temporary config for run: {temp_config_path}")

        # Build a simple, robust Snakemake command
        command = [
            "snakemake", 
            "--snakefile", str(main_snakefile),
            "--configfile", str(temp_config_path),
            "--cores", str(cores),
            "--nocolor",
            "--printshellcmds",
        ]

        if use_conda:
            command.append("--use-conda")
        
        if target_rule:
            command.append(target_rule)

        logger.info(f"Executing command: {' '.join(command)} in {workflow_path}")
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workflow_path
        )

        # Register process for potential cancellation
        if job_id:
            from .jobs import active_processes
            active_processes[job_id] = process

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"status": "failed", "stdout": "", "stderr": f"Execution timed out after {timeout} seconds.", "exit_code": -1, "error_message": "Timeout expired"}

        stdout = stdout_bytes.decode()
        stderr = stderr_bytes.decode()

        if process.returncode == 0:
            return {
                "status": "success",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": 0
            }
        else:
            error_msg = f"Snakemake workflow execution failed with exit code {process.returncode}"
            return {
                "status": "failed",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": process.returncode,
                "error_message": error_msg
            }

    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "error_message": error_msg
        }
    
    finally:
        if temp_config_path and temp_config_path.exists():
            try:
                os.remove(temp_config_path)
                logger.debug(f"Removed temporary config file: {temp_config_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary config file {temp_config_path}: {e}")

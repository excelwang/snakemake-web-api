import subprocess
import tempfile
import os
import logging
from pathlib import Path
from typing import Dict, Optional
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

def run_workflow(
    workflow_name: str,
    workflows_dir: str,
    config_overrides: dict,
    target_rule: Optional[str] = None,
    timeout: int = 3600,
) -> Dict:
    """
    Executes a Snakemake workflow by merging a config object with the base
    config.yaml and running Snakemake with a temporary config file.
    """
    temp_config_path = None
    try:
        if not workflow_name or not isinstance(workflow_name, str):
            raise ValueError("workflow_name must be a non-empty string")

        workflow_base_path = Path(workflows_dir)
        workflow_path = workflow_base_path / workflow_name
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
            "--cores", "1",
            "--use-conda",
            "--nocolor",
            "--printshellcmds",
            # All execution parameters like --cores, --resources must now be
            # handled by the workflow itself, using the config object.
        ]
        
        if target_rule:
            command.append(target_rule)

        logger.info(f"Executing command: {' '.join(command)} in {workflow_path}")
        
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True,
            timeout=timeout,
            cwd=workflow_path
        )
        
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"Snakemake workflow execution failed with exit code {e.returncode}"
        logger.error(error_msg)
        logger.error(f"Stdout:\n{e.stdout}")
        logger.error(f"Stderr:\n{e.stderr}")
        return {
            "status": "failed",
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "exit_code": e.returncode,
            "error_message": error_msg
        }
    
    except subprocess.TimeoutExpired as e:
        error_msg = f"Snakemake workflow execution timed out after {timeout} seconds"
        logger.error(error_msg)
        return {
            "status": "failed",
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": e.stderr.decode() if e.stderr else "",
            "exit_code": -1,
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

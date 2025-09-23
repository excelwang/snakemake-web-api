import subprocess
import tempfile
import os
import textwrap
import logging
from pathlib import Path
from typing import Union, Dict, List, Optional
import yaml

logger = logging.getLogger(__name__)

def _validate_workflow_inputs(workflow_name: str, 
                             inputs: Optional[Union[Dict, List]] = None, 
                             outputs: Optional[Union[Dict, List]] = None, 
                             params: Optional[Dict] = None,
                             config_content: Optional[Dict] = None) -> None:
    """Validate input parameters for workflow execution."""
    if not workflow_name or not isinstance(workflow_name, str):
        raise ValueError("workflow_name must be a non-empty string")
    
    # Add more specific validation for inputs, outputs, params if needed

def run_workflow(workflow_name: str,
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
                 workflow_base_dir: str = ".", # Added workflow_base_dir parameter
                 timeout: int = 600) -> Dict:
    """
    Executes a Snakemake workflow by modifying its config and running it.
    """
    temp_config_path = None
    try:
        _validate_workflow_inputs(workflow_name, inputs, outputs, params)

        # Determine workflow base directory
        # Now using the passed parameter instead of environment variable
        workflow_base_path = Path(workflow_base_dir)

        workflow_path = workflow_base_path / workflow_name
        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow not found at: {workflow_path}")
        
        main_snakefile = workflow_path / "workflow" / "Snakefile"
        if not main_snakefile.exists():
            raise FileNotFoundError(f"Main Snakefile not found for workflow at: {main_snakefile}")

        original_config_path = workflow_path / "config" / "config.yaml"
        if not original_config_path.exists():
            logger.warning(f"Original config.yaml not found for workflow at: {original_config_path}. Creating a new one.")
            original_config = {}
        else:
            with open(original_config_path, 'r') as f:
                original_config = yaml.safe_load(f)
        
        # Create a temporary config file by merging original with provided params
        merged_config = original_config.copy()
        if params:
            merged_config.update(params)
        
        # Handle inputs and outputs - this is a simplification and might need more sophisticated mapping
        if inputs:
            merged_config["inputs"] = inputs
        if outputs:
            merged_config["outputs"] = outputs

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp_config_file:
            yaml.dump(merged_config, tmp_config_file)
            temp_config_path = Path(tmp_config_file.name)
        
        logger.debug(f"Generated temporary config at: {temp_config_path}")

        # Build Snakemake command
        command = [
            "snakemake", 
            "--snakefile", str(main_snakefile),
            "--configfile", str(temp_config_path),
            "--use-conda", 
            "--cores", str(threads),
            "--printshellcmds"
        ]
        
        if target_rule:
            command.append(target_rule)
        else:
            # If no target rule, Snakemake will run the default target
            pass

        # Add extra parameters
        if extra_snakemake_args:
            command.extend(extra_snakemake_args.split())
        if container:
            command.extend(["--container-image", container])
        if benchmark:
            command.extend(["--benchmark-file", benchmark])
        if resources:
            for key, value in resources.items():
                command.extend(["--resources", f"{key}={value}"])
        if shadow:
            command.extend(["--shadow-prefix", shadow]) # Snakemake uses --shadow-prefix for shadow modes
        if conda_env:
            command.extend(["--conda-frontend", "mamba", "--conda-env", conda_env]) # Assuming mamba for speed

        logger.info(f"Executing command: {' '.join(command)}")
        
        # Execute command
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True,
            timeout=timeout,
            cwd=workflow_path # Run Snakemake from the workflow's base directory
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
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "error_message": error_msg
        }
    
    finally:
        # Clean up temporary config file
        if temp_config_path and temp_config_path.exists():
            try:
                os.remove(temp_config_path)
                logger.debug(f"Removed temporary config file: {temp_config_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary config file {temp_config_path}: {e}")

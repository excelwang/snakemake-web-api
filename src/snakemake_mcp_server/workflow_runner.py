import asyncio
import tempfile
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Union
import yaml
import collections.abc
from .utils import sync_workdir_to_s3

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
    use_cache: bool = False,
    timeout: int = 3600,
    job_id: Optional[str] = None,
    workdir: Optional[str] = None,
    workflow_profile: Optional[str] = None,
    prefill: bool = False,
) -> Dict:
    """
    Executes a Snakemake workflow by merging a config object with the base
    config.yaml and running Snakemake via asyncio.create_subprocess_exec.
    Outputs are redirected to a log file for real-time access.
    If 'workdir' is provided, execution happens there for isolation.
    Support for 'workflow_profile' allows K8s/S3 execution.
    'prefill' enables automatic S3 data provisioning.
    """
    temp_config_path = None
    log_file_path = None
    try:
        if not workflow_id or not isinstance(workflow_id, str):
            raise ValueError("workflow_id must be a non-empty string")

        workflow_base_path = Path(workflows_dir)
        workflow_source_path = (workflow_base_path / workflow_id).resolve()
        if not workflow_source_path.exists():
            raise FileNotFoundError(f"Workflow not found at: {workflow_source_path}")
        
        # Determine the execution directory
        execution_path = Path(workdir).resolve() if workdir else workflow_source_path
        execution_path.mkdir(parents=True, exist_ok=True)

        # Locate the Snakefile (it should be in the execution path now due to isolation setup)
        main_snakefile = execution_path / "workflow" / "Snakefile"
        if not main_snakefile.exists():
            main_snakefile_root = execution_path / "Snakefile"
            if not main_snakefile_root.exists():
                raise FileNotFoundError(f"Main Snakefile not found in execution path: {execution_path}")
            main_snakefile = main_snakefile_root

        # Load base config from the original source to ensure we have the defaults
        original_config_path = workflow_source_path / "config" / "config.yaml"
        if not original_config_path.exists():
            logger.warning(f"Original config.yaml not found for workflow at: {original_config_path}. Starting with an empty config.")
            base_config = {}
        else:
            with open(original_config_path, 'r') as f:
                base_config = yaml.safe_load(f) or {}
        
        # Deep merge the user's config overrides into the base config
        merged_config = deep_merge(config_overrides, base_config)

        # Write the temporary config file into the execution directory
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, dir=execution_path) as tmp_config_file:
            yaml.dump(merged_config, tmp_config_file)
            temp_config_path = Path(tmp_config_file.name)
        
        logger.debug(f"Generated temporary config for run: {temp_config_path}")

        # Setup real-time logging to file
        if job_id:
            log_dir = Path.home() / ".swa" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / f"{job_id}.log"
            log_file = open(log_file_path, 'w')
        else:
            log_file = None

        # Build a simple, robust Snakemake command
        command = [
            "snakemake", 
            "--snakefile", str(main_snakefile),
            "--configfile", str(temp_config_path),
            "--cores", str(cores),
            "--nocolor",
            "--printshellcmds",
        ]

        if workflow_profile:
            # 1. Search priority for the profile
            local_profile_path = execution_path / "workflow" / "profiles" / workflow_profile
            global_swa_profile_path = Path.home() / ".swa" / "profiles" / workflow_profile
            
            actual_profile_path = None
            if local_profile_path.exists():
                actual_profile_path = local_profile_path
            elif global_swa_profile_path.exists():
                actual_profile_path = global_swa_profile_path
            
            # 2. Add profile to command
            if actual_profile_path:
                command.extend(["--workflow-profile", str(actual_profile_path)])
            else:
                command.extend(["--workflow-profile", workflow_profile])

            # 3. Handle dynamic S3 prefix and pre-provisioning based on profile config
            if actual_profile_path and (actual_profile_path / "config.yaml").exists():
                try:
                    with open(actual_profile_path / "config.yaml", 'r') as f:
                        profile_config = yaml.safe_load(f) or {}
                    
                    common_prefix = profile_config.get("default-storage-provider") == "s3" and profile_config.get("default-storage-prefix")
                    if not common_prefix: # Fallback: check if s3 is in the prefix string anyway
                        prefix_val = profile_config.get("default-storage-prefix", "")
                        if prefix_val.startswith("s3://"):
                            common_prefix = prefix_val

                    if common_prefix:
                        # Construct dynamic prefix: base_prefix/swa-jobs/{job_id}/
                        base_prefix = common_prefix.rstrip('/')
                        dynamic_prefix = f"{base_prefix}/swa-jobs/{job_id or 'anonymous'}/"
                        
                        # Pre-provisioning: upload current workdir to S3 ONLY IF prefill is enabled
                        if prefill and workdir:
                            await sync_workdir_to_s3(str(execution_path), dynamic_prefix)
                        
                        # Override the storage prefix from the profile
                        command.extend(["--default-storage-prefix", dynamic_prefix])
                        logger.info(f"Using dynamic S3 prefix: {dynamic_prefix} (Prefill: {prefill})")
                except Exception as e:
                    logger.error(f"Failed to parse profile config for prefix extraction: {e}")

        if use_conda:
            command.append("--use-conda")
            # Use a global conda prefix to share environments across isolated runs
            conda_prefix = os.environ.get("SNAKEMAKE_CONDA_PREFIX", os.path.expanduser("~/.snakemake/conda"))
            command.extend(["--conda-prefix", conda_prefix])
        
        if use_cache:
            command.append("--cache")
        
        if target_rule:
            command.append(target_rule)

        logger.info(f"Executing command: {' '.join(command)} in {execution_path}")
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=log_file if log_file else asyncio.subprocess.PIPE,
            stderr=log_file if log_file else asyncio.subprocess.PIPE,
            cwd=execution_path
        )

        # Register process for potential cancellation
        if job_id:
            from .jobs import active_processes
            active_processes[job_id] = process

        try:
            if log_file:
                # If logging to file, we just wait for the process to exit
                await asyncio.wait_for(process.wait(), timeout=timeout)
                stdout = f"Logs redirected to {log_file_path}"
                stderr = ""
            else:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
                stdout = stdout_bytes.decode()
                stderr = stderr_bytes.decode()
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"status": "failed", "stdout": "", "stderr": f"Execution timed out after {timeout} seconds.", "exit_code": -1, "error_message": "Timeout expired"}
        finally:
            if log_file:
                log_file.close()

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

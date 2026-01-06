import asyncio
import tempfile
import os
import logging
import shutil
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
    Executes a Snakemake workflow in-place.
    Minimal interference with command line to ensure compatibility.
    """
    log_file_path = None
    try:
        if not workflow_id:
            raise ValueError("workflow_id must be a non-empty string")

        workflow_base_path = Path(workflows_dir)
        workflow_source_path = (workflow_base_path / workflow_id).resolve()
        
        # execution_path is the original source path for in-place run
        execution_path = workflow_source_path
        
        # Merge config and overwrite original config/config.yaml (temporary)
        original_config_path = workflow_source_path / "config" / "config.yaml"
        base_config = {}
        if original_config_path.exists():
            with open(original_config_path, 'r') as f:
                base_config = yaml.safe_load(f) or {}
        merged_config = deep_merge(config_overrides, base_config)

        # Ensure config dir exists
        (execution_path / "config").mkdir(parents=True, exist_ok=True)
        with open(execution_path / "config" / "config.yaml", 'w') as f:
            yaml.dump(merged_config, f)

        # Setup logging
        if job_id:
            log_dir = Path.home() / ".swa" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / f"{job_id}.log"
            log_file = open(log_file_path, 'w')
        else:
            log_file = None

        # Build MINIMAL command with explicit resource limits
        command = [
            "snakemake", 
            "--cores", str(cores),
            "--default-resources", "mem_mb=40960", "disk_mb=102400",
            "--shared-fs-usage", "none",
            "--software-deployment-method", "conda",
            "--scheduler", "greedy",
            "--notemp",
        ]

        if workflow_profile:
            # Handle profile modification for dynamic prefix
            # Priority: workflow-specific profile
            profile_path = execution_path / "workflow" / "profiles" / workflow_profile
            if not profile_path.exists():
                # Fallback to global profile
                global_profile = Path.home() / ".swa" / "profiles" / workflow_profile
                if global_profile.exists():
                    # Copy to local so Snakemake can see it in worker pods
                    dest = execution_path / "workflow" / "profiles" / workflow_profile
                    dest.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(global_profile, dest, dirs_exist_ok=True)
                    profile_path = dest

            command.extend(["--profile", str(profile_path.relative_to(execution_path)) if profile_path.is_relative_to(execution_path) else workflow_profile])

            # Update profile config.yaml with dynamic prefix
            config_file = profile_path / "config.yaml"
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        profile_config = yaml.safe_load(f) or {}
                    
                    provider = profile_config.get("default-storage-provider") or profile_config.get("default_storage_provider")
                    prefix_val = profile_config.get("default-storage-prefix") or profile_config.get("default_storage_prefix")

                    if (provider == "s3") or (prefix_val and prefix_val.startswith("s3://")):
                        base_prefix = prefix_val.rstrip('/')
                        # Prevent prefix accumulation: if '/swa-jobs/' is already in the prefix, 
                        # truncate everything from that point onwards to find the true base.
                        if "/swa-jobs/" in base_prefix:
                            base_prefix = base_prefix.split("/swa-jobs/")[0]
                            
                        dynamic_prefix = f"{base_prefix}/swa-jobs/{job_id or 'anonymous'}/"
                        
                        # Sync data to S3 if requested (prefill)
                        if prefill:
                            await sync_workdir_to_s3(str(execution_path), dynamic_prefix)
                        
                        profile_config["default-storage-prefix"] = dynamic_prefix
                        if not provider: profile_config["default-storage-provider"] = "s3"
                        
                        with open(config_file, 'w') as f:
                            yaml.dump(profile_config, f)
                        logger.info(f"Using dynamic S3 prefix: {dynamic_prefix}")
                except Exception as e:
                    logger.error(f"Failed to update profile for in-place run: {e}")

        if target_rule:
            command.append(target_rule)

        logger.info(f"Executing IN-PLACE command: {' '.join(command)} in {execution_path}")
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=log_file if log_file else asyncio.subprocess.PIPE,
            stderr=log_file if log_file else asyncio.subprocess.PIPE,
            cwd=execution_path
        )

        if job_id:
            from .jobs import active_processes
            active_processes[job_id] = process

        try:
            if log_file:
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
            return {"status": "failed", "stdout": "", "stderr": "Timeout", "exit_code": -1}
        finally:
            if log_file:
                log_file.close()

        return {"status": "success" if process.returncode == 0 else "failed", "stdout": stdout, "stderr": stderr, "exit_code": process.returncode}

    except Exception as e:
        logger.error(f"In-place run failed: {e}")
        return {"status": "failed", "stdout": "", "stderr": str(e), "exit_code": -1}
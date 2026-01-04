"""
Utility functions for handling Snakemake API responses.
"""
import logging
import shutil
import os
from pathlib import Path
from typing import Any, Optional
from .schemas import SnakemakeResponse

logger = logging.getLogger(__name__)


def setup_demo_workdir(demo_workdir: str, workdir: str):
    """
    Copies all files and directories from a demo source to a destination workdir.
    Handles symbolic links by copying them as symlinks.
    
    Args:
        demo_workdir (str): The source directory containing the demo files.
        workdir (str): The destination directory where files will be copied.
    """
    if not demo_workdir or not os.path.exists(demo_workdir):
        logger.warning(f"Demo workdir '{demo_workdir}' not provided or does not exist. Skipping file copy.")
        return

    demo_path = Path(demo_workdir)
    dest_path = Path(workdir)
    
    # Ensure the destination directory exists
    dest_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Copying demo files from {demo_path} to {dest_path}")
    try:
        # Use shutil.copytree to copy the entire directory, preserving symlinks
        # and allowing copying into an existing directory.
        shutil.copytree(demo_path, dest_path, symlinks=True, dirs_exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to copy demo directory {demo_path} to {dest_path}: {e}")
        raise

async def sync_workdir_to_s3(workdir: str, s3_prefix: str):
    """
    Syncs the local execution directory to S3 using boto3.
    Follows symlinks to ensure linked data is uploaded.
    Runs in a separate thread to avoid blocking the event loop.
    """
    import asyncio
    import boto3
    from urllib.parse import urlparse
    import os
    
    logger.info(f"Pre-provisioning data (boto3): {workdir} -> {s3_prefix}")
    
    def _do_sync():
        try:
            # Parse S3 URI
            parsed = urlparse(s3_prefix)
            bucket_name = parsed.netloc
            prefix = parsed.path.lstrip('/')

            # Initialize S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
            )

            workdir_path = Path(workdir)
            files_uploaded = 0
            
            # Walk through the directory and upload files.
            # followlinks=True is CRITICAL here because the isolation dir uses symlinks.
            for root, dirs, files in os.walk(workdir, followlinks=True):
                for file in files:
                    local_path = Path(root) / file
                    
                    # Exclude .snakemake and log files from the upload
                    if '.snakemake' in local_path.parts or local_path.suffix == '.log':
                        continue
                    
                    # Compute relative path for S3 key
                    rel_path = local_path.relative_to(workdir_path)
                    s3_key = os.path.join(prefix, str(rel_path))
                    
                    # For symlinks, we want to upload the target's content
                    source_to_upload = str(local_path.resolve()) if local_path.is_symlink() else str(local_path)
                    
                    logger.debug(f"Uploading: {rel_path} -> s3://{bucket_name}/{s3_key}")
                    
                    # upload_file automatically handles the path correctly
                    s3_client.upload_file(source_to_upload, bucket_name, s3_key)
                    files_uploaded += 1
            
            logger.info(f"S3 pre-provisioning complete. Uploaded {files_uploaded} files to {s3_prefix}")
            
        except Exception as e:
            logger.error(f"Error during S3 pre-provisioning with boto3: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # Run the blocking _do_sync in a separate thread
    await asyncio.to_thread(_do_sync)


def extract_response_status(data: Any) -> Optional[str]:
    """
    Extract status from response data, handling both structured models and dictionaries.
    
    Args:
        data: Response data that could be a SnakemakeResponse model or a dictionary
        
    Returns:
        Status string or None if not found
    """
    if hasattr(data, 'status'):
        return data.status
    elif isinstance(data, dict):
        return data.get('status')
    else:
        # For other object types that might have status attribute
        return getattr(data, 'status', None)


def extract_response_error_message(data: Any) -> Optional[str]:
    """
    Extract error message from response data, handling both structured models and dictionaries.
    
    Args:
        data: Response data that could be a SnakemakeResponse model or a dictionary
        
    Returns:
        Error message string or None if not found
    """
    if hasattr(data, 'error_message'):
        return data.error_message
    elif isinstance(data, dict):
        return data.get('error_message')
    else:
        # For other object types that might have error_message attribute
        return getattr(data, 'error_message', None)


def extract_response_exit_code(data: Any) -> Optional[int]:
    """
    Extract exit code from response data, handling both structured models and dictionaries.
    
    Args:
        data: Response data that could be a SnakemakeResponse model or a dictionary
        
    Returns:
        Exit code integer or None if not found
    """
    if hasattr(data, 'exit_code'):
        return data.exit_code
    elif isinstance(data, dict):
        return data.get('exit_code')
    else:
        # For other object types that might have exit_code attribute
        return getattr(data, 'exit_code', None)

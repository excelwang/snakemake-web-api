import click
import logging
import os
import sys
import uvicorn
import subprocess
import signal
import time
from pathlib import Path
from ..api.main import create_native_fastapi_app

logger = logging.getLogger(__name__)

PID_FILE = Path.home() / ".swa" / "rest.pid"

def get_pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, IOError):
            return None
    return None

def is_running(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

# Common options for reuse
def common_rest_options(f):
    options = [
        click.option("--host", default="127.0.0.1", help="Host to bind to. Default: 127.0.0.1"),
        click.option("--port", default=8082, type=int, help="Port to bind to. Default: 8082"),
        click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
                      help="Logging level. Default: INFO"),
        click.option("--workflow-profile", default=None, help="Default Snakemake profile to use for all workflows (e.g., 'k3s-s3')."),
        click.option("--prefill", is_flag=True, help="Enable automatic data pre-provisioning to S3 for remote profiles.")
    ]
    for option in reversed(options):
        f = option(f)
    return f

@click.group(
    help="Manage the Snakemake REST API server.",
    invoke_without_command=True
)
@common_rest_options
@click.pass_context
def rest(ctx, host, port, log_level, workflow_profile, prefill):
    """Manage the Snakemake REST API server."""
    ctx.ensure_object(dict)
    # Store initial values in context
    ctx.obj['HOST'] = host
    ctx.obj['PORT'] = port
    ctx.obj['LOG_LEVEL'] = log_level
    ctx.obj['WORKFLOW_PROFILE'] = workflow_profile
    ctx.obj['PREFILL'] = prefill

    if ctx.invoked_subcommand is None:
        ctx.invoke(run)

def merge_params(ctx, host, port, log_level, workflow_profile, prefill):
    """Merge params from group and subcommand, prioritizing subcommand."""
    # If subcommand provides a non-default/explicit value, use it. 
    # Otherwise use what was in the group context.
    
    # Simple logic: if subcommand params are provided, they take precedence.
    # Note: Click defaults make this slightly tricky, so we check if they were provided in the command line.
    
    final_host = host if ctx.get_parameter_source('host') != click.core.ParameterSource.DEFAULT else ctx.obj.get('HOST', host)
    final_port = port if ctx.get_parameter_source('port') != click.core.ParameterSource.DEFAULT else ctx.obj.get('PORT', port)
    final_log_level = log_level if ctx.get_parameter_source('log_level') != click.core.ParameterSource.DEFAULT else ctx.obj.get('LOG_LEVEL', log_level)
    final_workflow_profile = workflow_profile if ctx.get_parameter_source('workflow_profile') != click.core.ParameterSource.DEFAULT else ctx.obj.get('WORKFLOW_PROFILE', workflow_profile)
    final_prefill = prefill if ctx.get_parameter_source('prefill') != click.core.ParameterSource.DEFAULT else ctx.obj.get('PREFILL', prefill)
    
    return final_host, final_port, final_log_level, final_workflow_profile, final_prefill

@rest.command(help="Run the server in the foreground (blocking).")
@common_rest_options
@click.pass_context
def run(ctx, host, port, log_level, workflow_profile, prefill):
    """Start the Snakemake server with native FastAPI REST endpoints."""
    host, port, log_level, workflow_profile, prefill = merge_params(ctx, host, port, log_level, workflow_profile, prefill)

    # Reconfigure logging to respect the user's choice
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    
    wrappers_path = ctx.obj['WRAPPERS_PATH']
    workflows_dir = ctx.obj['WORKFLOWS_DIR']
    
    logger.info(f"Starting Snakemake Server with native FastAPI REST API...")
    logger.info(f"FastAPI server will be available at http://{host}:{port}")
    if workflow_profile:
        logger.info(f"Using default workflow profile: {workflow_profile}")
    if prefill:
        logger.info("Data pre-provisioning (prefill) is ENABLED.")
    
    if not os.path.isdir(wrappers_path):
        logger.error(f"Wrappers directory not found at: {wrappers_path}")
        sys.exit(1)
    
    if not os.path.isdir(workflows_dir):
        logger.error(f"Workflows directory not found at: {workflows_dir}")
        sys.exit(1)

    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    app.state.workflow_profile = workflow_profile
    app.state.prefill = prefill
    
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())

@rest.command(help="Start the server in the background.")
@common_rest_options
@click.pass_context
def start(ctx, host, port, log_level, workflow_profile, prefill):
    pid = get_pid()
    if is_running(pid):
        click.echo(f"Server is already running (PID: {pid}).")
        return

    host, port, log_level, workflow_profile, prefill = merge_params(ctx, host, port, log_level, workflow_profile, prefill)
    
    # Ensure log directory exists
    log_dir = Path.home() / ".swa" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log = log_dir / "server.log"

    click.echo(f"Starting Snakemake Server in background on {host}:{port}...")
    
    # Build command to run the 'run' subcommand
    cmd = [
        sys.executable, "-m", "snakemake_mcp_server.server", "rest"
    ]
    
    # Add options BEFORE the subcommand 'run' to be safe, but our new logic handles both
    cmd.extend(["--host", host, "--port", str(port), "--log-level", log_level])
    if workflow_profile:
        cmd.extend(["--workflow-profile", workflow_profile])
    if prefill:
        cmd.append("--prefill")
    
    cmd.append("run")
    
    with open(server_log, "a") as f:
        process = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=f,
            preexec_fn=os.setpgrp if os.name != 'nt' else None
        )
    
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(process.pid))
    
    # Give it a second to start and check
    time.sleep(2)
    if is_running(process.pid):
        click.echo(f"Server started (PID: {process.pid}).")
        click.echo(f"Logs: {server_log}")
    else:
        click.echo("Server failed to start. Check logs.")

@rest.command(help="Stop the background server.")
def stop():
    pid = get_pid()
    if not is_running(pid):
        click.echo("Server is not running.")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return

    click.echo(f"Stopping server (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait a bit for it to stop
        for _ in range(5):
            if not is_running(pid):
                break
            time.sleep(1)
        
        if is_running(pid):
            os.kill(pid, signal.SIGKILL)
            
        click.echo("Server stopped.")
    except OSError as e:
        click.echo(f"Error stopping server: {e}")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()

@rest.command(help="Check the status of the server.")
def status():
    pid = get_pid()
    if is_running(pid):
        click.echo(f"Server is running (PID: {pid}).")
    else:
        click.echo("Server is not running.")

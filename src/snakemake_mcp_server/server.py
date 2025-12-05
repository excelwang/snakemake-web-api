import click
import sys
import os
import logging
import dotenv
from pathlib import Path

# Load environment variables from ~/.swa/.env if file exists
config_dir = Path.home() / ".swa"
env_file = config_dir / ".env"

if env_file.exists():
    dotenv.load_dotenv(env_file)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from .wrapper_runner import run_wrapper
    from .workflow_runner import run_workflow
except ImportError as e:
    logger.error(f"Could not import runner module: {e}")
    sys.exit(1)

def validate_paths(snakebase_dir):
    """Validate the snakebase directory structure."""
    snakebase_path = Path(snakebase_dir).resolve()
    if not snakebase_path.exists():
        click.echo(f"Error: snakebase directory does not exist: {snakebase_path}", err=True)
        sys.exit(1)
    
    wrappers_path = snakebase_path / "snakemake-wrappers"
    workflows_dir = snakebase_path / "snakemake-workflows"
    
    return str(wrappers_path), str(workflows_dir)

@click.group(
    help="Snakemake API Server - A server for running Snakemake wrappers and workflows."
)
@click.option(
    '--snakebase-dir', 
    default=lambda: os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase")),
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Base directory for snakebase containing snakemake-wrappers and snakemake-workflows subdirectories. "
         "Defaults to SNAKEBASE_DIR environment variable or '~/snakebase'."
)
@click.pass_context
def cli(ctx, snakebase_dir):
    """Main CLI group for Snakemake API Server."""
    ctx.ensure_object(dict)
    wrappers_path, workflows_dir = validate_paths(snakebase_dir)
    
    # Add paths to context
    ctx.obj['SNAKEBASE_DIR'] = Path(snakebase_dir).resolve()
    ctx.obj['WRAPPERS_PATH'] = wrappers_path
    ctx.obj['WORKFLOWS_DIR'] = workflows_dir


from .cli.parse import parse
from .cli.run import run
from .cli.verify import verify

# The native FastAPI implementation with proper Pydantic models
# is now in the fastapi_app.py file to maintain consistency
# and follow proper module separation.
# Only the 'run' command variant is available for running the server.

cli.add_command(parse)
cli.add_command(run)
cli.add_command(verify)


def main():
    cli()

if __name__ == "__main__":
    main()
import click
import os
import json
import yaml
from pathlib import Path
import shutil
import traceback

from ..snakefile_parser import generate_demo_calls_for_wrapper
from ..schemas import WrapperMetadata, DemoCall, WrapperInfo, UserProvidedParams, PlatformRunParams

# --- Constants ---
CACHE_BASE_DIR = Path.home() / ".swa" / "cache"
WRAPPER_CACHE_DIR = CACHE_BASE_DIR / "wrappers"
WORKFLOW_CACHE_DIR = CACHE_BASE_DIR / "workflows"


# --- Helper Functions ---

def _parse_and_cache_wrapper(wrapper_path: Path, wrappers_base_path: Path):
    """Parses a single wrapper's metadata and demos, then caches it."""
    meta_file_path = wrapper_path / "meta.yaml"
    if not meta_file_path.exists():
        return False, 0

    wrapper_rel_path = wrapper_path.relative_to(wrappers_base_path).as_posix()
    
    try:
        with open(meta_file_path, 'r', encoding='utf-8') as f:
            meta_data = yaml.safe_load(f)
        
        notes_data = meta_data.get('notes')
        if isinstance(notes_data, str):
            notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]
            meta_data['notes'] = notes_data # Update meta_data with processed notes

        basic_demo_calls = generate_demo_calls_for_wrapper(str(wrapper_path), str(wrappers_base_path))
        num_demos = len(basic_demo_calls) if basic_demo_calls else 0
        
        enhanced_demos = [
            DemoCall(method='POST', endpoint='/tool-processes', payload=call).model_dump(mode="json")
            for call in basic_demo_calls
        ] if num_demos > 0 else None
        
        # Prepare info data by merging meta_data and ensuring name exists
        info_dict = meta_data.copy()
        if 'name' not in info_dict:
            info_dict['name'] = wrapper_path.name
            
        wrapper_meta = WrapperMetadata(
            id=wrapper_rel_path,
            info=WrapperInfo(**info_dict),
            user_params=UserProvidedParams(**meta_data),
            platform_params=PlatformRunParams(**meta_data)
        )

        cache_data = wrapper_meta.model_dump(mode="json")
        cache_data["demos"] = enhanced_demos

        cache_file_path = WRAPPER_CACHE_DIR / f"{wrapper_rel_path}.json"
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        return True, num_demos
    except Exception as e:
        click.echo(f"  [ERROR] Failed to parse wrapper {wrapper_rel_path}: {e}", err=True)
        return False, 0

def _parse_and_cache_workflow(workflow_path: Path, workflows_base_path: Path):
    """Parses a single workflow's metadata, config, and demos, then caches it."""
    workflow_id = workflow_path.name
    
    try:
        # 1. Parse config.yaml for default values
        config_path = workflow_path / "config" / "config.yaml"
        default_config = {}
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                default_config = yaml.safe_load(f) or {}

        # 2. Parse meta.yaml for info and param descriptions
        meta_path = workflow_path / "meta.yaml"
        info_data, params_schema = None, None
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta_data = yaml.safe_load(f) or {}
            info_data = meta_data.get("info") or {
                "name": meta_data.get("name", workflow_id),
                "description": meta_data.get("description"),
                "authors": meta_data.get("authors"),
                "notes": meta_data.get("notes")
            }
            params_schema = meta_data.get("params_schema")

        # 3. Parse demos/ directory
        demos_path = workflow_path / "demos"
        demos_list = []
        if demos_path.is_dir():
            for demo_file in demos_path.glob("*.yaml"):
                with open(demo_file, 'r', encoding='utf-8') as f:
                    demo_config = yaml.safe_load(f) or {}
                demos_list.append({
                    "name": demo_file.stem,
                    "description": demo_config.get("__description__"), # Optional description key within demo file
                    "config": {k: v for k, v in demo_config.items() if k != "__description__"}
                })
        
        # fallback to config/config.yaml as a demo if no demos found
        if not demos_list and config_path.exists():
            demos_list.append({
                "name": "default",
                "description": "Default configuration from config/config.yaml",
                "config": default_config
            })
        
        # 4. Assemble and cache
        cache_data = {
            "id": workflow_id,
            "info": info_data,
            "default_config": default_config,
            "params_schema": params_schema,
            "demos": demos_list
        }

        cache_file_path = WORKFLOW_CACHE_DIR / f"{workflow_id}.json"
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file_path, 'w') as f:
            json.dump(cache_data, f, indent=2)

        return True, len(demos_list)
    except Exception as e:
        click.echo(f"  [ERROR] Failed to parse workflow {workflow_id}: {e}", err=True)
        traceback.print_exc()
        return False, 0


# --- Main CLI Command ---

@click.command(help="Parse all wrappers and workflows to cache metadata.")
@click.pass_context
def parse(ctx):
    """Parses all wrappers and workflows, creating a metadata cache."""
    wrappers_path = Path(ctx.obj['WRAPPERS_PATH'])
    workflows_path = Path(ctx.obj['WORKFLOWS_DIR'])
    
    # --- Clear and Setup Cache Directories ---
    click.echo(f"Cache base directory: {CACHE_BASE_DIR}")
    if CACHE_BASE_DIR.exists():
        shutil.rmtree(CACHE_BASE_DIR)
        click.echo("Cleared existing cache.")
    WRAPPER_CACHE_DIR.mkdir(parents=True)
    WORKFLOW_CACHE_DIR.mkdir(parents=True)
    
    # --- Parse Wrappers ---
    click.echo(f"\nParsing wrappers in: {wrappers_path}")
    total_wrappers = 0
    parsed_wrappers = 0
    total_wrapper_demos = 0
    for root, dirs, files in os.walk(wrappers_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if "meta.yaml" in files and "wrapper.py" in files:
            total_wrappers += 1
            success, num_demos = _parse_and_cache_wrapper(Path(root), wrappers_path)
            if success:
                parsed_wrappers += 1
                total_wrapper_demos += num_demos
    click.echo(f"-> Parsed {parsed_wrappers}/{total_wrappers} wrappers with {total_wrapper_demos} demos.")
    
    # --- Parse Workflows ---
    click.echo(f"\nParsing workflows in: {workflows_path}")
    total_workflows = 0
    parsed_workflows = 0
    total_workflow_demos = 0
    if workflows_path.is_dir():
        for item in workflows_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it's a valid workflow (e.g., has a Snakefile)
                if (item / "workflow" / "Snakefile").exists() or (item / "Snakefile").exists():
                    total_workflows += 1
                    click.echo(f"Parsing workflow: {item.name}")
                    success, num_demos = _parse_and_cache_workflow(item, workflows_path)
                    if success:
                        parsed_workflows += 1
                        total_workflow_demos += num_demos
    click.echo(f"-> Parsed {parsed_workflows}/{total_workflows} workflows with {total_workflow_demos} demos.")
    
    click.echo("\nCache generation complete.")

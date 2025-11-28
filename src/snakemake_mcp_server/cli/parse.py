import click
import os
import json
import yaml
from pathlib import Path
import shutil
import traceback

from ..snakefile_parser import generate_demo_calls_for_wrapper
from ..schemas import WrapperMetadata, DemoCall, WrapperInfo, UserProvidedParams, PlatformRunParams

def _parse_and_cache_wrapper(wrapper_path: Path, wrappers_base_path: Path, cache_dir: Path):
    """Parses a single wrapper's metadata and demos, then caches it to a JSON file."""
    meta_file_path = wrapper_path / "meta.yaml"
    if not meta_file_path.exists():
        click.echo(f"  [WARNING] No meta.yaml found in {wrapper_path}. Skipping.", err=True)
        return False, 0

    wrapper_rel_path = wrapper_path.relative_to(wrappers_base_path).as_posix()
    click.echo(f"Parsing wrapper: {wrapper_rel_path}")

    try:
        with open(meta_file_path, 'r', encoding='utf-8') as f:
            meta_data = yaml.safe_load(f)
        
        notes_data = meta_data.get('notes')
        if isinstance(notes_data, str):
            notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]

        # Pre-parse demos using the robust DAG-based parser
        basic_demo_calls = generate_demo_calls_for_wrapper(str(wrapper_path), str(wrappers_base_path))
        num_demos = len(basic_demo_calls) if basic_demo_calls else 0
        
        if num_demos > 0:
            enhanced_demos = [
                DemoCall(method='POST', endpoint='/tool-processes', payload=call).model_dump(mode="json")
                for call in basic_demo_calls
            ]
        else:
            enhanced_demos = None
        
        wrapper_meta = WrapperMetadata(
            id=wrapper_rel_path,
            info=WrapperInfo(
                name=meta_data.get('name', wrapper_path.name),
                description=meta_data.get('description'),
                url=meta_data.get('url'),
                authors=meta_data.get('authors'),
                notes=notes_data
            ),
            user_params=UserProvidedParams(
                inputs=meta_data.get('input'),
                outputs=meta_data.get('output'),
                params=meta_data.get('params')
            ),
            platform_params=PlatformRunParams(
                log=meta_data.get('log'),
                threads=meta_data.get('threads'),
                resources=meta_data.get('resources'),
                priority=meta_data.get('priority'),
                shadow_depth=meta_data.get('shadow_depth'),
                benchmark=meta_data.get('benchmark'),
                container_img=meta_data.get('container_img'),
                env_modules=meta_data.get('env_modules'),
                group=meta_data.get('group')
            )
        )

        cache_data = wrapper_meta.model_dump(mode="json")
        cache_data["demos"] = enhanced_demos

        cache_file_path = cache_dir / f"{wrapper_rel_path}.json"
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file_path, 'w') as f:
            f.write(json.dumps(cache_data, indent=2))
        
        return True, num_demos

    except Exception as e:
        click.echo(f"  [ERROR] Failed to parse or cache {wrapper_rel_path}: {e}", err=True)
        traceback.print_exc()
        return False, 0


@click.command(
    help="Parse wrappers and cache metadata. Can parse all wrappers or a specific one."
)
@click.option('--wrapper-id', default=None, help='Parse a specific wrapper by its ID (e.g., "bio/samtools/faidx").')
@click.pass_context
def parse(ctx, wrapper_id):
    """Parses wrapper metadata and demos, then caches them."""
    wrappers_path_str = ctx.obj['WRAPPERS_PATH']
    wrappers_path = Path(wrappers_path_str)
    cache_dir = Path.home() / ".swa" / "parser"

    if wrapper_id:
        # Parse a single, specific wrapper
        click.echo(f"Parsing specific wrapper: {wrapper_id}")
        specific_wrapper_path = (wrappers_path / wrapper_id).resolve()
        
        if not specific_wrapper_path.exists():
            click.echo(f"Error: Wrapper path does not exist: {specific_wrapper_path}", err=True)
            return

        cache_dir.mkdir(parents=True, exist_ok=True) # Ensure cache dir exists
        success, num_demos = _parse_and_cache_wrapper(specific_wrapper_path, wrappers_path, cache_dir)
        
        if success:
            click.echo(f"\nSuccessfully parsed and cached wrapper '{wrapper_id}' with {num_demos} demos in {cache_dir}")
        else:
            click.echo(f"\nFailed to parse and cache wrapper '{wrapper_id}'.")

    else:
        # Parse all wrappers
        click.echo(f"Starting full parser cache generation for wrappers in: {wrappers_path}")
        
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            click.echo(f"Cleared existing cache directory: {cache_dir}")
        cache_dir.mkdir()

        wrapper_count = 0
        total_demo_count = 0
        parsed_wrappers = 0

        for root, dirs, files in os.walk(wrappers_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            if "meta.yaml" in files:
                wrapper_count += 1
                success, num_demos = _parse_and_cache_wrapper(Path(root), wrappers_path, cache_dir)
                if success:
                    parsed_wrappers += 1
                    total_demo_count += num_demos

        click.echo(f"\nSuccessfully parsed and cached {parsed_wrappers}/{wrapper_count} wrappers and {total_demo_count} demos in {cache_dir}")

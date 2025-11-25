import click
import os
import json
import yaml
from pathlib import Path
from ..snakefile_parser import generate_demo_calls_for_wrapper
from ..schemas import WrapperMetadata, DemoCall, WrapperInfo, UserProvidedParams, PlatformRunParams

@click.command(
    help="Parse all wrappers and cache the metadata to JSON files for faster server startup."
)
@click.pass_context
def parse(ctx):
    """Parses all wrapper metadata and demos, then caches them."""
    wrappers_path_str = ctx.obj['WRAPPERS_PATH']
    wrappers_path = Path(wrappers_path_str)
    cache_dir = Path.home() / ".swa" / "parser"
    
    click.echo(f"Starting parser cache generation for wrappers in: {wrappers_path}")
    
    # Create or clear the cache directory
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        click.echo(f"Cleared existing cache directory: {cache_dir}")
    cache_dir.mkdir()

    wrapper_count = 0
    total_demo_count = 0
    for root, dirs, files in os.walk(wrappers_path):
        # Skip hidden directories, including the cache dir itself
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if "meta.yaml" in files:
            wrapper_count += 1
            meta_file_path = os.path.join(root, "meta.yaml")
            wrapper_rel_path = os.path.relpath(root, wrappers_path)
            click.echo(f"Parsing wrapper {wrapper_count}: {wrapper_rel_path}")
            
            try:
                with open(meta_file_path, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
                
                notes_data = meta_data.get('notes')
                if isinstance(notes_data, str):
                    notes_data = [line.strip() for line in notes_data.split('\n') if line.strip()]

                # Pre-parse demos using the robust DAG-based parser
                basic_demo_calls = generate_demo_calls_for_wrapper(root, wrappers_path_str)
                num_demos = len(basic_demo_calls) if basic_demo_calls else 0
                if num_demos > 0:
                    total_demo_count += num_demos
                    enhanced_demos = [
                        DemoCall(method='POST', endpoint='/tool-processes', payload=call).model_dump(mode="json")
                        for call in basic_demo_calls
                    ]
                else:
                    enhanced_demos = None
                
                wrapper_meta = WrapperMetadata(
                    id=wrapper_rel_path,  # 唯一标识符
                    info=WrapperInfo(
                        name=meta_data.get('name', os.path.basename(root)),  # 显示名称
                        description=meta_data.get('description'),
                        url=meta_data.get('url'),
                        authors=meta_data.get('authors'),
                        notes=notes_data
                    ),
                    user_params=UserProvidedParams(
                        inputs=meta_data.get('input'),  # meta.yaml 中的 input 映射到 inputs
                        outputs=meta_data.get('output'),  # meta.yaml 中的 output 映射到 outputs
                        params=meta_data.get('params')
                    ),
                    platform_params=PlatformRunParams(
                        log=meta_data.get('log'),
                        threads=meta_data.get('threads'),
                        resources=meta_data.get('resources'),
                        priority=meta_data.get('priority'),
                        shadow_depth=meta_data.get('shadow_depth'),
                        benchmark=meta_data.get('benchmark'),
                        conda_env=meta_data.get('conda_env'),
                        container_img=meta_data.get('container_img'),
                        env_modules=meta_data.get('env_modules'),
                        group=meta_data.get('group')
                    )
                )

                # Save to cache with demos included in the JSON
                cache_data = wrapper_meta.model_dump(mode="json")
                cache_data["demos"] = enhanced_demos

                # Save to cache
                cache_file_path = cache_dir / f"{wrapper_rel_path}.json"
                cache_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file_path, 'w') as f:
                    f.write(json.dumps(cache_data, indent=2))

            except Exception as e:
                click.echo(f"  [ERROR] Failed to parse or cache {wrapper_rel_path}: {e}", err=True)
                import traceback
                traceback.print_exc() # Print full traceback for debugging

    click.echo(f"\nSuccessfully parsed and cached {wrapper_count} wrappers and {total_demo_count} demos in {cache_dir}")

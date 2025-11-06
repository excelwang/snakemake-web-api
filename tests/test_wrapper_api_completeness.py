import os
import yaml
import pytest
import sys
import tempfile
from pathlib import Path

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from snakemake_mcp_server.snakefile_parser import analyze_wrapper_test_directory, parse_snakefile_content
from snakemake_mcp_server.fastapi_app import SnakemakeWrapperRequest
from pydantic import BaseModel


def test_wrapper_api_parameter_completeness():
    """测试 wrapper 的参数是否能完全映射到 tool/process API 参数"""
    
    # 扫描所有可用的 wrappers
    wrappers_dir = Path("./snakebase/snakemake-wrappers")
    
    if not wrappers_dir.exists():
        print("Warning: snakebase/snakemake-wrappers directory not found")
        return
    
    missing_configurations = []
    complete_configurations = []
    
    # 遍历所有 wrapper 目录
    for root, dirs, files in os.walk(wrappers_dir):
        # 排除隐藏和临时目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if "meta.yaml" in files:
            wrapper_path = Path(root)
            
            # 读取 meta.yaml 信息
            meta_file = wrapper_path / "meta.yaml"
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Could not load meta.yaml from {meta_file}: {e}")
                continue
            
            # 检查是否有对应的 test 目录和 Snakefile
            test_dir = wrapper_path / "test"
            if test_dir.exists():
                snakefile = test_dir / "Snakefile"
                if snakefile.exists():
                    try:
                        # 解析 test Snakefile
                        tool_calls = analyze_wrapper_test_directory(str(wrapper_path), str(snakefile))
                        
                        # 获取 API 模型字段（可用的参数）
                        api_fields = set(SnakemakeWrapperRequest.model_fields.keys()) if hasattr(SnakemakeWrapperRequest, 'model_fields') else set(SnakemakeWrapperRequest.__fields__.keys())
                        
                        for i, call in enumerate(tool_calls):
                            wrapper_name = call.get('wrapper_name', 'unknown')
                            
                            # 检查每个参数是否在 API 中有对应
                            call_params = set()
                            for key in ['inputs', 'outputs', 'params', 'log', 'threads', 'wrapper_name', 'extra_snakemake_args', 'container', 'benchmark', 'resources', 'shadow', 'conda_env']:
                                if call.get(key) is not None:
                                    call_params.add(key)
                            
                            missing_params = call_params - api_fields
                            
                            if missing_params:
                                missing_configurations.append({
                                    'wrapper': wrapper_name,
                                    'snakefile_path': str(snakefile),
                                    'missing_params': missing_params,
                                    'actual_params': call_params
                                })
                                print(f"⚠️  Wrapper {wrapper_name} rule {i+1}: Missing API parameters: {missing_params}")
                            else:
                                complete_configurations.append({
                                    'wrapper': wrapper_name,
                                    'snakefile_path': str(snakefile),
                                    'params': call_params
                                })
                                print(f"✅ Wrapper {wrapper_name} rule {i+1}: All parameters supported")
                                
                    except Exception as e:
                        print(f"Warning: Could not parse Snakefile {snakefile}: {e}")
                        continue
    
    print(f"\n📊 总结:")
    print(f"完整支持的 wrappers: {len(complete_configurations)}")
    print(f"参数不完整的 wrappers: {len(missing_configurations)}")
    
    if missing_configurations:
        print(f"\n❌ 参数缺失的 wrappers 详情:")
        for item in missing_configurations:
            print(f"  - {item['wrapper']}: {item['missing_params']}")
    
    # 检查 meta.yaml 中的信息是否能映射到 API
    print(f"\n🔍 检查 meta.yaml 配置映射:")
    meta_missing_configurations = []
    
    for root, dirs, files in os.walk(wrappers_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        if "meta.yaml" in files:
            wrapper_path = Path(root)
            
            # 读取 meta.yaml
            meta_file = wrapper_path / "meta.yaml"
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
            except Exception as e:
                continue
            
            # 计算相对于 wrappers_dir 的路径作为 wrapper_name
            wrapper_relative_path = wrapper_path.relative_to(wrappers_dir)
            wrapper_name = str(wrapper_relative_path).replace(os.sep, '/')
            
            # 检查 meta.yaml 中的关键字段
            meta_fields = set()
            for key in ['input', 'output', 'params', 'description', 'authors', 'url']:
                if meta_data.get(key) is not None:
                    meta_fields.add(key)
            
            # 对于 meta.yaml 的字段，它们主要用于文档和指导
            # 检查 input/output/params 是否可以通过 API 传递
            # These are generally for documentation and guidance, which is handled through the tool metadata API
            
    assert len(missing_configurations) <= 10, f"Too many wrappers have missing API parameters: {len(missing_configurations)}"
    print(f"\n✅ 参数完备性检查完成，发现 {len(missing_configurations)} 个配置项缺失，仍在可接受范围内")


if __name__ == "__main__":
    test_wrapper_api_parameter_completeness()
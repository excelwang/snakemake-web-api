import subprocess
import tempfile
import os
import textwrap
import logging
from pathlib import Path
from typing import Union, Dict, List, Optional

logger = logging.getLogger(__name__)

def _validate_inputs(wrapper_name: str, 
                    inputs: Optional[Union[Dict, List]] = None, 
                    outputs: Optional[Union[Dict, List]] = None, 
                    params: Optional[Dict] = None, threads: int = 1, 
                    log: Optional[Union[Dict, List]] = None) -> None:
    """Validate input parameters."""
    if not wrapper_name or not isinstance(wrapper_name, str):
        raise ValueError("wrapper_name must be a non-empty string")
    
    if not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    
    # 验证文件路径格式 (only if inputs are provided)
    if inputs is not None:
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                if not isinstance(value, (str, list)):
                    raise ValueError(f"Invalid input format for key '{key}': {type(value)}")
        elif isinstance(inputs, list):
            for item in inputs:
                if not isinstance(item, str):
                    raise ValueError(f"Invalid input format: {type(item)}")
        else:
            raise ValueError("inputs must be a dict or list or None")

def _format_rule_section(data, directive: str = ""):
    """Helper function to format a dictionary or list into a Snakemake rule string."""
    if data is None:
        return ""
    if not data:
        return ""
    
    try:
        if directive == "resources":
            items = [f"{key}={value}" for key, value in data.items()]
            return textwrap.indent(",\n".join(items), "        ")
        elif isinstance(data, dict):
            items = []
            for key, value in data.items():
                if isinstance(value, str) and ("(" in value or "[" in value):
                    items.append(f"{key}={value}")
                else:
                    items.append(f"{key}={repr(value)}")
            return textwrap.indent(",\n".join(items), "        ")
        elif isinstance(data, list):
            items = []
            for value in data:
                if isinstance(value, str):
                    if "(" in value or "[" in value:
                        items.append(value)
                    else:
                        items.append(repr(value))
            return textwrap.indent(",\n".join(items), "        ")
        elif isinstance(data, str) and ("(" in data or "[" in data):
            return textwrap.indent(data, "        ")
        else:
            return textwrap.indent(repr(data), "        ")
    except Exception as e:
        logger.error(f"Error formatting rule section: {e}")
        raise ValueError(f"Failed to format rule section: {e}")

def run_wrapper(wrapper_name: str, 
                wrappers_path: str, 
                inputs: Optional[Union[Dict, List]] = None, 
                outputs: Optional[Union[Dict, List]] = None, 
                params: Optional[Dict] = None, threads: int = 1, 
                log: Optional[Union[Dict, List]] = None, 
                extra_snakemake_args: str = "", 
                container: Optional[str] = None,
                benchmark: Optional[str] = None,
                resources: Optional[Dict] = None,
                shadow: Optional[str] = None,
                conda_env: Optional[str] = None,
                workdir: Optional[str] = None,
                timeout: int = 600) -> Dict:
    """ 
    Dynamically generates a Snakefile to run a single Snakemake wrapper and executes it.
    
    Args:
        timeout (int): Timeout in seconds for the subprocess execution.
    """
    snakefile_path = None
    temp_conda_env_file = None
    try:
        # 验证输入
        _validate_inputs(wrapper_name, inputs, outputs, params, threads, log)
        
        # 确定wrapper路径
        wrapper_path = Path(wrappers_path) / wrapper_name
        if not wrapper_path.exists():
            raise FileNotFoundError(f"Wrapper not found at: {wrapper_path}")
        
        # Convert to absolute path to avoid resolution issues
        wrapper_path = wrapper_path.resolve()
        wrapper_url = f"file://{wrapper_path}"
        
        # 格式化规则部分
        input_str = _format_rule_section(inputs)
        output_str = _format_rule_section(outputs)
        params_str = _format_rule_section(params)
        log_str = _format_rule_section(log)
        benchmark_str = f'benchmark: "{benchmark}"' if benchmark else ""
        container_str = f'container: "{container}"' if container else ""
        resources_str = _format_rule_section(resources, "resources") if resources else ""
        shadow_str = f'shadow: "{shadow}"' if shadow else ""
        
        conda_str = ""
        if conda_env:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
                tmp.write(conda_env)
                temp_conda_env_file = tmp.name
            conda_str = f'conda: "{temp_conda_env_file}"'

        # 组装Snakefile内容
        snakefile_content = f"""
rule run_single_wrapper:
    input:
{input_str}
    output:
{output_str}
    params:
{params_str}
    threads:
        {threads}
    log:
{log_str}
    {benchmark_str}
    {container_str}
    {conda_str}
    resources:
{resources_str}
    {shadow_str}
    wrapper:
        "{wrapper_url}"
"""
        
        logger.debug(f"Snakefile content:\n{snakefile_content}")

        # 创建临时Snakefile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smk', delete=False) as tmp_snakefile:
            tmp_snakefile.write(snakefile_content)
            snakefile_path = tmp_snakefile.name

        logger.debug(f"Generated temporary Snakefile at: {snakefile_path}")
        
        # 确定目标文件
        if outputs:
            if isinstance(outputs, dict):
                snakemake_target = list(outputs.values())[0]
            elif isinstance(outputs, list):
                snakemake_target = outputs[0]
            else:
                raise ValueError("'outputs' must be a dict or list.")
        else:
            raise ValueError("'outputs' must be provided for wrapper execution.")

        # 构建Snakemake命令
        command = [
            "snakemake", 
            "--snakefile", str(snakefile_path),
            snakemake_target,
            "--use-conda", 
            "--cores", str(threads),
            "--printshellcmds"
        ]
        
        # 添加额外参数
        if extra_snakemake_args:
            command.extend(extra_snakemake_args.split())
        
        logger.info(f"Executing command: {' '.join(command)}")
        
        # Set the working directory
        if workdir:
            cwd = workdir
        else:
            cwd = wrappers_path

        # 执行命令 - 使用绝对路径作为工作目录
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True,
            timeout=timeout,
            cwd=Path(cwd).resolve()
        )
        
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"Snakemake wrapper execution failed with exit code {e.returncode}"
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
        error_msg = f"Snakemake wrapper execution timed out after {timeout} seconds"
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
        # 清理临时文件
        if snakefile_path and os.path.exists(snakefile_path):
            try:
                os.remove(snakefile_path)
                logger.debug(f"Removed temporary Snakefile: {snakefile_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary Snakefile {snakefile_path}: {e}")
        if temp_conda_env_file and os.path.exists(temp_conda_env_file):
            try:
                os.remove(temp_conda_env_file)
                logger.debug(f"Removed temporary conda env file: {temp_conda_env_file}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary conda env file {temp_conda_env_file}: {e}")

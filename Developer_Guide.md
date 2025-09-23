# Developer Guide

   * 架构概述：
       * server.py：FastMCP 应用程序，定义 mcp.tool 端点。
       * wrapper_runner.py：执行单个 wrapper 的逻辑（动态 Snakefile 生成）。
       * workflow_runner.py：执行完整工作流的逻辑（配置修改、Snakemake 命令构建）。
   * 参数处理和流程：
       * 详细解释如何将 mcp.tool 调用中的参数传递给 wrapper_runner.py 和 workflow_runner.py。
       * `run_snakemake_wrapper`：
           * 生成一个带有单个 run_single_wrapper 规则的临时 Snakefile。
           * outputs 参数对于目标确定是强制性的。
           * conda_env 参数向生成的 Snakefile 添加 conda: 指令。
           * shadow 参数添加 shadow: 指令。
       * `run_snakemake_workflow`：
           * 根据 workflow_name 和 workflow_base_dir 定位工作流。
           * 加载原始 config.yaml。
           * 配置合并逻辑： 解释如何将 mcp.tool 调用中的 inputs、outputs、params 合并到临时 config.yaml 中（例如，params
             直接更新配置的根，inputs/outputs 作为顶级键添加）。这是一个关键细节，需要清晰的解释和潜在的注意事项。
           * target_rule 参数用于指定工作流中的特定规则。
           * 如何将 container、benchmark、resources、shadow、conda_env 转换为 Snakemake
             命令行参数（--container-image、--benchmark-file、--resources、--shadow-prefix、--conda-env）。
   * 错误处理：
       * runner 模块如何捕获 subprocess.CalledProcessError、subprocess.TimeoutExpired 和通用 Exception。
       * mcp.tool 如何通过抛出 fastmcp.exceptions.ToolError（如果未捕获 ToolError，则为通用 Exception）来传播错误。
   * 测试策略：
       * conftest.py 和共享 fixture（mcp_server、http_client、test_files、wrappers_path、workflow_base_dir）的解释。
       * 为什么 fixture 是 function 作用域以实现隔离。
       * 如何为 wrapper 和工作流添加新测试。
       * SNAKEMAKE_WRAPPERS_PATH 环境变量对测试的重要性。
       * test_conda_env.py 和 test_shadow_wrapper.py 如何专门测试参数传递和 Snakemake 指令生成。
       * test_workflow_execution.py 用于验证工作流执行和配置修改。
   * 未来考虑/已知限制：
       * 当前工作流的配置合并是一种简化（直接更新根 params、inputs、outputs）。对于复杂工作流可能需要更复杂的映射。
       * shadow 指令与 singularity 的交互（如 FileNotFoundError 中所示）如果是一个常见问题，可能需要注意或进一步调查。
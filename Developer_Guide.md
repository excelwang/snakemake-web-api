# Developer Guide

## 架构概述
   * server.py：CLI 应用程序，定义 `parse`, `rest`, `verify` 三个子命令入口点。
   * api/main.py：创建原生 FastAPI 应用程序，定义 REST API 路由。
   * api/routes/：包含不同的 API 路由实现 (health, demo, tools, tool_processes, workflow_processes)。
   * wrapper_runner.py：执行单个 wrapper 的逻辑（动态 Snakefile 生成）。
   * workflow_runner.py：执行完整工作流的逻辑（配置修改、Snakemake 命令构建）。
   * snakefile_parser.py：解析 Snakefile 以生成工具元数据和演示调用。
   * schemas.py：定义 Pydantic 模式，用于 API 请求和响应。

## 参数处理和流程
   * 详细解释 CLI 参数如何传递到 FastAPI 应用程序状态，并进一步传递给 wrapper_runner.py 和 workflow_runner.py。
   * `run_snakemake_wrapper`：
       * 生成一个带有单个 run_single_wrapper 规则的临时 Snakefile。
       * outputs 参数对于目标确定是可选的。
       * conda_env 参数向生成的 Snakefile 添加 conda: 指令。
       * shadow 参数添加 shadow: 指令。
       * 使用 `workdir` 参数指定工作目录，在其中创建临时 Snakefile 和执行命令。
   * `run_snakemake_workflow`：
       * 根据 workflow_name 和 workflows_dir 定位工作流。
       * 加载原始 config.yaml。
       * 配置合并逻辑： 解释如何将 API 调用中的 inputs、outputs、params 合并到临时 config.yaml 中（例如，params
         直接更新配置的根，inputs/outputs 作为顶级键添加）。这是一个关键细节，需要清晰的解释和潜在的注意事项。
       * target_rule 参数用于指定工作流中的特定规则。
       * 如何将 container、benchmark、resources、shadow 转换为 Snakemake
         命令行参数（--container-image、--benchmark-file、--resources、--shadow-prefix）。
   * **异步任务处理**：
       * 新增 JobStatus、JobSubmissionResponse 模式以支持异步任务处理。
       * 任务提交后返回 job_id 和 status_url 用于后续状态检查。
       * 实现了异步任务状态轮询机制。

## CLI 命令结构
   * `parse`: 解析 snakemake-wrappers 目录中的包装器，生成缓存元数据。
   * `rest`: 启动 FastAPI REST API 服务器。
   * `verify`: 验证安装和配置是否正确。

## API 路由详解
   * `health`: 健康检查端点
   * `demo`: 提供演示调用端点
   * `tools`: 工具列表和元数据端点
   * `tool_processes`: 异步 wrapper 执行端点
   * `workflow_processes`: 异步 workflow 执行端点

## 错误处理
   * runner 模块如何捕获 subprocess.CalledProcessError、subprocess.TimeoutExpired 和通用 Exception。
   * FastAPI 如何通过 HTTP 异常响应传播错误。
   * 异步任务如何在任务结果中记录错误信息。

## 测试策略
   * conftest.py 和共享 fixture（http_client、test_files、wrappers_path、workflows_dir）的解释。
   * 为什么 fixture 是 function 作用域以实现隔离。
   * 如何为 wrapper 和工作流添加新测试。
   * SNAKEMAKE_WRAPPERS_PATH 环境变量对测试的重要性。
   * test_conda_env.py 和 test_shadow_wrapper.py 如何专门测试参数传递和 Snakemake 指令生成。
   * test_workflow_execution.py 用于验证工作流执行和配置修改。

## 未来考虑/已知限制
   * 当前工作流的配置合并是一种简化（直接更新根 params、inputs、outputs）。对于复杂工作流可能需要更复杂的映射。
   * shadow 指令与 singularity 的交互（如 FileNotFoundError 中所示）如果是一个常见问题，可能需要注意或进一步调查。
   * 当前实现依赖于 SNAKEBASE_DIR 环境变量，可能需要更加灵活的配置选项。
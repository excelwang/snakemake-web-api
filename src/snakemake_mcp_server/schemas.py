from pydantic import BaseModel
from typing import Union, Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

# Define new Pydantic models for async job handling
class JobStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    job_id: str
    status: JobStatus
    created_time: datetime
    result: Optional[Dict] = None


class JobList(BaseModel):
    jobs: List[Job]


class JobSubmissionResponse(BaseModel):
    job_id: str
    status_url: str


# UserProvidedParams 用于请求和元数据存储（统一使用 inputs/outputs）
class UserProvidedParams(BaseModel):
    inputs: Optional[Union[Dict, List]] = None
    outputs: Optional[Union[Dict, List]] = None
    params: Optional[Union[Dict, List]] = None


# PlatformRunParams 用于请求和元数据存储（统一使用可选字段）
class PlatformRunParams(BaseModel):
    log: Optional[Union[Dict, List]] = None
    threads: Optional[int] = None
    resources: Optional[Dict] = None
    priority: Optional[int] = None
    shadow_depth: Optional[str] = None
    benchmark: Optional[str] = None
    container_img: Optional[str] = None
    env_modules: Optional[List[str]] = None
    group: Optional[str] = None


# Define Pydantic models for request/response
class InternalWrapperRequest(UserProvidedParams, PlatformRunParams):
    wrapper_id: str
    workdir: Optional[str] = None


class UserWrapperRequest(UserProvidedParams):
    wrapper_id: str


class InternalWorkflowRequest(UserProvidedParams, PlatformRunParams):
    workflow_id: str
    extra_snakemake_args: str = ""
    container: Optional[str] = None  # This is different from container_img
    shadow: Optional[str] = None
    target_rule: Optional[str] = None


class SnakemakeResponse(BaseModel):
    status: str
    stdout: str
    stderr: str
    exit_code: int
    error_message: Optional[str] = None


class DemoCall(BaseModel):
    method: str
    endpoint: str
    payload: UserWrapperRequest


# WrapperInfo 类字段
class WrapperInfo(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    authors: Optional[List[str]] = None
    notes: Optional[List[str]] = None


class WrapperMetadata(BaseModel):
    # ID 字段
    id: str

    # WrapperInfo 类字段
    info: WrapperInfo

    # UserProvidedParams 类字段
    user_params: UserProvidedParams

    # PlatformRunParams 类字段
    platform_params: PlatformRunParams


class WrapperMetadataResponse(BaseModel):
    # ID 字段
    id: str

    # WrapperInfo 类字段
    info: WrapperInfo

    # UserProvidedParams 类字段
    user_params: UserProvidedParams


class DemoCaseResponse(BaseModel):
    method: str
    endpoint: str
    payload: UserWrapperRequest
    curl_example: str


class ListWrappersResponse(BaseModel):
    wrappers: List[WrapperMetadataResponse]
    total_count: int

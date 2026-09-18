"""批量复核任务服务。

客户端一次提交多条采集参数，后端按提交顺序逐条复核（结论与把握程度
和单条入口走同一条分析流水线），并支持：

- 某一条参数超出允许范围时只跳过该条并指明哪一项不合格，其余照常复核；
- 任务进行中可查询整体进度；
- 中途失败后可从失败处续跑，已算完的部分不重复计算。

任务保存在内存中，与现有无状态服务保持一致，不引入外部存储。
"""

import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.models.schemas import (
    BatchItemResult,
    BatchItemStatus,
    BatchJobResponse,
    BatchJobStatus,
    BatchProgressResponse,
    ECGAnalysisParams,
    ECGAnalysisRequest,
)
from app.services import ecg_service

# 终态条目：已得出结论 / 已跳过 / 已失败
_TERMINAL_ITEM_STATUSES = (
    BatchItemStatus.COMPLETED,
    BatchItemStatus.SKIPPED,
    BatchItemStatus.FAILED,
)


class BatchJob:
    """一批采集参数的复核任务（内存态）。"""

    def __init__(self, items: List[ECGAnalysisParams]):
        self.batch_id = uuid.uuid4().hex
        self.items = list(items)
        self.results: List[BatchItemResult] = [
            BatchItemResult(index=i, status=BatchItemStatus.PENDING, params=item)
            for i, item in enumerate(self.items)
        ]
        self.status = BatchJobStatus.PENDING
        # 下一条待处理的条目序号；已算完的条目排在其前面，续跑时不会重复计算
        self.current_index = 0
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        self.updated_at = self.created_at
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None


def _format_validation_errors(exc: ValidationError) -> str:
    """把参数校验错误整理成可读说明，指明哪一项不合格。"""
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", ())) or "unknown"
        parts.append(f"参数 {field}={err.get('input')!r} 不合格（{err.get('msg')}）")
    return "；".join(parts)


def _process(job: BatchJob) -> None:
    """按提交顺序逐条复核，在后台线程中运行。"""
    with job.lock:
        job.status = BatchJobStatus.PROCESSING
        job.updated_at = datetime.now()

    for i in range(job.current_index, len(job.items)):
        params = job.items[i]
        with job.lock:
            job.current_index = i
            job.results[i].status = BatchItemStatus.PROCESSING
            job.updated_at = datetime.now()

        # 与单条入口完全相同的参数校验；超出允许范围只跳过本条
        try:
            request = ECGAnalysisRequest(**params.model_dump())
        except ValidationError as exc:
            with job.lock:
                job.results[i].status = BatchItemStatus.SKIPPED
                job.results[i].error = _format_validation_errors(exc)
                job.current_index = i + 1
                job.updated_at = datetime.now()
            continue

        # 与单条入口共用同一条分析流水线，保证整组结论与单条入口一致
        try:
            response = ecg_service.analyze_request(request)
        except Exception as exc:  # 中途失败：停在这一处，等待续跑
            with job.lock:
                job.results[i].status = BatchItemStatus.FAILED
                job.results[i].error = str(exc)
                job.status = BatchJobStatus.FAILED
                job.error = f"第 {i + 1} 条复核失败：{exc}"
                job.updated_at = datetime.now()
            return

        with job.lock:
            job.results[i].status = BatchItemStatus.COMPLETED
            job.results[i].result = response
            job.current_index = i + 1
            job.updated_at = datetime.now()

    with job.lock:
        job.status = BatchJobStatus.COMPLETED
        job.updated_at = datetime.now()


_JOBS: Dict[str, BatchJob] = {}
_STORE_LOCK = threading.Lock()


def _start(job: BatchJob) -> None:
    thread = threading.Thread(target=_process, args=(job,), daemon=True)
    job.thread = thread
    thread.start()


def create_batch(items: List[ECGAnalysisParams]) -> BatchJob:
    """创建批量复核任务并立即开始按顺序逐条复核。"""
    job = BatchJob(items)
    with _STORE_LOCK:
        _JOBS[job.batch_id] = job
    _start(job)
    return job


def get_batch(batch_id: str) -> Optional[BatchJob]:
    with _STORE_LOCK:
        return _JOBS.get(batch_id)


def resume_batch(batch_id: str) -> Optional[Tuple[BatchJob, bool]]:
    """
    从中途失败处接着跑。

    返回 (任务, 是否已重新启动)；任务不存在返回 None，
    任务不处于失败状态时第二个元素为 False（不重复启动）。
    """
    job = get_batch(batch_id)
    if job is None:
        return None
    with job.lock:
        if job.status != BatchJobStatus.FAILED:
            return job, False
        # 仅重置失败的那一条，已算完/已跳过的条目保持原样
        failed_item = job.results[job.current_index]
        failed_item.status = BatchItemStatus.PENDING
        failed_item.error = None
        job.status = BatchJobStatus.PENDING
        job.error = None
        job.updated_at = datetime.now()
    _start(job)
    return job, True


def _counts(job: BatchJob) -> Tuple[int, int, int, int]:
    completed = succeeded = skipped = failed = 0
    for r in job.results:
        if r.status in _TERMINAL_ITEM_STATUSES:
            completed += 1
        if r.status == BatchItemStatus.COMPLETED:
            succeeded += 1
        elif r.status == BatchItemStatus.SKIPPED:
            skipped += 1
        elif r.status == BatchItemStatus.FAILED:
            failed += 1
    return completed, succeeded, skipped, failed


def to_progress(job: BatchJob) -> BatchProgressResponse:
    """整体进度快照（不含各条结果内容）。"""
    with job.lock:
        completed, succeeded, skipped, failed = _counts(job)
        total = len(job.items)
        return BatchProgressResponse(
            batch_id=job.batch_id,
            status=job.status,
            total=total,
            completed=completed,
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            progress=(completed / total) if total else 1.0,
            current_index=job.current_index,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def to_response(job: BatchJob) -> BatchJobResponse:
    """整组结果快照：进度 + 各条结论（与单条入口返回内容一致）。"""
    progress = to_progress(job)
    with job.lock:
        results = list(job.results)
    return BatchJobResponse(**progress.model_dump(), results=results)

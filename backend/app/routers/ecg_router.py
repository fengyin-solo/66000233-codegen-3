from fastapi import APIRouter, HTTPException
from typing import List

from app.models.schemas import (
    LeadName,
    ECGAnalysisRequest,
    ECGAnalysisResponse,
    ECGBatchAnalyzeRequest,
    BatchJobResponse,
    BatchProgressResponse,
)
from app.services import batch_service
from app.services.ecg_service import analyze_request

router = APIRouter()


@router.get("/leads", response_model=List[str])
async def get_available_leads():
    """Get list of available ECG leads."""
    return [lead.value for lead in LeadName]


@router.post("/analyze", response_model=ECGAnalysisResponse)
async def analyze_ecg(request: ECGAnalysisRequest):
    """
    Generate and analyze ECG signal for a specified lead.

    Performs:
    1. PQRST waveform generation
    2. Pan-Tompkins R-peak detection
    3. HRV metrics calculation
    4. Arrhythmia detection and classification
    """
    return analyze_request(request)


@router.post("/batch/analyze", response_model=BatchJobResponse, status_code=202)
async def analyze_batch(request: ECGBatchAnalyzeRequest):
    """
    提交批量复核任务。

    一次提交多条采集参数，后端按提交顺序逐条复核（结论与把握程度与单条
    入口一致），立即返回任务句柄；处理过程中可查询整体进度，全部算完后
    通过查询接口整组取回结果。
    """
    job = batch_service.create_batch(request.items)
    return batch_service.to_response(job)


@router.get("/batch/{batch_id}", response_model=BatchJobResponse)
async def get_batch(batch_id: str):
    """
    查询批量复核整组状态与各条结果。

    每条结果的内容与单条入口 /ecg/analyze 的返回保持一致；
    参数超出允许范围的条目状态为 skipped 并指明哪一项不合格。
    """
    job = batch_service.get_batch(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"批量复核任务不存在: {batch_id}")
    return batch_service.to_response(job)


@router.get("/batch/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(batch_id: str):
    """查询批量复核整体进度（轻量接口，不含各条结果内容）。"""
    job = batch_service.get_batch(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"批量复核任务不存在: {batch_id}")
    return batch_service.to_progress(job)


@router.post("/batch/{batch_id}/resume", response_model=BatchJobResponse)
async def resume_batch(batch_id: str):
    """
    从中途失败处接着跑。

    仅失败状态的任务可续跑；已算完的部分不重复计算，
    从失败的那一条继续按顺序复核。
    """
    result = batch_service.resume_batch(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"批量复核任务不存在: {batch_id}")
    job, started = result
    if not started:
        raise HTTPException(status_code=409, detail="仅失败状态的批量复核任务可以续跑")
    return batch_service.to_response(job)

from fastapi import APIRouter, HTTPException, Query
from typing import List

from app.models.schemas import (
    LeadName,
    ECGLead,
    ECGAnalysisRequest,
    ECGAnalysisResponse,
    ECGAnalysisBatchRequest,
    ECGBatchTaskSnapshot,
    RPeak,
    HRVMetrics,
    ArrhythmiaEvent,
    ArrhythmiaType,
)
from app.services.ecg_service import perform_analysis
from app.services.batch_service import batch_task_manager

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
    analysis = perform_analysis(
        lead_name=request.lead_name.value,
        duration=request.duration,
        sampling_rate=request.sampling_rate,
        heart_rate=request.heart_rate,
    )
    ecg_signal = analysis["ecg_signal"]
    r_peaks_raw = analysis["r_peaks"]
    hrv_raw = analysis["hrv"]
    arrhythmia_raw = analysis["arrhythmia_events"]
    diagnosis = analysis["rhythm_diagnosis"]

    r_peaks = [
        RPeak(index=rp["index"], time=rp["time"], amplitude=rp["amplitude"])
        for rp in r_peaks_raw
    ]

    # Calculate HRV metrics
    hrv = HRVMetrics(**hrv_raw)

    # Detect arrhythmia events
    arrhythmia_events = []
    for evt in arrhythmia_raw:
        arrhythmia_events.append(
            ArrhythmiaEvent(
                event_type=ArrhythmiaType(evt["event_type"]),
                confidence=evt["confidence"],
                description=evt["description"],
                timestamp=evt["timestamp"],
            )
        )

    # Build lead data
    lead = ECGLead(
        lead_name=request.lead_name,
        sampling_rate=request.sampling_rate,
        duration=request.duration,
        samples=[round(float(s), 4) for s in ecg_signal],
        r_peaks=r_peaks,
    )

    return ECGAnalysisResponse(
        lead=lead,
        hrv=hrv,
        arrhythmia_events=arrhythmia_events,
        rhythm_diagnosis=diagnosis,
    )


@router.post("/batch/analyze", response_model=ECGBatchTaskSnapshot, status_code=202)
async def analyze_ecg_batch(request: ECGAnalysisBatchRequest):
    """
    Submit a batch review: multiple acquisition parameter sets in one request.

    Items are processed sequentially in submission order through the same
    pipeline as the single-analysis entry. An item whose parameters are out
    of the allowed range is skipped (with the reason recorded) while the
    rest are processed normally. Returns the task snapshot; poll
    GET /ecg/batch/{task_id} for overall progress and grouped results.
    """
    return batch_task_manager.create_task(request.items)


@router.get("/batch/{task_id}", response_model=ECGBatchTaskSnapshot)
async def get_batch_task(task_id: str):
    """Query overall progress and per-item results of a batch review task."""
    snapshot = batch_task_manager.get_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="批量任务不存在")
    return snapshot


@router.post("/batch/{task_id}/resume", response_model=ECGBatchTaskSnapshot)
async def resume_batch_task(task_id: str):
    """
    Resume a failed batch task from the interrupted item.

    Items already completed or skipped keep their results and are never
    recomputed; only the remaining items are processed.
    """
    snapshot = batch_task_manager.resume_task(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="批量任务不存在")
    return snapshot

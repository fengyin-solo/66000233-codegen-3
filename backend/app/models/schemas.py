from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum


class LeadName(str, Enum):
    I = "I"
    II = "II"
    III = "III"
    aVR = "aVR"
    aVL = "aVL"
    aVF = "aVF"
    V1 = "V1"
    V2 = "V2"
    V3 = "V3"
    V4 = "V4"
    V5 = "V5"
    V6 = "V6"


class ArrhythmiaType(str, Enum):
    NORMAL = "normal"
    TACHYCARDIA = "tachycardia"
    BRADYCARDIA = "bradycardia"
    ST_ELEVATION = "st_elevation"
    AFIB = "atrial_fibrillation"
    PVC = "premature_ventricular_contraction"


class RPeak(BaseModel):
    index: int = Field(..., description="Sample index of R-peak")
    time: float = Field(..., description="Time in seconds")
    amplitude: float = Field(..., description="Amplitude in mV")


class HRVMetrics(BaseModel):
    heart_rate: float = Field(..., description="Heart rate in BPM")
    sdnn: float = Field(..., description="Standard deviation of NN intervals (ms)")
    rmssd: float = Field(..., description="Root mean square of successive differences (ms)")
    pnn50: float = Field(..., description="Percentage of successive differences > 50ms")
    nn_intervals: List[float] = Field(default_factory=list, description="NN intervals in ms")


class ArrhythmiaEvent(BaseModel):
    event_type: ArrhythmiaType = Field(..., description="Type of arrhythmia detected")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    description: str = Field(..., description="Human-readable description")
    timestamp: float = Field(..., description="Event timestamp in seconds")


class ECGLead(BaseModel):
    lead_name: LeadName = Field(..., description="ECG lead name")
    sampling_rate: int = Field(default=500, description="Sampling rate in Hz")
    duration: float = Field(default=10.0, description="Duration in seconds")
    samples: List[float] = Field(default_factory=list, description="ECG samples in mV")
    r_peaks: List[RPeak] = Field(default_factory=list, description="Detected R-peaks")


class ECGAnalysisRequest(BaseModel):
    lead_name: LeadName = Field(default=LeadName.II, description="ECG lead to analyze")
    duration: float = Field(default=10.0, ge=1.0, le=60.0, description="Duration in seconds")
    sampling_rate: int = Field(default=500, ge=100, le=1000, description="Sampling rate in Hz")
    heart_rate: float = Field(default=72.0, ge=30, le=200, description="Simulated heart rate BPM")


class ECGAnalysisResponse(BaseModel):
    lead: ECGLead = Field(..., description="ECG lead data")
    hrv: HRVMetrics = Field(..., description="HRV analysis results")
    arrhythmia_events: List[ArrhythmiaEvent] = Field(default_factory=list, description="Detected arrhythmia events")
    rhythm_diagnosis: str = Field(..., description="Overall rhythm diagnosis")


# ---------- Batch review (批量复核) ----------


class BatchItemStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class BatchTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ECGAnalysisBatchRequest(BaseModel):
    """Batch review submission: multiple acquisition parameter sets in one request.

    Each item accepts the same fields as the single-analysis entry
    (lead_name / duration / sampling_rate / heart_rate) plus an optional
    client-side ``item_id`` label that is echoed back in the result.
    Items are validated individually with the exact same rules as the
    single entry, so one out-of-range item never rejects the whole batch.
    """

    items: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Acquisition parameter sets, processed in submission order",
        json_schema_extra={
            "example": {
                "items": [
                    {"item_id": "A-01", "lead_name": "II", "duration": 10, "sampling_rate": 500, "heart_rate": 72},
                    {"item_id": "A-02", "lead_name": "V4", "duration": 10, "sampling_rate": 500, "heart_rate": 130},
                ]
            }
        },
    )


class ECGBatchItemResult(BaseModel):
    """Per-item outcome of a batch review, aligned with the single entry."""

    index: int = Field(..., description="Position of the item in submission order (0-based)")
    item_id: Optional[str] = Field(default=None, description="Client-supplied label, echoed back if provided")
    status: BatchItemStatus = Field(..., description="Item processing status")
    conclusion: Optional[str] = Field(default=None, description="Rhythm diagnosis, same as the single entry's rhythm_diagnosis")
    confidence: Optional[float] = Field(default=None, description="Confidence of the conclusion (0-1)")
    hrv: Optional[HRVMetrics] = Field(default=None, description="HRV analysis results")
    arrhythmia_events: Optional[List[ArrhythmiaEvent]] = Field(default=None, description="Detected arrhythmia events")
    error: Optional[str] = Field(default=None, description="Why the item was skipped or failed")


class ECGBatchTaskSnapshot(BaseModel):
    """Overall progress and grouped results of a batch review task."""

    task_id: str = Field(..., description="Batch task identifier")
    status: BatchTaskStatus = Field(..., description="Overall task status")
    total: int = Field(..., description="Total number of submitted items")
    processed: int = Field(..., description="Items finished so far (completed + skipped + failed)")
    progress: float = Field(..., ge=0, le=1, description="Overall progress ratio (0-1)")
    results: List[ECGBatchItemResult] = Field(default_factory=list, description="Per-item results in submission order")
    error: Optional[str] = Field(default=None, description="Task-level error when status is failed")
    created_at: str = Field(..., description="Task creation time (ISO 8601)")
    updated_at: str = Field(..., description="Last update time (ISO 8601)")

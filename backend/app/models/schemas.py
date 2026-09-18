from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


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


# ---------------------------------------------------------------------------
# 批量复核 (Batch Review)
# ---------------------------------------------------------------------------


class BatchItemStatus(str, Enum):
    """批量复核中单条条目的状态。"""

    PENDING = "pending"          # 等待复核
    PROCESSING = "processing"    # 复核中
    COMPLETED = "completed"      # 已得出结论与把握程度
    SKIPPED = "skipped"          # 参数超出允许范围，已跳过
    FAILED = "failed"            # 复核过程中途失败（可续跑）


class BatchJobStatus(str, Enum):
    """批量复核整组任务的状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"      # 全部条目均已处理（含被跳过的条目）
    FAILED = "failed"            # 中途失败，可从失败处续跑


class ECGAnalysisParams(BaseModel):
    """
    批量复核中单条采集参数。

    字段与单条入口 ECGAnalysisRequest 相同，但提交整组时不做范围校验——
    逐条复核时按单条入口同样的规则校验，超出允许范围的条目只跳过该条，
    不影响其余各条。
    """

    lead_name: str = Field(default="II", description="ECG lead to analyze")
    duration: float = Field(default=10.0, description="Duration in seconds")
    sampling_rate: int = Field(default=500, description="Sampling rate in Hz")
    heart_rate: float = Field(default=72.0, description="Simulated heart rate BPM")


class ECGBatchAnalyzeRequest(BaseModel):
    """批量复核请求：一次提交多条采集参数，后端按提交顺序逐条复核。"""

    items: List[ECGAnalysisParams] = Field(
        ..., min_length=1, description="采集参数列表，按提交顺序逐条复核"
    )


class BatchItemResult(BaseModel):
    """批量复核中单条条目的结果。"""

    index: int = Field(..., description="条目在提交列表中的序号（从 0 开始）")
    status: BatchItemStatus = Field(..., description="条目状态")
    params: ECGAnalysisParams = Field(..., description="该条提交的采集参数")
    result: Optional[ECGAnalysisResponse] = Field(
        default=None, description="复核结论与把握程度，内容与单条入口返回一致"
    )
    error: Optional[str] = Field(
        default=None, description="跳过或失败原因（指明哪一项不合格）"
    )


class BatchProgressResponse(BaseModel):
    """批量复核整体进度（轻量，不含各条结果内容）。"""

    batch_id: str = Field(..., description="批量任务 ID")
    status: BatchJobStatus = Field(..., description="整组任务状态")
    total: int = Field(..., description="条目总数")
    completed: int = Field(..., description="已处理条数（含跳过与失败）")
    succeeded: int = Field(..., description="复核成功条数")
    skipped: int = Field(..., description="因参数不合格被跳过的条数")
    failed: int = Field(..., description="复核失败条数")
    progress: float = Field(..., ge=0, le=1, description="整体进度 0~1")
    current_index: int = Field(..., description="当前待处理/处理中的条目序号")
    error: Optional[str] = Field(default=None, description="整组失败原因")
    created_at: datetime = Field(..., description="任务创建时间")
    updated_at: datetime = Field(..., description="最近更新时间")


class BatchJobResponse(BatchProgressResponse):
    """批量复核整组结果：进度 + 各条结论（与单条入口内容一致）。"""

    results: List[BatchItemResult] = Field(
        default_factory=list, description="各条复核结果，按提交顺序排列"
    )

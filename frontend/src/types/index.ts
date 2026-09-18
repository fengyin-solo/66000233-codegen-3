export interface ECGLead {
  leadName: string;
  samplingRate: number;
  duration: number;
  samples: number[];
  rPeaks: RPeak[];
}

export interface RPeak {
  index: number;
  time: number;
  amplitude: number;
}

export interface HRVData {
  heartRate: number;
  sdnn: number;
  rmssd: number;
  pnn50: number;
  nnIntervals: number[];
}

export interface ArrhythmiaEvent {
  eventType: 'normal' | 'tachycardia' | 'bradycardia' | 'st_elevation' | 'atrial_fibrillation' | 'premature_ventricular_contraction';
  confidence: number;
  description: string;
  timestamp: number;
}

export interface ECGAnalysisResponse {
  lead: ECGLead;
  hrv: HRVData;
  arrhythmiaEvents: ArrhythmiaEvent[];
  rhythmDiagnosis: string;
}

export interface ECGAnalysisRequest {
  leadName: string;
  duration: number;
  samplingRate: number;
  heartRate: number;
}

export const LEAD_NAMES: string[] = [
  'I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'
];

// ---------------------------------------------------------------------------
// 批量复核（与后端批量接口的返回结构一致，字段保持 snake_case）
// ---------------------------------------------------------------------------

export type BatchItemStatus = 'pending' | 'processing' | 'completed' | 'skipped' | 'failed';
export type BatchJobStatus = 'pending' | 'processing' | 'completed' | 'failed';

/** 批量复核中单条采集参数（提交时不做范围校验，由后端逐条复核） */
export interface BatchParams {
  lead_name: string;
  duration: number;
  sampling_rate: number;
  heart_rate: number;
}

/** 后端单条分析返回（与 /ecg/analyze 的返回内容一致） */
export interface BackendAnalysisResult {
  lead: {
    lead_name: string;
    sampling_rate: number;
    duration: number;
    samples: number[];
    r_peaks: RPeak[];
  };
  hrv: {
    heart_rate: number;
    sdnn: number;
    rmssd: number;
    pnn50: number;
    nn_intervals: number[];
  };
  arrhythmia_events: {
    event_type: string;
    confidence: number;
    description: string;
    timestamp: number;
  }[];
  rhythm_diagnosis: string;
}

export interface BatchItemResult {
  index: number;
  status: BatchItemStatus;
  params: BatchParams;
  result: BackendAnalysisResult | null;
  error: string | null;
}

export interface BatchProgress {
  batch_id: string;
  status: BatchJobStatus;
  total: number;
  completed: number;
  succeeded: number;
  skipped: number;
  failed: number;
  progress: number;
  current_index: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface BatchJob extends BatchProgress {
  results: BatchItemResult[];
}

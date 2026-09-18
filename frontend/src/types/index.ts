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

// ---------- Batch review (批量复核) ----------

export type BatchItemStatus = 'pending' | 'processing' | 'completed' | 'skipped' | 'failed';
export type BatchTaskStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface BatchItemResult {
  index: number;
  itemId: string | null;
  status: BatchItemStatus;
  conclusion: string | null;
  confidence: number | null;
  hrv: HRVData | null;
  arrhythmiaEvents: ArrhythmiaEvent[] | null;
  error: string | null;
}

export interface BatchTaskSnapshot {
  taskId: string;
  status: BatchTaskStatus;
  total: number;
  processed: number;
  progress: number;
  results: BatchItemResult[];
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

/** One editable parameter row in the batch review form */
export interface BatchParamRow {
  itemId: string;
  leadName: string;
  duration: number;
  samplingRate: number;
  heartRate: number;
}

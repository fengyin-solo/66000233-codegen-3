"""Batch review (批量复核) task management.

Clients submit multiple acquisition parameter sets at once; the service
processes them sequentially in submission order through the exact same
validation rules and analysis pipeline as the single-analysis entry.

Semantics:
- An item whose parameters fall outside the allowed range is skipped with
  a reason; all other items are still processed.
- Overall progress can be queried at any time while the task runs.
- If processing is interrupted by an unexpected error, the task is marked
  failed and can be resumed from the interrupted item — items already
  completed or skipped are never recomputed.
"""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from app.models.schemas import ECGAnalysisRequest
from app.services.ecg_service import perform_analysis

# Item statuses considered final: never recomputed on resume
_FINAL_ITEM_STATUSES = ("completed", "skipped")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BatchTaskManager:
    """In-memory manager for batch ECG review tasks."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ---------- public API ----------

    def create_task(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a batch task and start processing in the background."""
        task_id = uuid.uuid4().hex[:12]
        now = _utc_now()
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "items": list(items),
                "results": [self._new_result(i, item) for i, item in enumerate(items)],
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        self._start_worker(task_id)
        return self.get_snapshot(task_id)

    def get_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return the current snapshot of a task, or None if unknown."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return self._snapshot_locked(task)

    def resume_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Resume a failed task from the interrupted item.

        Completed and skipped items keep their results; only pending/failed
        items are (re)processed. Returns the current snapshot, or None if
        the task is unknown.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if task["status"] != "failed":
                # Already running or finished — nothing to resume
                return self._snapshot_locked(task)
            for result in task["results"]:
                if result["status"] == "failed":
                    result["status"] = "pending"
                    result["error"] = None
            task["error"] = None
            task["status"] = "pending"
            task["updated_at"] = _utc_now()
        self._start_worker(task_id)
        return self.get_snapshot(task_id)

    # ---------- internals ----------

    def _start_worker(self, task_id: str) -> None:
        thread = threading.Thread(target=self._run, args=(task_id,), daemon=True)
        thread.start()

    def _run(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = "running"
            task["updated_at"] = _utc_now()
            items = list(task["items"])

        for index, item in enumerate(items):
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                result = task["results"][index]
                if result["status"] in _FINAL_ITEM_STATUSES:
                    continue  # already done — never recompute
                result["status"] = "processing"
                task["updated_at"] = _utc_now()

            # Validate with the same rules as the single-analysis entry;
            # an out-of-range item is skipped without affecting the others.
            try:
                request = self._validate_item(item)
            except ValueError as exc:
                with self._lock:
                    result["status"] = "skipped"
                    result["error"] = str(exc)
                    task["updated_at"] = _utc_now()
                continue

            try:
                analysis = perform_analysis(
                    lead_name=request.lead_name.value,
                    duration=request.duration,
                    sampling_rate=request.sampling_rate,
                    heart_rate=request.heart_rate,
                )
            except Exception as exc:  # unexpected failure — halt, resumable
                with self._lock:
                    result["status"] = "failed"
                    result["error"] = f"分析过程出错: {exc}"
                    task["status"] = "failed"
                    task["error"] = f"第 {index + 1} 条处理失败: {exc}"
                    task["updated_at"] = _utc_now()
                return

            events = analysis["arrhythmia_events"]
            confidence = max((e["confidence"] for e in events), default=0.0)
            with self._lock:
                result["status"] = "completed"
                result["conclusion"] = analysis["rhythm_diagnosis"]
                result["confidence"] = confidence
                result["hrv"] = analysis["hrv"]
                result["arrhythmia_events"] = events
                result["error"] = None
                task["updated_at"] = _utc_now()

        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and task["status"] == "running":
                task["status"] = "completed"
                task["updated_at"] = _utc_now()

    @staticmethod
    def _new_result(index: int, item: Any) -> Dict[str, Any]:
        item_id = None
        if isinstance(item, dict) and item.get("item_id") is not None:
            item_id = str(item["item_id"])
        return {
            "index": index,
            "item_id": item_id,
            "status": "pending",
            "conclusion": None,
            "confidence": None,
            "hrv": None,
            "arrhythmia_events": None,
            "error": None,
        }

    @staticmethod
    def _validate_item(item: Any) -> ECGAnalysisRequest:
        """Validate one item with the same rules as the single entry."""
        if not isinstance(item, dict):
            raise ValueError("参数必须是键值对对象")
        try:
            return ECGAnalysisRequest(**item)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
            raise ValueError(f"参数超出允许范围 — {details}")

    @staticmethod
    def _snapshot_locked(task: Dict[str, Any]) -> Dict[str, Any]:
        results = [dict(r) for r in task["results"]]
        total = len(results)
        processed = sum(
            1 for r in results if r["status"] in _FINAL_ITEM_STATUSES + ("failed",)
        )
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "total": total,
            "processed": processed,
            "progress": round(processed / total, 4) if total else 0.0,
            "results": results,
            "error": task["error"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
        }


# Shared singleton used by the router
batch_task_manager = BatchTaskManager()

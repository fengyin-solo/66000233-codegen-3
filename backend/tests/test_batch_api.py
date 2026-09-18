"""批量复核接口测试。

覆盖：
- 单条入口行为保持不变；
- 批量提交按顺序逐条复核并整组返回；
- 超出允许范围的条目只跳过该条并指明不合格项；
- 整组结论与单条入口一致（相同参数相同结果）；
- 进行中可查询整体进度；
- 中途失败可续跑，已算完的部分不重复计算。
"""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ecg_service

client = TestClient(app)

VALID_ITEM = {"lead_name": "II", "duration": 5.0, "sampling_rate": 500, "heart_rate": 72.0}
SINGLE_KEYS = {"lead", "hrv", "arrhythmia_events", "rhythm_diagnosis"}


def submit_batch(items):
    resp = client.post("/ecg/batch/analyze", json={"items": items})
    assert resp.status_code == 202, resp.text
    return resp.json()


def wait_for_job(batch_id, timeout=30.0):
    """轮询直至任务进入终态，返回整组结果。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/ecg/batch/{batch_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"任务 {batch_id} 未在 {timeout}s 内结束")


# ---------------------------------------------------------------------------
# 单条入口保持不变
# ---------------------------------------------------------------------------


def test_single_entry_unchanged():
    resp = client.post("/ecg/analyze", json=VALID_ITEM)
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == SINGLE_KEYS
    assert data["lead"]["lead_name"] == "II"
    assert isinstance(data["rhythm_diagnosis"], str)
    assert data["arrhythmia_events"], "应至少给出一条结论事件"
    assert 0.0 <= data["arrhythmia_events"][0]["confidence"] <= 1.0


def test_single_entry_rejects_out_of_range():
    resp = client.post("/ecg/analyze", json={**VALID_ITEM, "heart_rate": 250})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 批量提交：按顺序逐条复核并整组返回
# ---------------------------------------------------------------------------


def test_batch_analyze_in_order():
    items = [
        {**VALID_ITEM, "heart_rate": 60.0},
        {**VALID_ITEM, "lead_name": "V1", "heart_rate": 80.0},
        {**VALID_ITEM, "lead_name": "aVF", "heart_rate": 110.0},
    ]
    job = submit_batch(items)
    assert job["status"] in ("pending", "processing", "completed")
    assert job["total"] == 3

    final = wait_for_job(job["batch_id"])
    assert final["status"] == "completed"
    assert final["completed"] == 3
    assert final["succeeded"] == 3
    assert final["progress"] == 1.0

    # 按提交顺序逐条返回，每条内容与单条入口结构一致
    for i, item in enumerate(items):
        r = final["results"][i]
        assert r["index"] == i
        assert r["status"] == "completed"
        assert r["params"]["lead_name"] == item["lead_name"]
        assert r["params"]["heart_rate"] == item["heart_rate"]
        assert set(r["result"].keys()) == SINGLE_KEYS
        assert r["result"]["lead"]["lead_name"] == item["lead_name"]
        assert r["error"] is None


# ---------------------------------------------------------------------------
# 超出允许范围：只跳过该条并指明不合格项，其余照常
# ---------------------------------------------------------------------------


def test_batch_skips_out_of_range_items():
    items = [
        VALID_ITEM,
        {**VALID_ITEM, "heart_rate": 250.0},     # 心率超出允许范围
        {**VALID_ITEM, "sampling_rate": 50},     # 采样率超出允许范围
        {**VALID_ITEM, "lead_name": "XX"},       # 导联名不合格
        {**VALID_ITEM, "lead_name": "V3"},
    ]
    job = submit_batch(items)
    final = wait_for_job(job["batch_id"])

    assert final["status"] == "completed"
    assert final["succeeded"] == 2
    assert final["skipped"] == 3

    statuses = [r["status"] for r in final["results"]]
    assert statuses == ["completed", "skipped", "skipped", "skipped", "completed"]

    # 每条被跳过的都指明哪一项不合格
    assert "heart_rate" in final["results"][1]["error"]
    assert "sampling_rate" in final["results"][2]["error"]
    assert "lead_name" in final["results"][3]["error"]
    for i in (1, 2, 3):
        assert final["results"][i]["result"] is None

    # 其余各条照常给出结论与把握程度
    for i in (0, 4):
        assert final["results"][i]["result"]["rhythm_diagnosis"]
        assert final["results"][i]["result"]["arrhythmia_events"]


# ---------------------------------------------------------------------------
# 整组结论与单条入口保持一致
# ---------------------------------------------------------------------------


def test_batch_result_matches_single_entry():
    np.random.seed(20260918)
    single = client.post("/ecg/analyze", json=VALID_ITEM).json()

    np.random.seed(20260918)
    job = submit_batch([VALID_ITEM])
    final = wait_for_job(job["batch_id"])

    batch_result = final["results"][0]["result"]
    assert batch_result == single


# ---------------------------------------------------------------------------
# 进行中可查询整体进度
# ---------------------------------------------------------------------------


def test_progress_observable_while_running(monkeypatch):
    real_analyze = ecg_service.analyze_request

    def slow_analyze(request):
        time.sleep(0.15)
        return real_analyze(request)

    monkeypatch.setattr(ecg_service, "analyze_request", slow_analyze)

    job = submit_batch([VALID_ITEM] * 4)
    batch_id = job["batch_id"]

    snapshots = []
    deadline = time.time() + 30
    while time.time() < deadline:
        resp = client.get(f"/ecg/batch/{batch_id}/progress")
        assert resp.status_code == 200
        data = resp.json()
        snapshots.append(data)
        if data["status"] in ("completed", "failed"):
            break
        time.sleep(0.02)

    assert snapshots[-1]["status"] == "completed"
    # 任务进行中能查到整体进度，且进度单调推进
    in_flight = [s for s in snapshots if s["status"] in ("pending", "processing")]
    assert in_flight, "应能观察到进行中的状态"
    assert any(s["completed"] < s["total"] for s in in_flight)
    completed_seq = [s["completed"] for s in snapshots]
    assert completed_seq == sorted(completed_seq)
    # 轻量进度接口不含各条结果内容
    assert "results" not in snapshots[0]


# ---------------------------------------------------------------------------
# 中途失败可续跑，已算完的部分不重复计算
# ---------------------------------------------------------------------------


def test_resume_after_failure_without_recompute(monkeypatch):
    real_analyze = ecg_service.analyze_request
    calls = []

    def flaky_analyze(request):
        calls.append(request.heart_rate)
        if request.heart_rate == 80.0:
            raise RuntimeError("模拟分析中途失败")
        return real_analyze(request)

    monkeypatch.setattr(ecg_service, "analyze_request", flaky_analyze)

    items = [
        {**VALID_ITEM, "heart_rate": 60.0},
        {**VALID_ITEM, "heart_rate": 80.0},
        {**VALID_ITEM, "heart_rate": 100.0},
    ]
    job = submit_batch(items)
    batch_id = job["batch_id"]
    final = wait_for_job(batch_id)

    # 停在中途失败处
    assert final["status"] == "failed"
    assert "第 2 条" in final["error"]
    statuses = [r["status"] for r in final["results"]]
    assert statuses == ["completed", "failed", "pending"]
    assert calls == [60.0, 80.0]
    first_result = final["results"][0]["result"]
    assert first_result is not None

    # 修复故障后从失败处续跑
    monkeypatch.setattr(ecg_service, "analyze_request", real_analyze)
    resp = client.post(f"/ecg/batch/{batch_id}/resume")
    assert resp.status_code == 200, resp.text

    resumed = wait_for_job(batch_id)
    assert resumed["status"] == "completed"
    assert resumed["succeeded"] == 3
    assert [r["status"] for r in resumed["results"]] == ["completed"] * 3

    # 已算完的第 1 条没有重复计算，结果原样保留
    assert calls == [60.0, 80.0]
    assert resumed["results"][0]["result"] == first_result


def test_resume_only_for_failed_job():
    job = submit_batch([VALID_ITEM])
    batch_id = job["batch_id"]
    final = wait_for_job(batch_id)
    assert final["status"] == "completed"

    resp = client.post(f"/ecg/batch/{batch_id}/resume")
    assert resp.status_code == 409

    resp = client.post("/ecg/batch/does-not-exist/resume")
    assert resp.status_code == 404
    resp = client.get("/ecg/batch/does-not-exist")
    assert resp.status_code == 404
    resp = client.get("/ecg/batch/does-not-exist/progress")
    assert resp.status_code == 404

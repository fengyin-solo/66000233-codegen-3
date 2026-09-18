# 心电 ECG 实时监测与心律失常检测系统

一个基于 Vue 3 + FastAPI 的心电图 (ECG) 实时监测与心律失常检测系统，支持 12 导联心电信号模拟、Pan-Tompkins R 峰值检测、心率变异性 (HRV) 分析及心律失常自动检测。

## 功能特性

### 心电信号生成
- 基于高斯函数的 PQRST 波形形态模拟，生成逼真的 12 导联心电图信号
- 支持 I, II, III, aVR, aVL, aVF, V1-V6 全部 12 导联
- 可调节心率 (30-180 BPM) 和记录时长 (5-30s)
- 包含基线漂移和高频噪声模拟真实采集环境

### R 峰值检测
- 采用 Pan-Tompkins 算法进行 QRS 波群检测
- 带通滤波 (5-15 Hz) → 微分 → 平方 → 滑动窗口积分 → 自适应阈值
- 准确的 R 峰值定位与标注

### 心率变异性分析 (HRV)
- 心率 (HR) 实时计算
- SDNN：所有 NN 间期的标准差
- RMSSD：相邻 NN 间期差值的均方根
- pNN50：相邻 RR 差值 > 50ms 的百分比
- RR 间期图 (Tachogram) 可视化

### 心律失常检测
- 心动过速检测 (HR > 100 BPM)
- 心动过缓检测 (HR < 60 BPM)
- ST 段抬高检测（提示心肌梗死可能）
- 心律不规则检测（疑似房颤）
- 置信度评分与中文诊断描述

### 批量复核
- 客户端一次提交多条采集参数，后端按提交顺序逐条算出结论与把握程度并整组返回
- 某一条参数超出允许范围时只跳过该条并指明哪一项不合格，其余各条照常给出结果
- 任务进行中可查询整体进度；中途失败可从失败处续跑，已算完的部分不重复计算
- 每条结果与单条入口 `/ecg/analyze` 的返回内容保持一致

批量复核接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/ecg/batch/analyze` | 提交批量复核任务（202 返回任务句柄） |
| GET | `/ecg/batch/{batch_id}` | 查询整组状态与各条结果 |
| GET | `/ecg/batch/{batch_id}/progress` | 查询整体进度（轻量） |
| POST | `/ecg/batch/{batch_id}/resume` | 从中途失败处续跑 |

前端侧边栏"功能视图"切换到"批量复核"即可一次录入多条参数提交复核（需勾选"使用后端 API"）。

## 技术栈

### 前端
- Vue 3 + TypeScript + Vite
- Pinia 状态管理
- ECharts + vue-echarts 数据可视化
- Tailwind CSS 样式
- Axios HTTP 客户端

### 后端
- Python FastAPI
- NumPy 数值计算
- SciPy 信号处理
- Pydantic 数据模型

## 快速开始

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端默认在 `http://localhost:5173` 运行，可通过侧边栏"使用后端 API"开关连接后端分析服务。

<template>
  <div class="space-y-4">
    <!-- 参数提交区 -->
    <div class="bg-gray-900/60 rounded-lg border border-gray-800 p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-semibold text-cyan-400">批量复核</h3>
        <span class="text-xs text-gray-500">一次提交多条采集参数，后端按提交顺序逐条复核</span>
      </div>

      <!-- 参数行 -->
      <div class="space-y-2">
        <div class="grid grid-cols-12 gap-2 text-xs text-gray-500 px-1">
          <span class="col-span-1">#</span>
          <span class="col-span-2">导联</span>
          <span class="col-span-3">时长 (s)</span>
          <span class="col-span-3">采样率 (Hz)</span>
          <span class="col-span-2">心率 (BPM)</span>
          <span class="col-span-1"></span>
        </div>
        <div
          v-for="(row, idx) in rows"
          :key="idx"
          class="grid grid-cols-12 gap-2 items-center"
        >
          <span class="col-span-1 text-xs text-gray-500 text-center">{{ idx + 1 }}</span>
          <select
            v-model="row.lead_name"
            :disabled="isRunning"
            class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 outline-none"
          >
            <option v-for="lead in leadNames" :key="lead" :value="lead">{{ lead }}</option>
          </select>
          <input
            v-model.number="row.duration"
            type="number"
            step="1"
            :disabled="isRunning"
            class="col-span-3 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 outline-none"
            placeholder="1 ~ 60"
          />
          <input
            v-model.number="row.sampling_rate"
            type="number"
            step="50"
            :disabled="isRunning"
            class="col-span-3 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 outline-none"
            placeholder="100 ~ 1000"
          />
          <input
            v-model.number="row.heart_rate"
            type="number"
            step="1"
            :disabled="isRunning"
            class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 outline-none"
            placeholder="30 ~ 200"
          />
          <button
            @click="removeRow(idx)"
            :disabled="isRunning || rows.length <= 1"
            class="col-span-1 text-gray-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed text-sm"
            title="删除该条"
          >
            ✕
          </button>
        </div>
      </div>

      <div class="flex items-center gap-2 mt-4">
        <button
          @click="addRow"
          :disabled="isRunning"
          class="px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 text-gray-300 border border-gray-700 hover:border-gray-500 transition-all disabled:opacity-40"
        >
          + 添加一条
        </button>
        <button
          @click="submit"
          :disabled="!canSubmit"
          :class="[
            'px-4 py-2 rounded-lg text-xs font-medium transition-all',
            canSubmit
              ? 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/20'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed',
          ]"
        >
          {{ store.batchSubmitting ? '提交中...' : `提交批量复核 (${rows.length} 条)` }}
        </button>
        <button
          v-if="store.batchJob"
          @click="resetAll"
          :disabled="isRunning"
          class="px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-500 transition-all disabled:opacity-40"
        >
          清空重填
        </button>
      </div>

      <p v-if="!store.useBackend" class="mt-3 text-xs text-amber-400/90">
        批量复核由后端服务执行，请先在侧边栏勾选"使用后端 API"。
      </p>
      <p v-if="store.batchError" class="mt-3 text-xs text-red-400">{{ store.batchError }}</p>
    </div>

    <!-- 整体进度 -->
    <div v-if="store.batchJob" class="bg-gray-900/60 rounded-lg border border-gray-800 p-4">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <h4 class="text-sm font-semibold text-gray-300">整体进度</h4>
          <span
            :class="[
              'px-2 py-0.5 rounded text-xs font-medium',
              statusBadgeClass(store.batchJob.status),
            ]"
          >
            {{ statusLabel(store.batchJob.status) }}
          </span>
        </div>
        <span class="text-xs text-gray-500">
          已处理 {{ store.batchJob.completed }} / {{ store.batchJob.total }}
          （成功 {{ store.batchJob.succeeded }} · 跳过 {{ store.batchJob.skipped }} · 失败 {{ store.batchJob.failed }}）
        </span>
      </div>

      <div class="h-2 rounded-full bg-gray-800 overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-300"
          :class="store.batchJob.status === 'failed' ? 'bg-red-500' : 'bg-cyan-500'"
          :style="{ width: (store.batchJob.progress * 100).toFixed(0) + '%' }"
        />
      </div>

      <div
        v-if="store.batchJob.status === 'failed'"
        class="mt-3 flex items-center justify-between bg-red-900/20 border border-red-700/40 rounded-lg px-3 py-2"
      >
        <span class="text-xs text-red-300">{{ store.batchJob.error }}</span>
        <button
          @click="store.resumeBatch()"
          class="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-500 text-white transition-all shrink-0 ml-3"
        >
          从失败处续跑
        </button>
      </div>
    </div>

    <!-- 逐条结果 -->
    <div v-if="store.batchJob" class="bg-gray-900/60 rounded-lg border border-gray-800 p-4">
      <h4 class="text-sm font-semibold text-gray-300 mb-3">逐条结论</h4>
      <div class="space-y-2">
        <div
          v-for="item in store.batchJob.results"
          :key="item.index"
          class="flex items-start gap-3 p-3 rounded-lg border text-sm"
          :class="itemRowClass(item.status)"
        >
          <span class="text-xs text-gray-500 w-6 pt-0.5 shrink-0">#{{ item.index + 1 }}</span>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-xs text-gray-400">
                {{ item.params.lead_name }} · {{ item.params.duration }}s ·
                {{ item.params.sampling_rate }}Hz · {{ item.params.heart_rate }}BPM
              </span>
              <span
                :class="['px-1.5 py-0.5 rounded text-xs', statusBadgeClass(item.status)]"
              >
                {{ statusLabel(item.status) }}
              </span>
            </div>

            <!-- 结论与把握程度 -->
            <template v-if="item.status === 'completed' && item.result">
              <p class="mt-1 text-xs text-gray-200">{{ item.result.rhythm_diagnosis }}</p>
              <p class="mt-0.5 text-xs text-gray-500">
                把握程度: {{ (confidenceOf(item.result) * 100).toFixed(0) }}%
                <span class="mx-1">·</span>
                HR {{ item.result.hrv.heart_rate.toFixed(0) }} BPM
                <span class="mx-1">·</span>
                SDNN {{ item.result.hrv.sdnn.toFixed(1) }} ms
              </p>
            </template>
            <p v-else-if="item.error" class="mt-1 text-xs opacity-90">{{ item.error }}</p>
            <p v-else-if="item.status === 'pending'" class="mt-1 text-xs text-gray-600">等待复核</p>
            <p v-else-if="item.status === 'processing'" class="mt-1 text-xs text-cyan-300/80">复核中...</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useECGStore } from '../store/ecg';
import { LEAD_NAMES } from '../types';
import type { BatchParams, BackendAnalysisResult } from '../types';

const store = useECGStore();
const leadNames = LEAD_NAMES;

const defaultRow = (): BatchParams => ({
  lead_name: 'II',
  duration: 10,
  sampling_rate: 500,
  heart_rate: 72,
});

const rows = ref<BatchParams[]>([defaultRow()]);

const isRunning = computed(
  () => store.batchJob?.status === 'pending' || store.batchJob?.status === 'processing'
);

const canSubmit = computed(
  () => store.useBackend && !store.batchSubmitting && !isRunning.value && rows.value.length > 0
);

function addRow() {
  rows.value.push(defaultRow());
}

function removeRow(idx: number) {
  if (rows.value.length > 1) {
    rows.value.splice(idx, 1);
  }
}

async function submit() {
  try {
    await store.submitBatch(rows.value.map((r) => ({ ...r })));
  } catch {
    // 错误信息已展示在 store.batchError
  }
}

function resetAll() {
  store.clearBatch();
  rows.value = [defaultRow()];
}

/** 把握程度：取该条结论事件中最高置信度 */
function confidenceOf(result: BackendAnalysisResult): number {
  if (!result.arrhythmia_events.length) return 0;
  return Math.max(...result.arrhythmia_events.map((e) => e.confidence));
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    processing: '复核中',
    completed: '已完成',
    skipped: '已跳过',
    failed: '已失败',
  };
  return labels[status] || status;
}

function statusBadgeClass(status: string): string {
  const classes: Record<string, string> = {
    pending: 'bg-gray-700/60 text-gray-400',
    processing: 'bg-cyan-900/50 text-cyan-300',
    completed: 'bg-emerald-900/50 text-emerald-300',
    skipped: 'bg-amber-900/50 text-amber-300',
    failed: 'bg-red-900/50 text-red-300',
  };
  return classes[status] || 'bg-gray-700/60 text-gray-400';
}

function itemRowClass(status: string): string {
  const classes: Record<string, string> = {
    pending: 'bg-gray-900/40 border-gray-800 text-gray-400',
    processing: 'bg-cyan-900/10 border-cyan-700/30 text-gray-300',
    completed: 'bg-emerald-900/10 border-emerald-700/30 text-gray-300',
    skipped: 'bg-amber-900/10 border-amber-700/30 text-amber-200',
    failed: 'bg-red-900/10 border-red-700/30 text-red-200',
  };
  return classes[status] || 'bg-gray-900/40 border-gray-800 text-gray-400';
}
</script>

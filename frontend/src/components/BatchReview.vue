<template>
  <div class="bg-gray-900/60 rounded-lg border border-gray-800 p-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-lg font-semibold text-cyan-400">批量复核</h3>
      <span v-if="batchTask" class="text-xs text-gray-500">任务 {{ batchTask.taskId }}</span>
    </div>

    <p v-if="!store.useBackend" class="text-xs text-yellow-500/80 bg-yellow-900/20 border border-yellow-700/30 rounded px-3 py-2 mb-3">
      批量复核需要连接后端服务，请在侧栏勾选"使用后端 API"。
    </p>

    <!-- Parameter rows editor -->
    <div class="space-y-2 mb-3">
      <div class="grid grid-cols-12 gap-2 text-xs text-gray-500 px-1">
        <span class="col-span-2">编号</span>
        <span class="col-span-2">导联</span>
        <span class="col-span-3">心率 (BPM)</span>
        <span class="col-span-2">时长 (s)</span>
        <span class="col-span-2">采样率 (Hz)</span>
        <span class="col-span-1" />
      </div>
      <div
        v-for="(row, idx) in rows"
        :key="idx"
        class="grid grid-cols-12 gap-2 items-center"
      >
        <input
          v-model="row.itemId"
          placeholder="可选"
          class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
        />
        <select
          v-model="row.leadName"
          class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
        >
          <option v-for="lead in leadNames" :key="lead" :value="lead">{{ lead }}</option>
        </select>
        <input
          v-model.number="row.heartRate"
          type="number"
          class="col-span-3 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
        />
        <input
          v-model.number="row.duration"
          type="number"
          class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
        />
        <input
          v-model.number="row.samplingRate"
          type="number"
          class="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
        />
        <button
          @click="removeRow(idx)"
          :disabled="rows.length <= 1"
          class="col-span-1 text-gray-500 hover:text-red-400 text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          title="删除该行"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- Action buttons -->
    <div class="flex gap-2 mb-3">
      <button
        @click="addRow"
        class="px-3 py-1.5 rounded text-xs font-medium bg-gray-800 text-gray-300 border border-gray-700 hover:border-gray-500 transition-all"
      >
        + 添加一条
      </button>
      <button
        @click="submit"
        :disabled="!store.useBackend || store.isBatchSubmitting || rows.length === 0 || isRunning"
        :class="[
          'px-4 py-1.5 rounded text-xs font-medium transition-all',
          !store.useBackend || store.isBatchSubmitting || rows.length === 0 || isRunning
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/20',
        ]"
      >
        {{ isRunning ? '复核中...' : '提交批量复核' }}
      </button>
      <button
        v-if="batchTask"
        @click="store.clearBatchReview()"
        class="px-3 py-1.5 rounded text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-500 transition-all"
      >
        清空结果
      </button>
    </div>

    <p v-if="store.batchError" class="text-xs text-red-400 mb-3">{{ store.batchError }}</p>

    <!-- Progress -->
    <div v-if="batchTask" class="mb-3">
      <div class="flex items-center justify-between text-xs text-gray-400 mb-1">
        <span>
          整体进度: {{ batchTask.processed }} / {{ batchTask.total }}
          <span :class="statusTextClass(batchTask.status)" class="ml-2 font-medium">{{ statusLabel(batchTask.status) }}</span>
        </span>
        <span>{{ (batchTask.progress * 100).toFixed(0) }}%</span>
      </div>
      <div class="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          :class="['h-full transition-all duration-300', batchTask.status === 'failed' ? 'bg-red-500' : 'bg-cyan-500']"
          :style="{ width: `${batchTask.progress * 100}%` }"
        />
      </div>
      <p v-if="batchTask.error" class="text-xs text-red-400 mt-1">{{ batchTask.error }}</p>
      <button
        v-if="batchTask.status === 'failed'"
        @click="store.resumeBatchReview()"
        class="mt-2 px-4 py-1.5 rounded text-xs font-medium bg-amber-600 hover:bg-amber-500 text-white transition-all shadow-lg shadow-amber-600/20"
      >
        从失败处继续
      </button>
    </div>

    <!-- Grouped results -->
    <div v-if="batchTask && batchTask.results.length > 0" class="space-y-1.5 max-h-72 overflow-y-auto">
      <div
        v-for="item in batchTask.results"
        :key="item.index"
        :class="[
          'px-3 py-2 rounded-lg border text-xs',
          item.status === 'completed'
            ? 'bg-emerald-900/20 border-emerald-700/30'
            : item.status === 'skipped'
            ? 'bg-yellow-900/20 border-yellow-700/30'
            : item.status === 'failed'
            ? 'bg-red-900/20 border-red-700/30'
            : 'bg-gray-800/40 border-gray-700/40',
        ]"
      >
        <div class="flex items-center justify-between">
          <span class="text-gray-300 font-medium">
            #{{ item.index + 1 }}<span v-if="item.itemId" class="text-gray-500"> ({{ item.itemId }})</span>
          </span>
          <span :class="statusTextClass(item.status)" class="font-medium">{{ statusLabel(item.status) }}</span>
        </div>
        <p v-if="item.status === 'completed'" class="mt-1 text-gray-300">
          {{ item.conclusion }}
          <span class="text-gray-500 ml-1">| 把握程度: {{ ((item.confidence ?? 0) * 100).toFixed(0) }}%</span>
        </p>
        <p v-else-if="item.error" class="mt-1 text-yellow-300/90">{{ item.error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useECGStore } from '../store/ecg';
import { LEAD_NAMES } from '../types';
import type { BatchParamRow } from '../types';

const store = useECGStore();
const leadNames = LEAD_NAMES;

const batchTask = computed(() => store.batchTask);
const isRunning = computed(
  () => batchTask.value?.status === 'running' || batchTask.value?.status === 'pending'
);

function defaultRow(): BatchParamRow {
  return {
    itemId: '',
    leadName: store.selectedLead,
    duration: store.duration,
    samplingRate: store.samplingRate,
    heartRate: store.heartRate,
  };
}

const rows = ref<BatchParamRow[]>([defaultRow(), defaultRow()]);

function addRow() {
  rows.value.push(defaultRow());
}

function removeRow(idx: number) {
  if (rows.value.length > 1) {
    rows.value.splice(idx, 1);
  }
}

function submit() {
  store.submitBatchReview(rows.value.map((r) => ({ ...r })));
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    processing: '计算中',
    running: '复核中',
    completed: '已完成',
    skipped: '已跳过',
    failed: '失败',
  };
  return labels[status] || status;
}

function statusTextClass(status: string): string {
  const classes: Record<string, string> = {
    pending: 'text-gray-400',
    processing: 'text-cyan-300',
    running: 'text-cyan-300',
    completed: 'text-emerald-400',
    skipped: 'text-yellow-400',
    failed: 'text-red-400',
  };
  return classes[status] || 'text-gray-400';
}
</script>

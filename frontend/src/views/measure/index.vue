<template>
  <section class="page" data-module="measure">
    <header class="page-head">
      <div>
        <h2>电气测试管理</h2>
        <p class="page-desc">维护测试单，围绕测试单号、测试项目、测试设备、测试值做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记测试单</button>
        <button class="btn" type="button" @click="exportRows">导出电气测试清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无电气测试数据，可先登记测试单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条电气测试记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card" role="dialog" aria-modal="true" aria-label="测试单详情">
        <header class="modal-head">
          <h3>测试单详情 · {{ detail['测试单号'] }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <div v-for="column in detailColumns" :key="column" class="detail-item">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </div>
        </dl>
        <p class="detail-note">结论由服务端按测试值与标准范围统一判定，列表与详情始终一致。</p>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stats = { waiting: number; passed: number; failed: number; judged: number; pass_rate: number }

const ENDPOINT = '/api/measure'
const columns = ["测试单号", "测试项目", "测试设备", "测试值", "标准范围", "测试结论", "测试人员", "测试状态"]
const detailColumns = columns
const actions = ["开始测试", "判定合格", "判定不合格"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const detail = ref<Row | null>(null)
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
// 统计值全部来自服务端 /stats，页面不按表格行自行另算合格率
const stats = ref([
  { label: '待测试单据', value: 0 },
  { label: '测试合格率', value: '0.0%' },
  { label: '不合格项数', value: 0 },
])

function applyStats(payload: Stats) {
  stats.value = [
    { label: '待测试单据', value: payload.waiting },
    { label: '测试合格率', value: `${(payload.pass_rate * 100).toFixed(1)}%` },
    { label: '不合格项数', value: payload.failed },
  ]
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '测试单登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  // 详情直接取服务端单条结果，与列表走同一份判定，避免两处各算一遍
  errorMessage.value = ''
  infoMessage.value = ''
  void request(`${ENDPOINT}/${row.id}`)
    .then(async (response) => {
      if (!response.ok) {
        throw new Error('测试单详情读取失败')
      }
      detail.value = await response.json()
    })
    .catch((error: unknown) => {
      errorMessage.value = error instanceof Error ? error.message : '测试单详情读取失败'
    })
}

function closeDetail() {
  detail.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null) as { message?: string } | null
    if (!response.ok || !payload) {
      throw new Error(payload?.message || '电气测试动作未生效，请稍后重试')
    }
    // 页面结论与服务端不一致时，服务端已纠偏，这里把说明透给操作人
    infoMessage.value = payload.message || `测试单已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电气测试操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  infoMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('测试单列表读取失败')
    }
    if (!statsResponse.ok) {
      throw new Error('测试统计读取失败')
    }
    const listPayload = await listResponse.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    applyStats(await statsResponse.json() as Stats)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电气测试列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.info-text { color: #176b3a; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}

.modal-card {
  width: min(720px, 92vw);
  max-height: 86vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.22);
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.modal-head h3 { margin: 0; font-size: 16px; }

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
  margin: 0;
}

.detail-item { margin: 0; }

.detail-item dt {
  font-size: 12px;
  color: #667085;
  margin-bottom: 2px;
}

.detail-item dd { margin: 0; font-size: 14px; word-break: break-all; }

.detail-note {
  margin: 16px 0 0;
  font-size: 12px;
  color: #667085;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}
</style>

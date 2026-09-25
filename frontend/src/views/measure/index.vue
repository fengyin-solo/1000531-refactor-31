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
            <button
              v-if="row['测试状态'] !== '合格'"
              class="link"
              type="button"
              @click="runAction('开始测试', row)"
            >
              开始测试
            </button>
            <button class="link" type="button" @click="openDetail(row)">详情/判定</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无电气测试数据，可先登记测试单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条电气测试记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="drawer-mask" @click="closeDetail">
      <aside class="drawer" @click.stop>
        <h3>测试单详情</h3>
        <dl class="detail-grid">
          <template v-for="field in readonlyFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>
        <label class="detail-item">
          <span>测试值</span>
          <input v-model="detailForm['测试值']" placeholder="录入本次测试值" />
        </label>
        <label class="detail-item">
          <span>标准范围</span>
          <input v-model="detailForm['标准范围']" placeholder="如 10.2~11.4、≥2、≤10" />
        </label>
        <label class="detail-item">
          <span>测试人员</span>
          <input v-model="detailForm['测试人员']" placeholder="录入测试人员" />
        </label>
        <p class="detail-conclusion">测试结论：{{ detail['测试结论'] || '—' }}</p>
        <p v-if="detail['结论说明']" class="notice-text">{{ detail['结论说明'] }}</p>
        <p v-if="detailMessage" class="notice-text">{{ detailMessage }}</p>
        <div class="drawer-actions">
          <button class="btn primary" type="button" @click="submitJudge('判定合格')">判定合格</button>
          <button class="btn" type="button" @click="submitJudge('判定不合格')">判定不合格</button>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatItem = { label: string; value: string | number }

const ENDPOINT = '/api/measure'
const columns = ["测试单号", "测试项目", "测试设备", "测试值", "标准范围", "测试结论", "测试人员", "测试状态"]
const readonlyFields = ["测试单号", "测试项目", "测试设备", "测试状态"]
const judgeFields = ["测试值", "标准范围", "测试人员"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref<StatItem[]>([
  { label: '待测试单据', value: '—' },
  { label: '测试合格率', value: '—' },
  { label: '不合格项数', value: '—' },
])
const detail = ref<Row | null>(null)
const detailForm = ref<Record<string, string>>({})
const detailMessage = ref('')

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

async function readResult(response: Response, fallback: string) {
  const payload = (await response.json()) as { ok?: boolean; message?: string; entry?: Row }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message || fallback)
  }
  return payload
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    await readResult(response, '电气测试动作未生效，请稍后重试')
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电气测试操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  detailMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    const payload = (await response.json()) as Row
    detail.value = payload
    detailForm.value = Object.fromEntries(
      judgeFields.map((field) => [field, String(payload[field] ?? '')]),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '测试单详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailMessage.value = ''
}

async function submitJudge(action: string) {
  if (!detail.value) {
    return
  }
  detailMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...detailForm.value } }),
    })
    const payload = await readResult(response, '电气测试动作未生效，请稍后重试')
    // 结论以服务端返回为准；页面判定与服务端不一致时，说明随 message 一并展示
    detailMessage.value = payload.message ?? ''
    if (payload.entry) {
      detail.value = payload.entry
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    detailMessage.value = error instanceof Error ? error.message : '电气测试操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('电气测试统计读取失败')
    }
    const payload = (await response.json()) as { items?: StatItem[] }
    stats.value = payload.items ?? stats.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电气测试统计读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('测试单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '电气测试列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: 360px;
  max-width: 90vw;
  height: 100%;
  background: #fff;
  padding: 16px;
  overflow-y: auto;
  box-shadow: -4px 0 12px rgba(15, 23, 42, 0.12);
}
.detail-grid {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 6px 10px;
  font-size: 13px;
  margin: 0 0 12px;
}
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.detail-item { display: block; margin-bottom: 10px; font-size: 13px; }
.detail-item span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 2px; }
.detail-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.detail-conclusion { font-size: 13px; margin: 12px 0 4px; }
.notice-text { color: #b42318; font-size: 12px; margin: 4px 0; }
.drawer-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>

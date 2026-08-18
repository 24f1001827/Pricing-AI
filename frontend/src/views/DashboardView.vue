<template>
  <div class="page">
    <AppNav />

    <div class="content">
      <div class="page-header">
        <div>
          <p class="section-kicker">Workspace overview</p>
          <h1>Good {{ timeOfDay }}, {{ firstName }}</h1>
          <p class="subtitle">Here's what's happening with your business</p>
        </div>
        <n-button type="primary" size="large" :loading="isTraining" @click="startTraining">
          <n-icon><SparklesOutline /></n-icon> Train model
        </n-button>
      </div>

      <n-alert v-if="error" type="error" closable @close="error = null" style="margin-bottom: 20px">
        {{ error }}
      </n-alert>

      <n-alert v-if="retrainSuggestion?.should_retrain" type="warning" style="margin-bottom: 20px">
        <template #header>Retraining Recommended</template>
        Reasons: {{ retrainSuggestion.triggers.join(', ') }}
        <n-button size="small" type="warning" style="margin-left: 12px" @click="startTraining">Retrain Now</n-button>
      </n-alert>

      <!-- Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon products"><n-icon><CubeOutline /></n-icon></div>
          <div>
            <p class="stat-label">Products</p>
            <p class="stat-value">{{ summary?.products?.length || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon orders"><n-icon><ReceiptOutline /></n-icon></div>
          <div>
            <p class="stat-label">Transactions</p>
            <p class="stat-value">{{ summary?.total_records?.toLocaleString() || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon revenue"><n-icon><TrendingUpOutline /></n-icon></div>
          <div>
            <p class="stat-label">Total Revenue</p>
            <p class="stat-value">${{ summary?.total_revenue?.toLocaleString() || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon range"><n-icon><CalendarOutline /></n-icon></div>
          <div>
            <p class="stat-label">Date Range</p>
            <p class="stat-value" style="font-size: 14px">{{ dateRange }}</p>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <!-- Training Jobs -->
        <div class="card">
          <div class="card-header">
            <h3>Training Jobs</h3>
            <n-tag :type="latestJob?.status === 'completed' ? 'success' : latestJob?.status === 'training' ? 'warning' : 'default'" size="small">
              {{ latestJob?.status || 'No jobs' }}
            </n-tag>
          </div>
          <div v-if="trainingJobs.length === 0" class="empty-state">
            <p>No training jobs yet</p>
            <p class="muted">Add data and train your first model</p>
          </div>
          <div v-else class="job-list">
            <div v-for="job in trainingJobs.slice(0, 5)" :key="job.unique_id" class="job-item">
              <div>
                <p class="job-id">{{ job.unique_id.slice(0, 12) }}...</p>
                <p class="job-meta">{{ formatDate(job.created_at) }} · {{ job.trigger }}</p>
              </div>
              <div class="job-actions">
                <n-tag :type="statusType(job.status)" size="small">{{ job.status }}</n-tag>
                <n-button
                  v-if="job.status === 'completed'"
                  size="tiny"
                  type="primary"
                  @click="router.push({ name: 'predictions', params: { uniqueId: job.unique_id } })"
                >
                  View
                </n-button>
                <n-button
                  v-if="job.status === 'training'"
                  size="tiny"
                  @click="router.push({ name: 'training', params: { uniqueId: job.unique_id } })"
                >
                  Progress
                </n-button>
              </div>
            </div>
          </div>
        </div>

        <!-- Quick Actions -->
        <div class="card">
          <h3 class="card-title">Quick Actions</h3>
          <div class="action-list">
            <div class="action-item" @click="router.push('/products')">
              <div class="action-icon"><n-icon><CubeOutline /></n-icon></div>
              <div>
                <p class="action-title">Manage Products</p>
                <p class="action-desc">Add or update your product catalog</p>
              </div>
              <span class="action-arrow">→</span>
            </div>
            <div class="action-item" @click="router.push('/orders')">
              <div class="action-icon"><n-icon><BarChartOutline /></n-icon></div>
              <div>
                <p class="action-title">Log Sales Data</p>
                <p class="action-desc">Record transactions or import from CSV</p>
              </div>
              <span class="action-arrow">→</span>
            </div>
            <div class="action-item" v-if="latestJob?.status === 'completed'" @click="router.push({ name: 'predictions', params: { uniqueId: latestJob.unique_id } })">
              <div class="action-icon"><n-icon><AnalyticsOutline /></n-icon></div>
              <div>
                <p class="action-title">View Latest Predictions</p>
                <p class="action-desc">See pricing recommendations</p>
              </div>
              <span class="action-arrow">→</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSalesStore } from '@/stores/sales'
import { useTrainingStore } from '@/stores/training'
import { NButton, NAlert, NIcon, NTag } from 'naive-ui'
import { AnalyticsOutline, BarChartOutline, CalendarOutline, CubeOutline, ReceiptOutline, SparklesOutline, TrendingUpOutline } from '@vicons/ionicons5'
import AppNav from '@/components/AppNav.vue'
import api from '@/services/api'

const router = useRouter()
const authStore = useAuthStore()
const salesStore = useSalesStore()
const trainingStore = useTrainingStore()

const summary = ref(null)
const trainingJobs = ref([])
const retrainSuggestion = ref(null)
const isTraining = ref(false)
const error = ref(null)

const firstName = computed(() => authStore.user?.name?.split(' ')[0] || '')
const latestJob = computed(() => trainingJobs.value[0] || null)
const dateRange = computed(() => {
  if (!summary.value?.date_range) return 'No data'
  return `${summary.value.date_range.start} → ${summary.value.date_range.end}`
})
const timeOfDay = computed(() => {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
})

function statusType(status) {
  return { completed: 'success', training: 'warning', failed: 'error', pending: 'default' }[status] || 'default'
}

function formatDate(dt) {
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  await authStore.fetchUser()
  summary.value = await salesStore.fetchSummary()
  trainingJobs.value = await trainingStore.fetchHistory()
  try {
    const res = await api.get('/training/should-retrain')
    retrainSuggestion.value = res.data
  } catch {
    // Retraining advice is optional; the dashboard remains usable without it.
    retrainSuggestion.value = null
  }
})

async function startTraining() {
  isTraining.value = true
  error.value = null
  try {
    const job = await trainingStore.startTraining()
    router.push({ name: 'training', params: { uniqueId: job.unique_id } })
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to start training'
    isTraining.value = false
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
.page-header h1 { font-size: 26px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.section-kicker { margin: 0 0 7px; color: var(--primary); font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }

.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.stat-icon.products { background: #e7f5ef; color: #16735a; }.stat-icon.orders { background: #eaf3f5; color: #326c79; }.stat-icon.revenue { background: #fbf3e1; color: #a0691a; }.stat-icon.range { background: #f5ebee; color: #a84d5b; }
.stat-label { font-size: 12px; color: var(--text-muted); margin: 0 0 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.card-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.card-title { font-size: 15px; font-weight: 600; margin: 0 0 16px; }

.job-list { display: flex; flex-direction: column; gap: 12px; }
.job-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border); }
.job-item:last-child { border-bottom: none; }
.job-id { font-size: 13px; font-family: monospace; color: var(--text-primary); margin: 0 0 2px; }
.job-meta { font-size: 11px; color: var(--text-muted); margin: 0; }
.job-actions { display: flex; align-items: center; gap: 8px; }

.action-list { display: flex; flex-direction: column; gap: 4px; }
.action-item { display: flex; align-items: center; gap: 14px; padding: 12px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s; }
.action-item:hover { background: var(--surface-2); }
.action-icon { color: var(--primary); font-size: 18px; width: 36px; height: 36px; background: var(--primary-light); border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.action-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin: 0 0 2px; }
.action-desc { font-size: 12px; color: var(--text-muted); margin: 0; }
.action-arrow { margin-left: auto; color: var(--text-muted); font-size: 16px; }

.empty-state { text-align: center; padding: 32px 0; color: var(--text-secondary); font-size: 14px; }
.muted { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
</style>

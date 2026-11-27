<template>
  <div class="page">
    <AppNav />

    <div class="content">
      <div class="page-header">
        <div>
          <p class="section-kicker">Model Training</p>
          <h1>Training Run</h1>
          <p class="subtitle">Job ID: <code>{{ uniqueId }}</code></p>
        </div>
        <n-button @click="router.push({ name: 'dashboard' })">Back to Dashboard</n-button>
      </div>

      <div class="training-card">
        <div v-if="status === 'training' || status === 'pending'" class="training-progress">
          <div class="spinner"></div>
          <h3>{{ status === 'pending' ? 'Queued for training...' : 'Training in progress...' }}</h3>
          <p>Profiling daily demand, benchmarking models, and computing optimal prices &amp; stock alerts.</p>
          <p class="hint">This usually finishes within a few seconds.</p>
        </div>

        <div v-if="status === 'completed'" class="training-complete">
          <div class="status-badge success">Completed</div>
          <h3>Training Complete</h3>
          <p v-if="jobData?.model_name" class="model-info">
            Best Model: <strong>{{ jobData.model_name }}</strong>
          </p>
          <div v-if="jobData?.metrics" class="metrics-row">
            <div class="metric-chip"><span>R²</span><strong>{{ jobData.metrics.r2 }}</strong></div>
            <div class="metric-chip"><span>RMSE</span><strong>{{ jobData.metrics.rmse }}</strong></div>
            <div class="metric-chip"><span>MAE</span><strong>{{ jobData.metrics.mae }}</strong></div>
          </div>
          <n-button
            type="primary"
            size="large"
            style="margin-top: 24px"
            @click="router.push({ name: 'predictions', params: { uniqueId } })"
          >
            View Predictions &amp; Inventory
          </n-button>
        </div>

        <div v-if="status === 'failed'" class="training-failed">
          <div class="status-badge error">Failed</div>
          <h3>Training Failed</h3>
          <p class="error-detail">{{ jobData?.error_message || 'Check your order data and try starting a new training run.' }}</p>
          <div style="display: flex; justify-content: center; gap: 12px; margin-top: 24px">
            <n-button @click="router.push({ name: 'orders' })">View Orders</n-button>
            <n-button type="primary" @click="router.push({ name: 'dashboard' })">Back to Dashboard</n-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTrainingStore } from '@/stores/training'
import { NButton } from 'naive-ui'
import AppNav from '@/components/AppNav.vue'

const router = useRouter()
const route = useRoute()
const trainingStore = useTrainingStore()

const uniqueId = route.params.uniqueId
const status = ref('pending')
const jobData = ref(null)
let pollInterval = null

onMounted(() => {
  pollStatus()
  pollInterval = setInterval(pollStatus, 2500)
})

onUnmounted(() => {
  clearInterval(pollInterval)
})

async function pollStatus() {
  try {
    const result = await trainingStore.getStatus(uniqueId)
    jobData.value = result
    status.value = result.status
    if (status.value === 'completed' || status.value === 'failed') {
      clearInterval(pollInterval)
    }
  } catch (error) {
    console.error('Failed to fetch training status', error)
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 760px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.section-kicker { margin: 0 0 7px; color: var(--primary); font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.subtitle { color: var(--text-secondary); font-size: 13px; margin: 0; }
code { background: var(--primary-light); color: var(--primary); padding: 2px 6px; border-radius: 4px; font-size: 12px; }

.training-card { background: var(--surface); border: 1px solid var(--border); padding: 48px 36px; border-radius: var(--radius-md); text-align: center; }
.spinner { width: 48px; height: 48px; border: 4px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 24px; }
@keyframes spin { to { transform: rotate(360deg); } }

.status-badge { display: inline-block; padding: 5px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; margin-bottom: 14px; }
.status-badge.success { background: #e7f5ef; color: #16735a; }
.status-badge.error { background: #fdecec; color: #c2414c; }

.model-info { color: var(--text-secondary); margin: 8px 0 16px; }
.metrics-row { display: flex; justify-content: center; gap: 16px; margin-top: 12px; }
.metric-chip { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 18px; }
.metric-chip span { display: block; font-size: 11px; color: var(--text-muted); text-transform: uppercase; }
.metric-chip strong { font-size: 16px; color: var(--text-primary); }
.hint { color: var(--text-muted); font-size: 13px; margin-top: 8px; }
.error-detail { color: #c2414c; background: #fdecec; border-radius: var(--radius-sm); padding: 12px 16px; font-size: 13px; margin-top: 12px; }
</style>

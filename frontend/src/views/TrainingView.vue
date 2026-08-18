<template>
  <div class="training-page">
    <nav class="navbar">
      <h1>Pricing Platform</h1>
      <button @click="router.push({ name: 'dashboard' })">Back to Dashboard</button>
    </nav>

    <div class="content">
      <h2>Model Training</h2>

      <div class="training-card">
        <div v-if="status === 'training'" class="training-progress">
          <div class="spinner"></div>
          <h3>Training in progress...</h3>
          <p>Our AI agent is analyzing your data and training a model.</p>
          <p class="hint">This may take a few minutes.</p>
        </div>

        <div v-if="status === 'completed'" class="training-complete">
          <div class="success-icon">✅</div>
          <h3>Training Complete</h3>
          <p>Your pricing model is ready.</p>
          <button
            @click="router.push({ name: 'predictions', params: { uniqueId } })"
            class="primary-btn"
          >
            View Predictions
          </button>
        </div>

        <div v-if="status === 'failed'" class="training-failed">
          <div class="error-icon">❌</div>
          <h3>Training Failed</h3>
          <p>Something went wrong. Check your order data and start a new training run.</p>
          <button @click="router.push({ name: 'orders' })" class="primary-btn">
            View Orders
          </button>
        </div>

        <div v-if="status === 'pending'" class="training-pending">
          <h3>Waiting to start...</h3>
          <p>Your training job is queued.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTrainingStore } from '@/stores/training'

const router = useRouter()
const route = useRoute()
const trainingStore = useTrainingStore()

const uniqueId = route.params.uniqueId
const status = ref('training')
let pollInterval = null

onMounted(() => {
  pollStatus()
  pollInterval = setInterval(pollStatus, 5000)
})

onUnmounted(() => {
  clearInterval(pollInterval)
})

async function pollStatus() {
  try {
    const result = await trainingStore.getTrainingStatus(uniqueId)
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
.training-page { min-height: 100vh; background: #f5f5f5; }

.navbar {
  background: white;
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.content { padding: 32px; max-width: 600px; margin: 0 auto; }

.training-card {
  background: white;
  padding: 48px;
  border-radius: 12px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f0f0f0;
  border-top-color: #4285f4;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 24px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.success-icon, .error-icon { font-size: 48px; margin-bottom: 16px; }

.hint { color: #999; font-size: 14px; }

.primary-btn {
  background: #4285f4;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 24px;
}
</style>

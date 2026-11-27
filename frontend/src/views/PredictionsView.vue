<template>
  <div class="page">
    <AppNav />
    <div class="content">
      <div class="page-header">
        <div>
          <h1>Pricing Intelligence</h1>
          <p class="subtitle">AI-powered price, demand, and inventory recommendations</p>
        </div>
        <n-tag :type="objectiveType" size="medium">
          Optimizing: {{ predictions?.optimization_objective || 'revenue' }}
        </n-tag>
      </div>

      <div v-if="loading" class="loading-state">
        <n-spin size="large" />
        <p>Loading predictions...</p>
      </div>

      <n-alert v-else-if="error" type="error">{{ error }}</n-alert>

      <template v-else-if="predictions">
        <n-alert v-if="notice" type="success" closable @close="notice = null" style="margin-bottom: 16px">
          {{ notice }}
        </n-alert>

        <!-- Overall Metrics -->
        <div class="stats-grid" style="margin-bottom: 24px">
          <div class="stat-card highlight">
            <p class="stat-label">{{ predictions.product_results?.length > 1 ? 'Avg Optimal Price' : 'Optimal Price' }}</p>
            <p class="stat-value">${{ predictions.optimal_price }}</p>
          </div>
          <div class="stat-card">
            <p class="stat-label">Predicted Daily Demand</p>
            <p class="stat-value">{{ predictions.predicted_demand }} units</p>
          </div>
          <div class="stat-card">
            <p class="stat-label">Expected Daily Revenue</p>
            <p class="stat-value">${{ predictions.expected_revenue?.toLocaleString() }}</p>
          </div>
          <div class="stat-card">
            <p class="stat-label">Products Analyzed</p>
            <p class="stat-value">{{ predictions.product_results?.length || 0 }}</p>
          </div>
        </div>

        <!-- Model Strategy & Metrics -->
        <div v-if="predictions.model_summary?.model_name" class="card" style="margin-bottom: 20px">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap">
            <div style="flex: 1; min-width: 260px">
              <h3 style="margin: 0 0 6px">Model Strategy: {{ predictions.model_summary.model_name }}</h3>
              <p style="font-size: 13px; color: var(--text-secondary); margin: 0">
                {{ predictions.model_summary.strategy_explanation }}
              </p>
            </div>
            <div class="metrics-strip" v-if="predictions.model_summary.metrics">
              <div class="mini-metric"><span>R²</span><strong>{{ predictions.model_summary.metrics.r2 }}</strong></div>
              <div class="mini-metric"><span>RMSE</span><strong>{{ predictions.model_summary.metrics.rmse }}</strong></div>
              <div class="mini-metric"><span>MAE</span><strong>{{ predictions.model_summary.metrics.mae }}</strong></div>
            </div>
          </div>
        </div>

        <!-- Demand Forecast -->
        <div class="card" style="margin-bottom: 20px">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
            <div>
              <h3 style="margin: 0 0 4px">Demand Forecast</h3>
              <p style="font-size: 13px; color: var(--text-muted); margin: 0">Predicted units to be sold (calendar-aware)</p>
            </div>
            <n-radio-group v-model:value="forecastPeriod" size="small">
              <n-radio-button value="day1">Tomorrow</n-radio-button>
              <n-radio-button value="day7">Next 7 Days</n-radio-button>
              <n-radio-button value="day30">Next 30 Days</n-radio-button>
            </n-radio-group>
          </div>

          <div class="product-forecast-grid">
            <div
              v-for="product in predictions.product_results"
              :key="product.product"
              class="forecast-card"
            >
              <div class="forecast-product">{{ product.product_name || product.product }}</div>
              <div class="forecast-value">{{ product.forecast?.[forecastPeriod]?.toFixed(0) || '—' }} units</div>
              <div class="forecast-label">{{ forecastLabel }}</div>
            </div>
            <div v-if="predictions.demand_forecast?.total" class="forecast-card total">
              <div class="forecast-product">Portfolio Total</div>
              <div class="forecast-value">{{ predictions.demand_forecast.total?.[forecastPeriod]?.toFixed(0) || '—' }} units</div>
              <div class="forecast-label">{{ forecastLabel }}</div>
            </div>
          </div>
        </div>

        <!-- Per-Product Pricing -->
        <div class="card" style="margin-bottom: 20px">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
            <h3 style="margin: 0">Per-Product Recommendations</h3>
            <n-select
              v-if="predictions.product_results?.length"
              v-model:value="selectedProduct"
              :options="productOptions"
              size="small"
              style="width: 220px"
            />
          </div>

          <n-data-table
            :columns="productColumns"
            :data="predictions.product_results || []"
            :bordered="false"
            :striped="true"
          />
        </div>

        <!-- Price Curve Chart -->
        <div class="card" style="margin-bottom: 20px">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
            <div>
              <h3 style="margin: 0 0 4px">Price vs Revenue Curve</h3>
              <p style="font-size: 13px; color: var(--text-muted); margin: 0">
                {{ selectedProduct === 'all' ? 'Portfolio aggregate' : `Product: ${selectedProduct}` }}
              </p>
            </div>
          </div>
          <div class="chart-container">
            <canvas ref="chartCanvas"></canvas>
          </div>
        </div>

        <!-- Price Sensitivity Table -->
        <div class="card" style="margin-bottom: 20px">
          <h3 style="margin: 0 0 16px">Price Sensitivity Analysis</h3>
          <n-data-table
            :columns="curveColumns"
            :data="samplePoints"
            :bordered="false"
            :striped="true"
            size="small"
          />
        </div>

        <!-- Chat Assistant -->
        <div class="card">
          <h3 style="margin: 0 0 4px">Ask Your Pricing Assistant</h3>
          <p style="font-size: 13px; color: var(--text-muted); margin: 0 0 16px">
            Ask anything about your pricing, inventory risks, or explore what-if scenarios
          </p>

          <div class="chat-messages" ref="chatContainer">
            <div v-if="chatHistory.length === 0" class="chat-empty">
              <p>Ask about your pricing, compare scenarios, or check inventory reorder recommendations.</p>
            </div>
            <div v-for="(msg, i) in chatHistory" :key="i" class="message" :class="msg.role">
              <div class="message-bubble">{{ msg.content }}</div>
            </div>
            <div v-if="chatLoading" class="message assistant">
              <div class="message-bubble typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>

          <div class="chat-suggestions">
            <n-button
              v-for="s in suggestions"
              :key="s"
              size="tiny"
              quaternary
              @click="sendSuggestion(s)"
            >
              {{ s }}
            </n-button>
          </div>

          <div class="chat-input">
            <n-input
              v-model:value="chatMessage"
              placeholder="Ask about pricing, demand, or inventory..."
              @keyup.enter="sendMessage"
              :disabled="chatLoading"
            />
            <n-button type="primary" @click="sendMessage" :disabled="chatLoading || !chatMessage">
              Send
            </n-button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch, h } from 'vue'
import { useRoute } from 'vue-router'
import { usePredictionsStore } from '@/stores/predictions'
import { useProductsStore } from '@/stores/products'
import {
  NButton, NInput, NDataTable, NTag, NAlert, NSpin,
  NRadioGroup, NRadioButton, NSelect
} from 'naive-ui'
import AppNav from '@/components/AppNav.vue'
import api from '@/services/api'

const route = useRoute()
const predictionsStore = usePredictionsStore()
const productsStore = useProductsStore()

const uniqueId = route.params.uniqueId
const loading = ref(true)
const error = ref(null)
const notice = ref(null)
const predictions = ref(null)
const chartCanvas = ref(null)
let chartInstance = null
const selectedProduct = ref('all')
const forecastPeriod = ref('day1')
const chatHistory = ref([])
const chatMessage = ref('')
const chatLoading = ref(false)
const chatContainer = ref(null)

const forecastLabel = computed(() => ({ day1: 'tomorrow', day7: 'next 7 days', day30: 'next 30 days' }[forecastPeriod.value]))

const objectiveType = computed(() => {
  const obj = predictions.value?.optimization_objective
  return obj === 'revenue' ? 'info' : obj === 'profit' ? 'success' : 'warning'
})

const productOptions = computed(() => {
  const opts = [{ label: 'All Products (Portfolio)', value: 'all' }]
  predictions.value?.product_results?.forEach(p => opts.push({ label: p.product_name || p.product, value: p.product }))
  return opts
})

const samplePoints = computed(() => {
  const curve = selectedProduct.value === 'all'
    ? predictions.value?.price_demand_curve
    : predictions.value?.product_results?.find(p => p.product === selectedProduct.value)?.curve
  if (!curve) return []
  const step = Math.max(1, Math.floor(curve.length / 10))
  return curve.filter((_, i) => i % step === 0)
})

const productColumns = [
  {
    title: 'Product',
    key: 'product',
    render: r => h('code', { style: 'background:#f0f4ff;color:#6366f1;padding:2px 6px;border-radius:4px;font-size:12px' }, r.product),
  },
  { title: 'Optimal Price', key: 'optimal_price', render: r => h('strong', {}, `$${r.optimal_price}`) },
  {
    title: 'Stock-Aware Price',
    key: 'inventory_adjusted_price',
    render: r => r.inventory_adjusted_price != null ? `$${r.inventory_adjusted_price}` : '—',
  },
  { title: 'Predicted Demand', key: 'predicted_demand', render: r => `${r.predicted_demand} units` },
  { title: 'Expected Revenue', key: 'expected_revenue', render: r => `$${r.expected_revenue?.toFixed(2)}` },
  { title: 'Expected Profit', key: 'expected_profit', render: r => r.expected_profit != null ? `$${r.expected_profit?.toFixed(2)}` : '—' },
  {
    title: 'Action',
    key: 'apply',
    render: r => h(
      NButton,
      {
        size: 'tiny',
        type: 'primary',
        ghost: true,
        onClick: () => applyPrice(r.product, r.inventory_adjusted_price ?? r.optimal_price),
      },
      { default: () => 'Apply Price' }
    ),
  },
]

const curveColumns = [
  { title: 'Price', key: 'price', render: r => `$${r.price}` },
  { title: 'Predicted Demand', key: 'predicted_demand', render: r => `${r.predicted_demand} units` },
  { title: 'Revenue', key: 'revenue', render: r => `$${r.revenue}` },
  { title: 'Profit', key: 'profit', render: r => r.profit != null ? `$${r.profit}` : '—' },
]

const suggestions = [
  'Why is this the optimal price?',
  'Which products need restocking?',
  'What drives demand most?',
  'What if I raise price by 15%?',
]

async function applyPrice(productId, price) {
  try {
    await productsStore.applyRecommendedPrice(productId, price)
    notice.value = `Applied $${price} as the new base price for ${productId}.`
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not apply price'
  }
}

onMounted(async () => {
  try {
    predictions.value = await predictionsStore.getPredictions(uniqueId)
    await nextTick()
    drawChart()
  } catch {
    error.value = 'Failed to load predictions'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
})

watch(selectedProduct, () => {
  nextTick(() => drawChart())
})

function drawChart() {
  if (!chartCanvas.value || !predictions.value) return

  const curve = selectedProduct.value === 'all'
    ? predictions.value.price_demand_curve
    : predictions.value.product_results?.find(p => p.product === selectedProduct.value)?.curve

  if (!curve) return

  import('chart.js').then(({ Chart, registerables }) => {
    Chart.register(...registerables)
    const existing = Chart.getChart(chartCanvas.value)
    if (existing) existing.destroy()

    chartInstance = new Chart(chartCanvas.value, {
      type: 'line',
      data: {
        labels: curve.map(p => `$${p.price}`),
        datasets: [
          {
            label: 'Revenue',
            data: curve.map(p => p.revenue),
            borderColor: '#16735a',
            backgroundColor: 'rgba(22,115,90,0.08)',
            tension: 0.4,
            yAxisID: 'y',
          },
          {
            label: 'Demand',
            data: curve.map(p => p.predicted_demand),
            borderColor: '#326c79',
            backgroundColor: 'rgba(50,108,121,0.08)',
            tension: 0.4,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { type: 'linear', position: 'left', title: { display: true, text: 'Revenue ($)' } },
          y1: { type: 'linear', position: 'right', title: { display: true, text: 'Demand (units)' }, grid: { drawOnChartArea: false } },
        },
      },
    })
  })
}

async function sendMessage() {
  if (!chatMessage.value.trim() || chatLoading.value) return
  const msg = chatMessage.value.trim()
  chatHistory.value.push({ role: 'user', content: msg })
  chatMessage.value = ''
  chatLoading.value = true
  try {
    const res = await api.post(`/predictions/chat/${uniqueId}`, {
      message: msg,
      history: chatHistory.value.slice(0, -1),
    })
    chatHistory.value.push({ role: 'assistant', content: res.data.response })
  } catch (err) {
    console.error('Unable to send pricing-assistant message', err)
    chatHistory.value.push({ role: 'assistant', content: 'Sorry, I could not process that. Try again.' })
  } finally {
    chatLoading.value = false
    await nextTick()
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function sendSuggestion(s) {
  chatMessage.value = s
  sendMessage()
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }

.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 20px; }
.stat-card.highlight { border-color: var(--primary); background: var(--primary-light); }
.stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }

.metrics-strip { display: flex; gap: 10px; }
.mini-metric { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 14px; text-align: center; }
.mini-metric span { display: block; font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
.mini-metric strong { font-size: 14px; color: var(--text-primary); }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
.chart-container { height: 300px; }

.product-forecast-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.forecast-card { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 16px; text-align: center; }
.forecast-card.total { border-color: var(--primary); background: var(--primary-light); }
.forecast-product { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.forecast-value { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.forecast-label { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

.chat-messages { min-height: 200px; max-height: 350px; overflow-y: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 16px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px; background: var(--surface-2); }
.chat-empty { text-align: center; color: var(--text-muted); font-size: 14px; padding: 24px 0; }
.message { display: flex; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.message-bubble { max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; }
.message.user .message-bubble { background: var(--primary); color: white; border-bottom-right-radius: 4px; }
.message.assistant .message-bubble { background: var(--surface); border: 1px solid var(--border); color: var(--text-primary); border-bottom-left-radius: 4px; }
.typing span { display: inline-block; width: 6px; height: 6px; background: var(--text-muted); border-radius: 50%; margin: 0 2px; animation: bounce 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }

.chat-suggestions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.chat-input { display: flex; gap: 8px; }
.loading-state { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 80px 0; color: var(--text-muted); }
</style>

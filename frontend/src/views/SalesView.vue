<template>
  <div class="page">
    <AppNav />
    <div class="content">
      <div class="page-header">
        <div>
          <h1>Sales Data</h1>
          <p class="subtitle">Log transactions and view aggregated analytics</p>
        </div>
        <div style="display: flex; gap: 10px">
          <n-button @click="salesStore.downloadTemplate()"><n-icon><DownloadOutline /></n-icon> Template</n-button>
          <n-button @click="showImport = !showImport"><n-icon><CloudUploadOutline /></n-icon> Import CSV</n-button>
          <n-button type="primary" @click="showForm = !showForm">+ Log Transaction</n-button>
        </div>
      </div>

      <!-- Summary -->
      <div class="stats-grid" style="margin-bottom: 20px">
        <div class="stat-card">
          <p class="stat-label">Transactions</p>
          <p class="stat-value">{{ summary?.total_records?.toLocaleString() || 0 }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">Units Sold</p>
          <p class="stat-value">{{ summary?.total_units?.toLocaleString() || 0 }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">Revenue</p>
          <p class="stat-value">${{ summary?.total_revenue?.toLocaleString() || 0 }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">Products</p>
          <p class="stat-value">{{ summary?.products?.length || 0 }}</p>
        </div>
      </div>

      <!-- Import -->
      <div v-if="showImport" class="card" style="margin-bottom: 20px">
        <h3 style="margin: 0 0 12px">Import Transactions</h3>
        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px">
          Required columns: <code>product_id, units, price</code>. Optional: <code>transaction_time, cost, is_promotion, inventory_level, channel</code>
        </p>
        <n-upload accept=".csv" :default-upload="false" @change="handleImport">
          <n-button>Choose CSV File</n-button>
        </n-upload>
        <n-alert v-if="importResult" type="success" style="margin-top: 12px">
          {{ importResult.imported }} records imported
          <span v-if="importResult.errors?.length"> · {{ importResult.errors.length }} errors</span>
        </n-alert>
        <n-alert v-if="importError" type="error" style="margin-top: 12px">{{ importError }}</n-alert>
      </div>

      <!-- Log Transaction Form -->
      <div v-if="showForm" class="card" style="margin-bottom: 20px">
        <h3 style="margin: 0 0 16px">Log Transaction</h3>
        <n-form :model="form" label-placement="top">
          <n-grid :cols="4" :x-gap="16">
            <n-form-item-gi label="Product *">
              <n-select v-model:value="form.product_id" :options="productOptions" placeholder="Select product" />
            </n-form-item-gi>
            <n-form-item-gi label="Date & Time">
              <n-date-picker v-model:value="form.transaction_time" type="datetime" style="width:100%" />
            </n-form-item-gi>
            <n-form-item-gi label="Units *">
              <n-input-number v-model:value="form.units" :min="1" style="width:100%" />
            </n-form-item-gi>
            <n-form-item-gi label="Price per Unit ($) *">
              <n-input-number v-model:value="form.price" :min="0" :step="0.01" style="width:100%" />
            </n-form-item-gi>
            <n-form-item-gi label="Cost per Unit ($)">
              <n-input-number v-model:value="form.cost" :min="0" :step="0.01" style="width:100%" />
            </n-form-item-gi>
            <n-form-item-gi label="Inventory Level">
              <n-input-number v-model:value="form.inventory_level" :min="0" style="width:100%" />
            </n-form-item-gi>
            <n-form-item-gi label="Channel">
              <n-select v-model:value="form.channel" :options="channelOptions" clearable />
            </n-form-item-gi>
            <n-form-item-gi label=" ">
              <n-checkbox v-model:checked="form.is_promotion_bool">Promotion Active</n-checkbox>
            </n-form-item-gi>
          </n-grid>
          <n-alert v-if="formError" type="error" style="margin-top: 8px">{{ formError }}</n-alert>
          <div style="display: flex; gap: 10px; margin-top: 16px; justify-content: flex-end">
            <n-button @click="cancelForm">Cancel</n-button>
            <n-button type="primary" @click="submitForm">Log Transaction</n-button>
          </div>
        </n-form>
      </div>

      <!-- Aggregated View -->
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
          <h3 style="margin: 0">Sales Analytics</h3>
          <div style="display: flex; gap: 10px; align-items: center">
            <n-radio-group v-model:value="granularity" @update:value="fetchAggregated" size="small">
              <n-radio-button value="hourly">Hourly</n-radio-button>
              <n-radio-button value="daily">Daily</n-radio-button>
              <n-radio-button value="weekly">Weekly</n-radio-button>
              <n-radio-button value="monthly">Monthly</n-radio-button>
            </n-radio-group>
          </div>
        </div>
        <n-data-table
          :columns="aggColumns"
          :data="aggregated"
          :pagination="{ pageSize: 15 }"
          :bordered="false"
          :striped="true"
          size="small"
        />
      </div>

      <!-- Recent Transactions -->
      <div class="card" style="margin-top: 20px">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
          <h3 style="margin: 0">Recent Transactions</h3>
          <n-input v-model:value="search" placeholder="Search product..." size="small" style="width: 200px" clearable />
        </div>
        <n-data-table
          :columns="txColumns"
          :data="filteredTransactions"
          :pagination="{ pageSize: 20 }"
          :bordered="false"
          size="small"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, h } from 'vue'
import { useSalesStore } from '@/stores/sales'
import { useProductsStore } from '@/stores/products'
import {
  NButton, NInput, NSelect, NInputNumber, NCheckbox, NDatePicker,
  NDataTable, NForm, NFormItemGi, NGrid, NAlert,
  NUpload, NTag, NRadioGroup, NRadioButton, NPopconfirm, NIcon
} from 'naive-ui'
import { CloudUploadOutline, DownloadOutline } from '@vicons/ionicons5'
import AppNav from '@/components/AppNav.vue'
import api from '@/services/api'

const salesStore = useSalesStore()
const productsStore = useProductsStore()

const transactions = ref([])
const products = ref([])
const aggregated = ref([])
const summary = ref(null)
const search = ref('')
const showForm = ref(false)
const showImport = ref(false)
const granularity = ref('daily')
const importResult = ref(null)
const importError = ref(null)
const formError = ref(null)

const form = ref({
  product_id: null,
  transaction_time: Date.now(),
  units: 1,
  price: null,
  cost: null,
  is_promotion_bool: false,
  inventory_level: null,
  channel: null
})

const productOptions = computed(() =>
  products.value.map(p => ({ label: `${p.product_name} (${p.product_id})`, value: p.product_id }))
)

const channelOptions = [
  { label: 'Online', value: 'online' },
  { label: 'Offline', value: 'offline' },
  { label: 'Wholesale', value: 'wholesale' },
  { label: 'Retail', value: 'retail' }
]

const filteredTransactions = computed(() => {
  if (!search.value) return transactions.value
  return transactions.value.filter(t => t.product_id.toLowerCase().includes(search.value.toLowerCase()))
})

const aggColumns = [
  { title: 'Period', key: 'period' },
  { title: 'Transactions', key: 'transactions' },
  { title: 'Units', key: 'total_units' },
  { title: 'Revenue', key: 'total_revenue', render: r => `$${r.total_revenue?.toFixed(2)}` },
  { title: 'Profit', key: 'total_profit', render: r => `$${r.total_profit?.toFixed(2)}` },
  { title: 'Avg Price', key: 'avg_price', render: r => `$${r.avg_price?.toFixed(2)}` }
]

const txColumns = [
  { title: 'Time', key: 'transaction_time', render: r => new Date(r.transaction_time).toLocaleString() },
  { title: 'Product', key: 'product_id', render: r => h('code', { style: 'background:#f0f4ff;color:#6366f1;padding:2px 6px;border-radius:4px;font-size:11px' }, r.product_id) },
  { title: 'Units', key: 'units' },
  { title: 'Price', key: 'price', render: r => `$${r.price}` },
  { title: 'Revenue', key: 'revenue', render: r => `$${(r.units * r.price).toFixed(2)}` },
  { title: 'Promo', key: 'is_promotion', render: r => r.is_promotion ? h(NTag, { type: 'success', size: 'small' }, { default: () => 'Yes' }) : '—' },
  { title: 'Channel', key: 'channel', render: r => r.channel || '—' },
  {
    title: '',
    key: 'delete',
    render: r => h(NPopconfirm, { onPositiveClick: () => deleteTransaction(r.id) }, {
      default: () => 'Delete this transaction?',
      trigger: () => h(NButton, { size: 'tiny', quaternary: true }, { default: () => '🗑' })
    })
  }
]

onMounted(async () => {
  transactions.value = await salesStore.fetchSales() // using /transactions endpoint
  products.value = await productsStore.fetchProducts()
  summary.value = await salesStore.fetchSummary()
  await fetchAggregated()
})

async function fetchAggregated() {
  const res = await api.get(`/sales/aggregated?granularity=${granularity.value}`)
  aggregated.value = res.data
}

function cancelForm() {
  showForm.value = false
  formError.value = null
  form.value = { product_id: null, transaction_time: Date.now(), units: 1, price: null, cost: null, is_promotion_bool: false, inventory_level: null, channel: null }
}

async function submitForm() {
  formError.value = null
  if (!form.value.product_id || !form.value.price || !form.value.units) {
    formError.value = 'Product, units, and price are required'
    return
  }
  try {
    const payload = {
      product_id: form.value.product_id,
      transaction_time: new Date(form.value.transaction_time).toISOString(),
      units: form.value.units,
      price: form.value.price,
      cost: form.value.cost,
      is_promotion: form.value.is_promotion_bool ? 1 : 0,
      inventory_level: form.value.inventory_level,
      channel: form.value.channel
    }
    await api.post('/sales/transaction', payload)
    transactions.value = await salesStore.fetchSales()
    summary.value = await salesStore.fetchSummary()
    await fetchAggregated()
    cancelForm()
  } catch (err) {
    formError.value = err.response?.data?.detail || 'Failed to log transaction'
  }
}

async function handleImport(data) {
  const file = data.file.file
  importError.value = null
  importResult.value = null
  try {
    importResult.value = await salesStore.importCSV(file)
    transactions.value = await salesStore.fetchSales()
    summary.value = await salesStore.fetchSummary()
    await fetchAggregated()
  } catch (err) {
    importError.value = err.response?.data?.detail || 'Import failed'
  }
}

async function deleteTransaction(id) {
  await api.delete(`/sales/transaction/${id}`)
  transactions.value = transactions.value.filter(t => t.id !== id)
  summary.value = await salesStore.fetchSummary()
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1300px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 20px; }
.stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
code { background: #f0f4ff; color: #6366f1; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-family: monospace; }
</style>

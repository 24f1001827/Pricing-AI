<template>
  <div class="page">
    <AppNav />
    <div class="content">
      <div class="page-header">
        <div>
          <p class="section-kicker">Replenishment &amp; Stock-Aware Pricing</p>
          <h1>Inventory Optimization</h1>
          <p class="subtitle">Monitor days of cover, reorder points, EOQ, and stock-constrained price actions</p>
        </div>
        <div style="display: flex; gap: 10px">
          <n-button @click="loadInventory">Refresh</n-button>
          <n-button type="primary" @click="router.push('/products')">Manage Catalog</n-button>
        </div>
      </div>

      <n-alert v-if="notice" type="success" closable @close="notice = null" style="margin-bottom: 16px">
        {{ notice }}
      </n-alert>
      <n-alert v-if="error" type="error" closable @close="error = null" style="margin-bottom: 16px">
        {{ error }}
      </n-alert>

      <div class="stats-grid" style="margin-bottom: 20px">
        <div class="stat-card">
          <p class="stat-label">Tracked SKUs</p>
          <p class="stat-value">{{ items.length }}</p>
        </div>
        <div class="stat-card danger">
          <p class="stat-label">Stockout Risk</p>
          <p class="stat-value">{{ countByStatus('stockout_risk') }}</p>
        </div>
        <div class="stat-card warn">
          <p class="stat-label">Reorder Now</p>
          <p class="stat-value">{{ countByStatus('reorder_now') }}</p>
        </div>
        <div class="stat-card info">
          <p class="stat-label">Overstock</p>
          <p class="stat-value">{{ countByStatus('overstock') }}</p>
        </div>
      </div>

      <n-alert v-if="!hasForecast && items.length" type="info" style="margin-bottom: 20px">
        Train a demand model from your Dashboard to populate safety stock, reorder points, EOQ, and inventory-aware pricing.
      </n-alert>

      <div class="card">
        <n-data-table
          :columns="columns"
          :data="items"
          :loading="loading"
          :bordered="false"
          :striped="true"
          :pagination="{ pageSize: 15 }"
        />
      </div>
    </div>

    <n-modal v-model:show="showRestockModal" preset="card" :title="`Restock ${restockTarget?.product_name || ''}`" style="width: 420px">
      <n-form label-placement="top">
        <p style="font-size: 13px; color: var(--text-secondary); margin: 0 0 12px">
          Current stock: <strong>{{ restockTarget?.stock_on_hand ?? 0 }}</strong> ·
          Recommended order qty: <strong>{{ restockTarget?.recommended_order_qty ?? '—' }}</strong>
        </p>
        <n-form-item label="Units Received">
          <n-input-number v-model:value="restockQty" :min="1" style="width: 100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showRestockModal = false">Cancel</n-button>
          <n-button type="primary" :loading="saving" @click="submitRestock">Confirm Restock</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useProductsStore } from '@/stores/products'
import { NAlert, NButton, NDataTable, NForm, NFormItem, NInputNumber, NModal, NTag } from 'naive-ui'
import AppNav from '@/components/AppNav.vue'

const router = useRouter()
const productsStore = useProductsStore()

const items = ref([])
const hasForecast = ref(false)
const loading = ref(true)
const saving = ref(false)
const notice = ref(null)
const error = ref(null)
const showRestockModal = ref(false)
const restockTarget = ref(null)
const restockQty = ref(10)

const statusMeta = {
  stockout_risk: { label: 'Stockout Risk', type: 'error' },
  reorder_now: { label: 'Reorder Now', type: 'warning' },
  overstock: { label: 'Overstock', type: 'info' },
  healthy: { label: 'Healthy', type: 'success' },
  unforecasted: { label: 'Needs Forecast', type: 'default' },
}

const columns = [
  {
    title: 'Product',
    key: 'product_id',
    render: r => h('div', {}, [
      h('strong', {}, r.product_name),
      h('div', { style: 'font-size:11px;color:#788981' }, r.product_id),
    ]),
  },
  {
    title: 'Status',
    key: 'stock_status',
    render: r => {
      const m = statusMeta[r.stock_status] || statusMeta.unforecasted
      return h(NTag, { type: m.type, size: 'small' }, { default: () => m.label })
    },
  },
  { title: 'Stock', key: 'stock_on_hand' },
  { title: 'Avg Daily Demand', key: 'avg_daily_demand', render: r => r.avg_daily_demand ? `${r.avg_daily_demand}/d` : '—' },
  { title: 'Days Cover', key: 'days_of_cover', render: r => r.days_of_cover != null ? `${r.days_of_cover}d` : '—' },
  { title: 'Safety Stock', key: 'safety_stock', render: r => r.safety_stock ?? '—' },
  { title: 'Reorder Point', key: 'reorder_point', render: r => r.reorder_point ?? '—' },
  { title: 'Rec. Order Qty', key: 'recommended_order_qty', render: r => r.recommended_order_qty > 0 ? `${r.recommended_order_qty} units` : '0' },
  {
    title: 'Stock-Aware Price',
    key: 'inventory_adjusted_price',
    render: r => {
      if (r.inventory_adjusted_price == null) return '—'
      const changed = r.base_optimal_price != null && r.inventory_adjusted_price !== r.base_optimal_price
      return h('div', { title: r.price_action_note || '' }, [
        h('strong', {}, `$${r.inventory_adjusted_price}`),
        changed ? h('div', { style: 'font-size:11px;color:#b7791f' }, `Base: $${r.base_optimal_price}`) : null,
      ])
    },
  },
  {
    title: 'Actions',
    key: 'actions',
    render: r => h('div', { style: 'display:flex;gap:6px' }, [
      h(NButton, { size: 'tiny', onClick: () => openRestock(r) }, { default: () => 'Restock' }),
      r.inventory_adjusted_price != null
        ? h(NButton, { size: 'tiny', type: 'primary', ghost: true, onClick: () => applyPrice(r) }, { default: () => 'Apply Price' })
        : null,
    ]),
  },
]

function countByStatus(status) {
  return items.value.filter(i => i.stock_status === status).length
}

async function loadInventory() {
  loading.value = true
  error.value = null
  try {
    const res = await productsStore.fetchInventorySummary()
    hasForecast.value = res.has_forecast
    items.value = res.items || []
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to load inventory summary'
  } finally {
    loading.value = false
  }
}

function openRestock(row) {
  restockTarget.value = row
  restockQty.value = row.recommended_order_qty > 0 ? row.recommended_order_qty : (row.eoq || 25)
  showRestockModal.value = true
}

async function submitRestock() {
  if (!restockTarget.value) return
  saving.value = true
  error.value = null
  try {
    await productsStore.restockProduct(restockTarget.value.product_id, restockQty.value)
    notice.value = `Added ${restockQty.value} units to ${restockTarget.value.product_name}.`
    showRestockModal.value = false
    await loadInventory()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to restock product'
  } finally {
    saving.value = false
  }
}

async function applyPrice(row) {
  error.value = null
  try {
    await productsStore.applyRecommendedPrice(row.product_id, row.inventory_adjusted_price)
    notice.value = `Updated base price of ${row.product_name} to $${row.inventory_adjusted_price}.`
    await loadInventory()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to apply price'
  }
}

onMounted(loadInventory)
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1320px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.section-kicker { margin: 0 0 7px; color: var(--primary); font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 20px; }
.stat-card.danger { border-color: #f1c6ca; background: #fff9f9; }
.stat-card.warn { border-color: #f0d8a8; background: #fffcf5; }
.stat-card.info { border-color: #c6dce4; background: #f8fbfc; }
.stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-primary); margin: 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
@media (max-width: 800px) { .stats-grid { grid-template-columns: 1fr 1fr; } }
</style>

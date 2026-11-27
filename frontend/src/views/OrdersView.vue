<template>
  <div class="page">
    <AppNav />
    <div class="content">
      <div class="page-header">
        <div>
          <h1>Orders</h1>
          <p class="subtitle">Log customer purchases, manage business calendar, and view sales analytics</p>
        </div>
        <div style="display:flex;gap:10px">
          <n-button @click="ordersStore.downloadTemplate()"><n-icon><DownloadOutline /></n-icon> Template</n-button>
          <n-button @click="showImport = !showImport"><n-icon><CloudUploadOutline /></n-icon> Import</n-button>
          <n-button type="primary" @click="showOrderForm = true">+ New Order</n-button>
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="stats-grid" style="margin-bottom:20px">
        <div class="stat-card">
          <div class="stat-icon orders"><n-icon><ReceiptOutline /></n-icon></div>
          <div>
            <p class="stat-label">Total Orders</p>
            <p class="stat-value">{{ summary?.total_orders?.toLocaleString() || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon revenue"><n-icon><CashOutline /></n-icon></div>
          <div>
            <p class="stat-label">Total Revenue</p>
            <p class="stat-value">${{ summary?.total_revenue?.toLocaleString() || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon profit"><n-icon><TrendingUpOutline /></n-icon></div>
          <div>
            <p class="stat-label">Total Profit</p>
            <p class="stat-value">${{ summary?.total_profit?.toLocaleString() || 0 }}</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon customers"><n-icon><PeopleOutline /></n-icon></div>
          <div>
            <p class="stat-label">Unique Customers</p>
            <p class="stat-value">{{ summary?.unique_customers || 0 }}</p>
          </div>
        </div>
      </div>

      <!-- Import -->
      <div v-if="showImport" class="card" style="margin-bottom:20px">
        <h3 style="margin:0 0 12px">Import Orders from CSV</h3>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">
          Each row = one line item. Rows with same <code>customer_email + order_time</code> are grouped into one order.
        </p>
        <n-upload accept=".csv" :default-upload="false" @change="handleImport">
          <n-button>Choose CSV File</n-button>
        </n-upload>
        <n-alert v-if="importResult" type="success" style="margin-top:12px">
          {{ importResult.orders_created }} orders imported
          <span v-if="importResult.errors?.length">; {{ importResult.errors.join(' · ') }}</span>
        </n-alert>
        <n-alert v-if="importError" type="error" style="margin-top:12px">{{ importError }}</n-alert>
      </div>

      <!-- Tabs -->
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="orders" tab="Recent Orders">
          <div class="card">
            <n-data-table
              :columns="orderColumns"
              :data="orders"
              :pagination="{ pageSize: 20 }"
              :bordered="false"
              :striped="true"
              :row-props="rowProps"
            />
          </div>
        </n-tab-pane>

        <n-tab-pane name="analytics" tab="Analytics">
          <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
              <h3 style="margin:0">Sales Over Time</h3>
              <n-radio-group v-model:value="granularity" @update:value="fetchAggregated" size="small">
                <n-radio-button value="daily">Daily</n-radio-button>
                <n-radio-button value="weekly">Weekly</n-radio-button>
                <n-radio-button value="monthly">Monthly</n-radio-button>
              </n-radio-group>
            </div>
            <div style="height:300px"><canvas ref="chartCanvas"></canvas></div>
          </div>
        </n-tab-pane>

        <n-tab-pane name="products" tab="By Product">
          <div class="card">
            <n-data-table :columns="productColumns" :data="byProduct" :bordered="false" :striped="true" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="customers" tab="Customers">
          <div class="card">
            <n-data-table :columns="customerColumns" :data="customers" :bordered="false" :striped="true" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="calendar" tab="Business Calendar">
          <div class="card">
            <h3 style="margin: 0 0 8px">Holidays, Festivals &amp; Closed Days</h3>
            <p style="font-size: 13px; color: var(--text-muted); margin: 0 0 16px">
              Closed days are excluded from nightly evaluation and forecast as 0 demand; holidays and festivals improve demand predictions.
            </p>
            <div class="calendar-form">
              <n-input v-model:value="calendarForm.date" placeholder="YYYY-MM-DD" style="width: 150px" />
              <n-checkbox v-model:checked="calendarForm.is_closed">Closed</n-checkbox>
              <n-checkbox v-model:checked="calendarForm.is_holiday">Holiday</n-checkbox>
              <n-checkbox v-model:checked="calendarForm.is_festival">Festival</n-checkbox>
              <n-input v-model:value="calendarForm.note" placeholder="Optional note (e.g. Diwali sale)" style="flex: 1" />
              <n-button type="primary" @click="saveCalendar">Save Date</n-button>
            </div>
            <n-data-table :columns="calendarColumns" :data="calendarEntries" :bordered="false" :striped="true" size="small" />
          </div>
        </n-tab-pane>
      </n-tabs>
    </div>

    <!-- New Order Modal -->
    <n-modal v-model:show="showOrderForm" preset="card" title="New Order" style="width:680px;max-height:90vh;overflow-y:auto">
      <n-form label-placement="top">
        <n-grid :cols="2" :x-gap="16">
          <n-form-item-gi label="Customer Name">
            <n-input v-model:value="orderForm.customer_name" placeholder="John Doe" />
          </n-form-item-gi>
          <n-form-item-gi label="Customer Email">
            <n-input v-model:value="orderForm.customer_email" placeholder="john@example.com" />
          </n-form-item-gi>
          <n-form-item-gi label="Order Time">
            <n-date-picker v-model:value="orderForm.order_time" type="datetime" style="width:100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Channel">
            <n-select v-model:value="orderForm.channel" :options="channelOptions" clearable />
          </n-form-item-gi>
          <n-form-item-gi :span="2">
            <n-checkbox v-model:checked="orderForm.is_promotion">Promotion Applied</n-checkbox>
          </n-form-item-gi>
        </n-grid>

        <n-divider>Line Items</n-divider>

        <div v-for="(item, i) in orderForm.line_items" :key="i" class="line-item-row">
          <n-select
            v-model:value="item.product_id"
            :options="productOptions"
            placeholder="Product"
            style="flex:2"
            @update:value="(v) => autoFillPrice(v, i)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="Qty" style="width:80px" />
          <n-input-number v-model:value="item.unit_price" :min="0" :step="0.01" placeholder="Price" style="width:110px" />
          <n-input-number v-model:value="item.unit_cost" :min="0" :step="0.01" placeholder="Cost" style="width:110px" />
          <n-input-number v-model:value="item.inventory_level" :min="0" placeholder="Stock" style="width:90px" />
          <n-button circle quaternary @click="removeItem(i)" :disabled="orderForm.line_items.length === 1">✕</n-button>
        </div>

        <n-button dashed block style="margin-top:10px" @click="addItem">+ Add Item</n-button>

        <div class="order-totals">
          <span>Subtotal: <strong>${{ orderTotal.toFixed(2) }}</strong></span>
          <span style="margin-left:24px">Profit: <strong>${{ orderProfit.toFixed(2) }}</strong></span>
        </div>

        <n-alert v-if="orderError" type="error" style="margin-top:12px">{{ orderError }}</n-alert>
      </n-form>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:10px">
          <n-button @click="showOrderForm = false">Cancel</n-button>
          <n-button type="primary" :loading="submitting" @click="submitOrder">Place Order</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Order Detail Modal -->
    <n-modal v-model:show="showDetail" preset="card" :title="`Order ${selectedOrder?.order_id?.slice(0,8)}...`" style="width:560px">
      <div v-if="selectedOrder">
        <n-descriptions bordered :column="2" size="small">
          <n-descriptions-item label="Customer">{{ selectedOrder.customer_name || 'Guest' }}</n-descriptions-item>
          <n-descriptions-item label="Email">{{ selectedOrder.customer_email || '—' }}</n-descriptions-item>
          <n-descriptions-item label="Time">{{ new Date(selectedOrder.order_time).toLocaleString() }}</n-descriptions-item>
          <n-descriptions-item label="Channel">{{ selectedOrder.channel || '—' }}</n-descriptions-item>
          <n-descriptions-item label="Revenue">${{ selectedOrder.total_revenue }}</n-descriptions-item>
          <n-descriptions-item label="Profit">${{ selectedOrder.total_profit }}</n-descriptions-item>
        </n-descriptions>
        <n-divider>Items</n-divider>
        <n-data-table
          :columns="[
            { title: 'Product', key: 'product_id' },
            { title: 'Qty', key: 'quantity' },
            { title: 'Unit Price', key: 'unit_price', render: r => `$${r.unit_price}` },
            { title: 'Total', key: 'total', render: r => `$${(r.quantity * r.unit_price).toFixed(2)}` }
          ]"
          :data="selectedOrder.items"
          :bordered="false"
          size="small"
        />
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch, h, nextTick } from 'vue'
import { useOrdersStore } from '@/stores/orders'
import { useProductsStore } from '@/stores/products'
import {
  NButton, NDataTable, NModal, NForm, NFormItemGi,
  NInput, NInputNumber, NSelect, NCheckbox, NDatePicker, NGrid,
  NAlert, NUpload, NTabs, NTabPane, NRadioGroup, NRadioButton,
  NDivider, NDescriptions, NDescriptionsItem, NPopconfirm, NIcon, NTag
} from 'naive-ui'
import { CashOutline, CloudUploadOutline, DownloadOutline, PeopleOutline, ReceiptOutline, TrendingUpOutline } from '@vicons/ionicons5'
import AppNav from '@/components/AppNav.vue'
import api from '@/services/api'

const ordersStore = useOrdersStore()
const productsStore = useProductsStore()

const orders = ref([])
const byProduct = ref([])
const customers = ref([])
const aggregated = ref([])
const calendarEntries = ref([])
const summary = ref(null)
const products = ref([])
const activeTab = ref('orders')
const granularity = ref('daily')
const showOrderForm = ref(false)
const showImport = ref(false)
const showDetail = ref(false)
const selectedOrder = ref(null)
const submitting = ref(false)
const orderError = ref(null)
const importResult = ref(null)
const importError = ref(null)
const chartCanvas = ref(null)
let chartInstance = null

const calendarForm = ref({
  date: new Date().toISOString().slice(0, 10),
  is_closed: false,
  is_holiday: false,
  is_festival: false,
  note: '',
})

const channelOptions = [
  { label: 'In-Store', value: 'in-store' },
  { label: 'Online', value: 'online' },
  { label: 'Phone', value: 'phone' },
  { label: 'Wholesale', value: 'wholesale' },
]

const productOptions = computed(() =>
  products.value.map(p => ({ label: `${p.product_name} (${p.product_id})`, value: p.product_id }))
)

const orderForm = ref({
  customer_name: '',
  customer_email: '',
  order_time: Date.now(),
  channel: null,
  is_promotion: false,
  line_items: [{ product_id: null, quantity: 1, unit_price: null, unit_cost: null, inventory_level: null }],
})

const orderTotal = computed(() =>
  orderForm.value.line_items.reduce((sum, i) => sum + (i.quantity || 0) * (i.unit_price || 0), 0)
)

const orderProfit = computed(() =>
  orderForm.value.line_items.reduce((sum, i) => {
    const p = products.value.find(p => p.product_id === i.product_id)
    const cost = i.unit_cost ?? p?.cost ?? 0
    return sum + (i.quantity || 0) * ((i.unit_price || 0) - cost)
  }, 0)
)

const orderColumns = [
  { title: 'Time', key: 'order_time', render: r => new Date(r.order_time).toLocaleString(), width: 160 },
  { title: 'Customer', key: 'customer_name', render: r => r.customer_name || 'Guest' },
  { title: 'Items', key: 'items', render: r => `${r.items?.length || 0} item(s)` },
  { title: 'Revenue', key: 'total_revenue', render: r => `$${r.total_revenue?.toFixed(2)}` },
  { title: 'Profit', key: 'total_profit', render: r => `$${r.total_profit?.toFixed(2)}` },
  { title: 'Channel', key: 'channel', render: r => r.channel || '—' },
  {
    title: '',
    key: 'actions',
    render: r => h('div', { style: 'display:flex;gap:6px' }, [
      h(NButton, { size: 'tiny', onClick: () => { selectedOrder.value = r; showDetail.value = true } }, { default: () => 'View' }),
      h(NPopconfirm, { onPositiveClick: () => deleteOrder(r.order_id) }, {
        default: () => 'Delete this order?',
        trigger: () => h(NButton, { size: 'tiny', quaternary: true }, { default: () => 'Delete' }),
      }),
    ]),
  },
]

const productColumns = [
  { title: 'Product', key: 'product_id' },
  { title: 'Units Sold', key: 'total_quantity' },
  { title: 'Revenue', key: 'total_revenue', render: r => `$${r.total_revenue?.toFixed(2)}` },
  { title: 'Profit', key: 'total_profit', render: r => `$${r.total_profit?.toFixed(2)}` },
  { title: 'Avg Price', key: 'avg_price', render: r => `$${r.avg_price?.toFixed(2)}` },
  { title: 'Orders', key: 'orders' },
]

const customerColumns = [
  { title: 'Customer', key: 'customer_name' },
  { title: 'Email', key: 'customer_email' },
  { title: 'Orders', key: 'total_orders' },
  { title: 'Total Spent', key: 'total_spent', render: r => `$${r.total_spent?.toFixed(2)}` },
  { title: 'First Order', key: 'first_order' },
  { title: 'Last Order', key: 'last_order' },
]

const calendarColumns = [
  { title: 'Date', key: 'date' },
  {
    title: 'Flags',
    key: 'flags',
    render: r => h('div', { style: 'display:flex;gap:6px' }, [
      r.is_closed ? h(NTag, { type: 'error', size: 'small' }, { default: () => 'Closed' }) : null,
      r.is_holiday ? h(NTag, { type: 'warning', size: 'small' }, { default: () => 'Holiday' }) : null,
      r.is_festival ? h(NTag, { type: 'info', size: 'small' }, { default: () => 'Festival' }) : null,
    ]),
  },
  { title: 'Note', key: 'note', render: r => r.note || '—' },
  {
    title: '',
    key: 'del',
    render: r => h(NButton, { size: 'tiny', quaternary: true, onClick: () => deleteCalendar(r.id) }, { default: () => 'Remove' }),
  },
]

function rowProps() {
  return { style: 'cursor:pointer' }
}

function addItem() {
  orderForm.value.line_items.push({ product_id: null, quantity: 1, unit_price: null, unit_cost: null, inventory_level: null })
}

function removeItem(i) {
  orderForm.value.line_items.splice(i, 1)
}

function autoFillPrice(productId, index) {
  const product = products.value.find(p => p.product_id === productId)
  if (product) {
    orderForm.value.line_items[index].unit_price = product.base_price
    orderForm.value.line_items[index].unit_cost = product.cost
  }
}

async function submitOrder() {
  orderError.value = null
  const validItems = orderForm.value.line_items.filter(i => i.product_id && i.unit_price != null)
  if (!validItems.length) {
    orderError.value = 'Add at least one item with product and price'
    return
  }
  submitting.value = true
  try {
    await ordersStore.createOrder({
      customer_name: orderForm.value.customer_name || null,
      customer_email: orderForm.value.customer_email || null,
      order_time: new Date(orderForm.value.order_time).toISOString(),
      channel: orderForm.value.channel,
      is_promotion: orderForm.value.is_promotion,
      line_items: validItems,
    })
    orders.value = await ordersStore.fetchOrders()
    summary.value = await ordersStore.fetchSummary()
    showOrderForm.value = false
    orderForm.value = {
      customer_name: '', customer_email: '', order_time: Date.now(),
      channel: null, is_promotion: false,
      line_items: [{ product_id: null, quantity: 1, unit_price: null, unit_cost: null, inventory_level: null }],
    }
  } catch (err) {
    orderError.value = err.response?.data?.detail || 'Failed to create order'
  } finally {
    submitting.value = false
  }
}

async function deleteOrder(orderId) {
  await ordersStore.deleteOrder(orderId)
  orders.value = orders.value.filter(o => o.order_id !== orderId)
  summary.value = await ordersStore.fetchSummary()
}

async function handleImport(data) {
  const file = data.file.file
  importError.value = null
  importResult.value = null
  try {
    importResult.value = await ordersStore.importCSV(file)
    orders.value = await ordersStore.fetchOrders()
    summary.value = await ordersStore.fetchSummary()
  } catch (err) {
    importError.value = err.response?.data?.detail || 'Import failed'
  }
}

async function fetchAggregated() {
  const res = await api.get(`/orders/aggregated?granularity=${granularity.value}`)
  aggregated.value = res.data
  await nextTick()
  drawChart()
}

function drawChart() {
  if (!chartCanvas.value || !aggregated.value.length) return
  import('chart.js').then(({ Chart, registerables }) => {
    Chart.register(...registerables)
    const existing = Chart.getChart(chartCanvas.value)
    if (existing) existing.destroy()
    chartInstance = new Chart(chartCanvas.value, {
      type: 'bar',
      data: {
        labels: aggregated.value.map(d => d.period),
        datasets: [
          { label: 'Revenue', data: aggregated.value.map(d => d.revenue), backgroundColor: 'rgba(22,115,90,0.75)', yAxisID: 'y' },
          { label: 'Profit', data: aggregated.value.map(d => d.profit), backgroundColor: 'rgba(183,121,31,0.75)', yAxisID: 'y' },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'Amount ($)' } } },
      },
    })
  })
}

async function fetchCalendar() {
  const res = await api.get('/orders/calendar')
  calendarEntries.value = res.data
}

async function saveCalendar() {
  await api.post('/orders/calendar', calendarForm.value)
  calendarForm.value.note = ''
  await fetchCalendar()
}

async function deleteCalendar(id) {
  await api.delete(`/orders/calendar/${id}`)
  await fetchCalendar()
}

watch(activeTab, async (tab) => {
  if (tab === 'analytics') { await fetchAggregated() }
  if (tab === 'products') {
    const res = await api.get('/orders/by-product')
    byProduct.value = res.data
  }
  if (tab === 'customers') {
    const res = await api.get('/orders/customers')
    customers.value = res.data
  }
  if (tab === 'calendar') {
    await fetchCalendar()
  }
})

onMounted(async () => {
  orders.value = await ordersStore.fetchOrders()
  summary.value = await ordersStore.fetchSummary()
  products.value = await productsStore.fetchProducts()
})

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1300px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 20px; display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.stat-icon.orders { background:#eaf3f5; color:#326c79; }
.stat-icon.revenue { background:#e7f5ef; color:#16735a; }
.stat-icon.profit { background:#fbf3e1; color:#a0691a; }
.stat-icon.customers { background:#f5ebee; color:#a84d5b; }
.stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 4px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
.line-item-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.calendar-form { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 18px; }
.order-totals { margin-top: 16px; padding: 12px 16px; background: var(--surface-2); border-radius: var(--radius-sm); font-size: 14px; }
code { background: #f0f4ff; color: #6366f1; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
</style>

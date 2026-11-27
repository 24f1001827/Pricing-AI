<template>
  <div class="page">
    <AppNav />
    <div class="content">
      <div class="page-header">
        <div>
          <h1>Product Catalog</h1>
          <p class="subtitle">Manage prices, guardrails, and inventory parameters</p>
        </div>
        <n-button type="primary" @click="openNew">+ Add Product</n-button>
      </div>

      <!-- Optimization objective -->
      <div class="card" style="margin-bottom: 20px">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px">
          <div>
            <p style="font-size: 14px; font-weight: 600; margin: 0 0 4px">Optimization Objective</p>
            <p style="font-size: 12px; color: var(--text-muted); margin: 0">What should the pricing engine optimize for?</p>
          </div>
          <n-radio-group v-model:value="objective" @update:value="updateObjective">
            <n-radio-button value="revenue">Maximize Revenue</n-radio-button>
            <n-radio-button value="profit">Maximize Profit</n-radio-button>
            <n-radio-button value="units">Maximize Units Sold</n-radio-button>
          </n-radio-group>
        </div>
      </div>

      <div class="card">
        <n-data-table
          :columns="columns"
          :data="products"
          :pagination="{ pageSize: 10 }"
          :bordered="false"
          :striped="true"
        />
        <div v-if="products.length === 0" class="empty-state">
          No products yet. Add your first product to get started.
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? 'Edit Product' : 'Add Product'" style="width: 600px">
      <n-form :model="form" label-placement="top">
        <n-grid :cols="2" :x-gap="16">
          <n-form-item-gi label="Product ID *">
            <n-input v-model:value="form.product_id" :disabled="!!editingId" placeholder="e.g. P001" />
          </n-form-item-gi>
          <n-form-item-gi label="Product Name *">
            <n-input v-model:value="form.product_name" placeholder="e.g. Wireless Headphones" />
          </n-form-item-gi>
          <n-form-item-gi label="Category">
            <n-input v-model:value="form.category" placeholder="e.g. Electronics" />
          </n-form-item-gi>
          <n-form-item-gi label="Base Price ($)">
            <n-input-number v-model:value="form.base_price" :min="0" :step="0.01" placeholder="29.99" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Cost per Unit ($)">
            <n-input-number v-model:value="form.cost" :min="0" :step="0.01" placeholder="15.00" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Stock on Hand">
            <n-input-number v-model:value="form.stock_on_hand" :min="0" placeholder="100" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Min Price Guardrail ($)">
            <n-input-number v-model:value="form.min_price" :min="0" :step="0.01" placeholder="Optional floor" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Max Price Guardrail ($)">
            <n-input-number v-model:value="form.max_price" :min="0" :step="0.01" placeholder="Optional ceiling" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Supplier Lead Time (days)">
            <n-input-number v-model:value="form.lead_time_days" :min="1" :max="365" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Target Service Level (0.50–0.99)">
            <n-input-number v-model:value="form.service_level" :min="0.5" :max="0.999" :step="0.01" style="width: 100%" />
          </n-form-item-gi>
        </n-grid>
        <n-alert v-if="formError" type="error" style="margin-top: 12px">{{ formError }}</n-alert>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="cancelForm">Cancel</n-button>
          <n-button type="primary" @click="submitForm">
            {{ editingId ? 'Update' : 'Add Product' }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useProductsStore } from '@/stores/products'
import { useAuthStore } from '@/stores/auth'
import {
  NButton,
  NDataTable,
  NModal,
  NForm,
  NFormItemGi,
  NInput,
  NInputNumber,
  NGrid,
  NAlert,
  NTag,
  NRadioGroup,
  NRadioButton,
  NPopconfirm,
} from 'naive-ui'
import AppNav from '@/components/AppNav.vue'
import api from '@/services/api'

const productsStore = useProductsStore()
const authStore = useAuthStore()

const products = ref([])
const showModal = ref(false)
const editingId = ref(null)
const formError = ref(null)
const objective = ref('revenue')

const blankForm = () => ({
  product_id: '',
  product_name: '',
  category: '',
  base_price: null,
  cost: null,
  min_price: null,
  max_price: null,
  stock_on_hand: 0,
  lead_time_days: 7,
  service_level: 0.95,
})

const form = ref(blankForm())

const columns = [
  {
    title: 'Product ID',
    key: 'product_id',
    render: (row) => h('code', { style: 'background:#f0f4ff;color:#6366f1;padding:2px 6px;border-radius:4px;font-size:12px' }, row.product_id),
  },
  { title: 'Name', key: 'product_name' },
  { title: 'Category', key: 'category', render: (row) => row.category || '—' },
  { title: 'Base Price', key: 'base_price', render: (row) => row.base_price != null ? `$${row.base_price}` : '—' },
  { title: 'Cost', key: 'cost', render: (row) => row.cost != null ? `$${row.cost}` : '—' },
  {
    title: 'Margin',
    key: 'margin',
    render: (row) => {
      if (!row.base_price || row.cost == null) return '—'
      const margin = Math.round(((row.base_price - row.cost) / row.base_price) * 100)
      return h(NTag, { type: margin > 40 ? 'success' : margin > 20 ? 'warning' : 'error', size: 'small' }, { default: () => `${margin}%` })
    },
  },
  { title: 'Stock', key: 'stock_on_hand', render: (row) => row.stock_on_hand ?? 0 },
  { title: 'Lead Time', key: 'lead_time_days', render: (row) => `${row.lead_time_days || 7}d` },
  {
    title: 'Actions',
    key: 'actions',
    render: (row) => h('div', { style: 'display:flex;gap:8px' }, [
      h(NButton, { size: 'tiny', onClick: () => editProduct(row) }, { default: () => 'Edit' }),
      h(NPopconfirm, { onPositiveClick: () => deleteProduct(row.product_id) }, {
        default: () => 'Delete this product?',
        trigger: () => h(NButton, { size: 'tiny', type: 'error', ghost: true }, { default: () => 'Delete' }),
      }),
    ]),
  },
]

onMounted(async () => {
  products.value = await productsStore.fetchProducts()
  await authStore.fetchUser()
  objective.value = authStore.user?.optimization_objective || 'revenue'
})

function openNew() {
  editingId.value = null
  form.value = blankForm()
  showModal.value = true
}

function editProduct(product) {
  editingId.value = product.product_id
  form.value = { ...blankForm(), ...product }
  showModal.value = true
}

function cancelForm() {
  showModal.value = false
  editingId.value = null
  formError.value = null
  form.value = blankForm()
}

async function submitForm() {
  formError.value = null
  if (!form.value.product_id || !form.value.product_name) {
    formError.value = 'Product ID and Name are required'
    return
  }
  try {
    if (editingId.value) {
      await productsStore.updateProduct(editingId.value, form.value)
    } else {
      await productsStore.createProduct(form.value)
    }
    products.value = await productsStore.fetchProducts()
    cancelForm()
  } catch (err) {
    formError.value = err.response?.data?.detail || 'Failed to save'
  }
}

async function deleteProduct(productId) {
  await productsStore.deleteProduct(productId)
  products.value = products.value.filter(p => p.product_id !== productId)
}

async function updateObjective(val) {
  await api.put('/products/settings/objective', { objective: val })
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--surface-2); }
.content { padding: 32px; max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 4px; }
.subtitle { color: var(--text-secondary); font-size: 14px; margin: 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }
.empty-state { text-align: center; padding: 48px 0; color: var(--text-muted); font-size: 14px; }
</style>

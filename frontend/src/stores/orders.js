import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useOrdersStore = defineStore('orders', () => {
  const orders = ref([])
  const summary = ref(null)

  async function fetchOrders(limit = 50) {
    const res = await api.get(`/orders/?limit=${limit}`)
    orders.value = res.data
    return res.data
  }

  async function fetchSummary() {
    const res = await api.get('/orders/summary')
    summary.value = res.data
    return res.data
  }

  async function createOrder(order) {
    const res = await api.post('/orders/', order)
    return res.data
  }

  async function deleteOrder(orderId) {
    await api.delete(`/orders/${orderId}`)
    orders.value = orders.value.filter(o => o.order_id !== orderId)
  }

  async function importCSV(file) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/orders/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    return res.data
  }

  async function downloadTemplate() {
    const res = await api.get('/orders/template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.setAttribute('download', 'orders_template.csv')
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return { orders, summary, fetchOrders, fetchSummary, createOrder, deleteOrder, importCSV, downloadTemplate }
})
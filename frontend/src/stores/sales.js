import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useSalesStore = defineStore('sales', () => {
  const records = ref([])
  const summary = ref(null)

  async function fetchSales() {
    const response = await api.get('/sales/')
    records.value = response.data
    return response.data
  }

  async function fetchSummary() {
    const response = await api.get('/sales/summary')
    summary.value = response.data
    return response.data
  }

  async function logSale(record) {
    const response = await api.post('/sales/', record)
    records.value.unshift(response.data)
    return response.data
  }

  async function importCSV(file) {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/sales/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  }

  async function downloadTemplate() {
    const response = await api.get('/sales/template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'sales_template.csv')
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function deleteSale(recordId) {
    await api.delete(`/sales/${recordId}`)
    records.value = records.value.filter(r => r.id !== recordId)
  }

  return { records, summary, fetchSales, fetchSummary, logSale, importCSV, downloadTemplate, deleteSale }
})
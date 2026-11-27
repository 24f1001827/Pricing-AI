import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useProductsStore = defineStore('products', () => {
  const products = ref([])

  async function fetchProducts() {
    const response = await api.get('/products/')
    products.value = response.data
    return response.data
  }

  async function createProduct(product) {
    const response = await api.post('/products/', product)
    products.value.push(response.data)
    return response.data
  }

  async function updateProduct(productId, data) {
    const response = await api.put(`/products/${productId}`, data)
    const index = products.value.findIndex(p => p.product_id === productId)
    if (index !== -1) products.value[index] = response.data
    return response.data
  }

  async function restockProduct(productId, quantity) {
    const response = await api.post(`/products/${productId}/restock`, { quantity })
    const index = products.value.findIndex(p => p.product_id === productId)
    if (index !== -1) products.value[index] = response.data
    return response.data
  }

  async function applyRecommendedPrice(productId, price) {
    const response = await api.post(`/products/${productId}/apply-price`, { price })
    const index = products.value.findIndex(p => p.product_id === productId)
    if (index !== -1) products.value[index] = response.data
    return response.data
  }

  async function fetchInventorySummary() {
    const response = await api.get('/products/inventory-summary')
    return response.data
  }

  async function deleteProduct(productId) {
    await api.delete(`/products/${productId}`)
    products.value = products.value.filter(p => p.product_id !== productId)
  }

  return {
    products,
    fetchProducts,
    createProduct,
    updateProduct,
    restockProduct,
    applyRecommendedPrice,
    fetchInventorySummary,
    deleteProduct,
  }
})

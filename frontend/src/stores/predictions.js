import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const usePredictionsStore = defineStore('predictions', () => {
  const predictions = ref(null)

  async function getPredictions(uniqueId) {
    const res = await api.get(`/predictions/${uniqueId}`)
    predictions.value = res.data
    return res.data
  }

  async function getLatest() {
    const res = await api.get('/predictions/latest')
    predictions.value = res.data
    return res.data
  }

  return { predictions, getPredictions, getLatest }
})
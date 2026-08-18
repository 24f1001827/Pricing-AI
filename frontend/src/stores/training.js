import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useTrainingStore = defineStore('training', () => {
  const jobs = ref([])

  async function startTraining() {
    const res = await api.post('/training/start')
    return res.data
  }

  async function getStatus(uniqueId) {
    const res = await api.get(`/training/status/${uniqueId}`)
    return res.data
  }

  async function fetchHistory() {
    const res = await api.get('/training/history')
    jobs.value = res.data
    return res.data
  }

  async function checkRetrain() {
    const res = await api.get('/training/should-retrain')
    return res.data
  }

  return { jobs, startTraining, getStatus, fetchHistory, checkRetrain }
})
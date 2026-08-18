import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useUploadStore = defineStore('upload', () => {
  const uploads = ref([])
  const currentUpload = ref(null)

  async function uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/upload/file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    currentUpload.value = response.data
    uploads.value.push(response.data)
    return response.data
  }

  async function startTraining(uniqueId) {
    const response = await api.post(`/training/start/${uniqueId}`)
    return response.data
  }

  async function getTrainingStatus(uniqueId) {
    const response = await api.get(`/training/status/${uniqueId}`)
    return response.data
  }

  return { uploads, currentUpload, uploadFile, startTraining, getTrainingStatus }
})
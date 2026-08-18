import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(null)
  const user = ref(null)

  const isAuthenticated = computed(() => !!token.value)

  function setToken() {
    token.value = true
  }

  function logout() {
    token.value = null
    user.value = null
    api.post('/auth/logout').catch(() => {})
  }

  async function fetchUser() {
    try {
      const response = await api.get('/auth/me')
      user.value = response.data
      token.value = true
    } catch {
      logout()
    }
  }

  return { token, user, isAuthenticated, setToken, logout, fetchUser }
})

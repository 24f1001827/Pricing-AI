<template>
  <main class="registration-page">
    <section class="registration-card">
      <RouterLink class="brand" :to="{ name: 'home' }"><span>PI</span> Pricing Intelligence</RouterLink>
      <div class="heading">
        <p>Secure access</p>
        <h1>Create your account</h1>
        <span>Set up your private Pricing Intelligence workspace.</span>
      </div>

      <div v-if="error" class="message error" role="alert">{{ error }}</div>
      <div v-else-if="!registrationEnabled" class="message" role="status">Account registration is currently unavailable. Contact an administrator for access.</div>

      <form @submit.prevent="submit">
        <label><span>Full name</span><input v-model.trim="form.name" type="text" autocomplete="name" required minlength="2" maxlength="100" :disabled="!registrationEnabled" /></label>
        <label><span>Email address</span><input v-model.trim="form.email" type="email" autocomplete="email" required :disabled="!registrationEnabled" /></label>
        <label><span>Password</span><input v-model="form.password" type="password" autocomplete="new-password" required minlength="8" maxlength="128" :disabled="!registrationEnabled" /></label>
        <label><span>Confirm password</span><input v-model="confirmPassword" type="password" autocomplete="new-password" required minlength="8" maxlength="128" :disabled="!registrationEnabled" /></label>
        <button type="submit" :disabled="loading || !registrationEnabled">{{ loading ? 'Creating account…' : 'Create account' }}</button>
      </form>

      <p class="signin-link">Already have an account? <RouterLink :to="{ name: 'login' }">Sign in</RouterLink></p>
    </section>
  </main>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'

const router = useRouter()
const authStore = useAuthStore()
const form = reactive({ name: '', email: '', password: '' })
const confirmPassword = ref('')
const registrationEnabled = ref(false)
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    registrationEnabled.value = (await api.get('/auth/setup-status')).data.registration_enabled
  } catch {
    error.value = 'The service is unavailable. Please try again shortly.'
  }
})

async function submit() {
  error.value = ''
  if (form.password !== confirmPassword.value) {
    error.value = 'Passwords do not match.'
    return
  }
  loading.value = true
  try {
    await api.post('/auth/register', form)
    await authStore.fetchUser()
    if (!authStore.isAuthenticated) throw new Error('Session could not be established.')
    router.push({ name: 'dashboard' })
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || 'Account creation could not be completed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.registration-page { min-height: 100vh; display: grid; place-items: center; padding: 28px; color: #15202b; background: linear-gradient(135deg, #10251e, #1c4b3b); }
.registration-card { width: min(100%, 460px); padding: 34px; border: 1px solid #dce3e8; border-radius: 14px; background: #fff; box-shadow: 0 20px 50px rgba(0,0,0,.2); }
.brand { display: inline-flex; align-items: center; gap: 9px; color: #173a2d; font-weight: 800; text-decoration: none; }.brand span { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 8px; color: #fff; background: #21815f; font-size: 10px; }
.heading { margin: 30px 0 24px; }.heading p { margin: 0 0 8px; color: #16735a; font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }.heading h1 { margin: 0; font-size: 30px; letter-spacing: -.03em; }.heading > span { display: block; margin-top: 10px; color: #53616d; line-height: 1.5; }
.message { margin-bottom: 16px; padding: 12px; border: 1px solid #c6ddd1; border-radius: 8px; color: #235b45; background: #edf8f3; font-size: 13px; line-height: 1.45; }.message.error { border-color: #f0d38a; color: #7a4d00; background: #fff6df; }
label { display: block; margin-bottom: 15px; } label span { display: block; margin-bottom: 7px; color: #44534c; font-size: 13px; font-weight: 700; } input { box-sizing: border-box; width: 100%; min-height: 44px; padding: 10px 12px; border: 1px solid #cfd8d3; border-radius: 8px; color: #15202b; font: inherit; outline: none; } input:focus { border-color: #16735a; box-shadow: 0 0 0 3px #e7f5ef; } input:disabled { cursor: not-allowed; background: #f4f6f8; }
button { width: 100%; min-height: 46px; margin-top: 6px; border: 0; border-radius: 9px; color: #fff; background: #16735a; font: inherit; font-weight: 750; cursor: pointer; } button:hover:not(:disabled) { background: #105c47; } button:disabled { cursor: not-allowed; opacity: .65; }.signin-link { margin: 22px 0 0; text-align: center; color: #61707c; font-size: 13px; }.signin-link a { color: #16735a; font-weight: 700; text-decoration: none; }
@media (max-width: 520px) { .registration-page { padding: 16px; }.registration-card { padding: 25px; } }
</style>

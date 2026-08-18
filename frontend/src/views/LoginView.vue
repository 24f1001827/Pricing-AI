<template>
  <div class="login-page">
    <section class="brand-panel" aria-label="Platform overview">
      <nav class="brand-nav"><div class="brand-mark">PI</div><span>Pricing Intelligence</span></nav>
      <div class="hero-copy">
        <p class="eyebrow">Commerce AI command center</p>
        <h1>Decisive pricing starts with a clearer view of your business.</h1>
        <p>Bring sales signals, price recommendations, and model performance into one private workspace.</p>
      </div>
      <div class="signal-grid">
        <article v-for="signal in platformSignals" :key="signal.label"><strong>{{ signal.value }}</strong><span>{{ signal.label }}</span></article>
      </div>
    </section>

    <main class="signin-panel">
      <form class="signin-card" @submit.prevent="submit">
        <div class="card-heading">
          <p class="eyebrow">Secure access</p>
          <h2>Welcome back</h2>
          <p>Sign in to review forecasts, recommendations, and training activity.</p>
        </div>

        <div v-if="error" class="login-error" role="alert">{{ error }}</div>

        <label class="field"><span>Email address</span><input v-model.trim="form.email" type="email" autocomplete="email" required /></label>
        <label class="field"><span>Password</span><input v-model="form.password" type="password" autocomplete="current-password" required minlength="8" maxlength="128" /></label>

        <button class="submit-btn" type="submit" :disabled="loading">{{ loading ? 'Please wait…' : 'Sign in' }}</button>
        <RouterLink class="switch-btn" :to="{ name: 'register' }">Need access? Create an account</RouterLink>

        <div class="security-notes" aria-label="Security notes">
          <div class="security-note"><span>01</span><div><strong>Private accounts</strong><p>Access is limited to accounts created for this workspace.</p></div></div>
          <div class="security-note"><span>02</span><div><strong>Secure session</strong><p>Your session is stored in an HTTP-only browser cookie.</p></div></div>
        </div>
      </form>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const error = ref('')
const form = reactive({ email: '', password: '' })
const platformSignals = [
  { value: '01', label: 'private workspace' },
  { value: '24/7', label: 'model monitoring' },
  { value: '100%', label: 'account-controlled access' }
]

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await api.post('/auth/login', form)
    await authStore.fetchUser()
    if (!authStore.isAuthenticated) throw new Error('Session could not be established.')
    router.push({ name: 'dashboard' })
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || 'Sign-in could not be completed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; background: #f4f6f8; color: #15202b; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(420px, .85fr); }
.brand-panel { background: #10251e; color: white; padding: 34px; display: flex; flex-direction: column; justify-content: space-between; gap: 36px; min-height: 100vh; }.brand-nav { display: flex; align-items: center; gap: 12px; font-weight: 800; }.brand-mark { width: 38px; height: 38px; border-radius: 10px; background: #21815f; display: grid; place-items: center; font-size: 11px; letter-spacing: .04em; }.eyebrow { margin: 0 0 8px; color: #687582; font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }.brand-panel .eyebrow { color: #9de0c4; }.hero-copy { max-width: 760px; }.hero-copy h1 { margin: 0; font-size: 46px; line-height: 1.08; letter-spacing: -.04em; }.hero-copy p:last-child { max-width: 620px; color: #c9d6df; line-height: 1.6; margin: 18px 0 0; font-size: 17px; }.signal-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.signal-grid article { border: 1px solid rgba(201,214,223,.18); border-radius: 10px; padding: 18px; background: rgba(255,255,255,.05); }.signal-grid strong { display: block; font-size: 25px; margin-bottom: 6px; }.signal-grid span { color: #c9d6df; font-size: 12px; font-weight: 700; }
.signin-panel { display: grid; place-items: center; padding: 34px; }.signin-card { width: min(100%, 430px); background: white; border: 1px solid #dce3e8; border-radius: 12px; box-shadow: 0 18px 42px rgba(16,24,32,.08); padding: 30px; }.card-heading h2 { margin: 0; font-size: 30px; letter-spacing: -.03em; }.card-heading p:last-child { color: #53616d; line-height: 1.55; margin: 10px 0 24px; }.login-error { background: #fff6df; border: 1px solid #f0d38a; color: #7a4d00; border-radius: 8px; padding: 12px; line-height: 1.45; font-size: 13px; font-weight: 700; margin-bottom: 14px; }.field { display: block; margin-bottom: 15px; }.field span { display: block; margin-bottom: 7px; color: #44534c; font-size: 13px; font-weight: 700; }.field input { width: 100%; min-height: 44px; border: 1px solid #cfd8d3; border-radius: 8px; padding: 10px 12px; color: #15202b; font: inherit; outline: none; }.field input:focus { border-color: #16735a; box-shadow: 0 0 0 3px #e7f5ef; }.submit-btn { width: 100%; min-height: 46px; margin-top: 6px; border: 0; border-radius: 9px; background: #16735a; color: white; font: inherit; font-size: 14px; font-weight: 750; cursor: pointer; }.submit-btn:hover:not(:disabled) { background: #105c47; }.submit-btn:disabled { opacity: .65; cursor: wait; }.switch-btn { width: 100%; margin-top: 12px; border: 0; background: transparent; color: #16735a; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }.security-notes { margin-top: 24px; display: flex; flex-direction: column; gap: 10px; }.security-note { display: grid; grid-template-columns: 34px minmax(0,1fr); gap: 12px; padding: 12px; border: 1px solid #edf1f4; border-radius: 8px; }.security-note > span { width: 30px; height: 30px; border-radius: 7px; background: #edf8f3; color: #16735a; display: grid; place-items: center; font-size: 10px; font-weight: 900; }.security-note strong { display: block; margin-bottom: 3px; font-size: 13px; }.security-note p { margin: 0; color: #61707c; line-height: 1.4; font-size: 12px; }
@media (max-width: 960px) { .login-page { grid-template-columns: 1fr; }.brand-panel { min-height: auto; }.hero-copy h1 { font-size: 34px; } } @media (max-width: 620px) { .brand-panel, .signin-panel { padding: 22px; }.signal-grid { grid-template-columns: 1fr; }.signin-card { padding: 22px; } }
</style>

<template>
  <nav class="navbar">
    <div class="nav-brand" @click="router.push('/dashboard')">
      <div class="brand-icon">PI</div>
      <span class="brand-name">Pricing Intelligence</span>
    </div>
    <div class="nav-links">
      <router-link to="/dashboard" class="nav-link"><n-icon><GridOutline /></n-icon> Dashboard</router-link>
      <router-link to="/products" class="nav-link"><n-icon><CubeOutline /></n-icon> Products</router-link>
      <router-link to="/orders" class="nav-link"><n-icon><ReceiptOutline /></n-icon> Orders</router-link>
    </div>
    <div class="nav-right">
      <div class="user-info">
        <img v-if="authStore.user?.profile_picture" :src="authStore.user.profile_picture" class="avatar" alt="" />
        <div class="user-details">
          <p class="user-name">{{ authStore.user?.name }}</p>
          <p class="user-email">{{ authStore.user?.email }}</p>
        </div>
      </div>
      <n-button quaternary size="small" @click="handleLogout">Sign out</n-button>
    </div>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { NButton, NIcon } from 'naive-ui'
import { CubeOutline, GridOutline, ReceiptOutline } from '@vicons/ionicons5'

const router = useRouter()
const authStore = useAuthStore()
function handleLogout() { authStore.logout(); router.push({ name: 'login' }) }
</script>

<style scoped>
.navbar { background: rgba(255, 255, 255, .94); backdrop-filter: blur(14px); padding: 0 32px; height: 68px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; }
.nav-brand { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.brand-icon { width: 34px; height: 34px; background: var(--primary); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; letter-spacing: .04em; color: white; }
.brand-name { font-size: 15px; font-weight: 750; color: var(--text-primary); letter-spacing: -.3px; }
.nav-links { display: flex; gap: 4px; }
.nav-link { display: flex; align-items: center; gap: 7px; padding: 9px 13px; border-radius: var(--radius-sm); color: var(--text-secondary); font-size: 13px; font-weight: 600; transition: all .15s; text-decoration: none; }
.nav-link:hover { background: var(--surface-2); color: var(--text-primary); }
.nav-link.router-link-active { background: var(--primary-light); color: var(--primary); }
.nav-right { display: flex; align-items: center; gap: 16px; }
.user-info { display: flex; align-items: center; gap: 10px; }
.avatar { width: 34px; height: 34px; border-radius: 50%; border: 2px solid var(--border); }
.user-name { font-size: 13px; font-weight: 650; color: var(--text-primary); margin: 0 0 1px; }
.user-email { font-size: 11px; color: var(--text-muted); margin: 0; }
@media (max-width: 720px) { .navbar { padding: 0 18px; } .brand-name, .user-details { display: none; } .nav-link { padding: 9px; font-size: 0; } .nav-link :deep(.n-icon) { font-size: 18px; } }
</style>

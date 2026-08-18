<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <RouterView />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { NConfigProvider, NMessageProvider } from 'naive-ui'

const themeOverrides = {
  common: {
    primaryColor: '#16735a',
    primaryColorHover: '#105c47',
    primaryColorPressed: '#0b4737',
    borderRadius: '10px',
    fontFamily: 'Inter, -apple-system, sans-serif'
  }
}
</script>

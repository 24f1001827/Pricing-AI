<template>
  <main class="home">
    <nav class="home-nav">
      <button class="brand" @click="router.push('/')" aria-label="Pricing Intelligence home"><span class="brand-mark">PI</span><span>Pricing Intelligence</span></button>
      <button class="sign-in" @click="router.push({ name: 'login' })">Sign in <n-icon><ArrowForwardOutline /></n-icon></button>
    </nav>
    <section class="hero">
      <p class="eyebrow">Pricing decisions, made clear</p>
      <h1>Turn sales signals into pricing confidence.</h1>
      <p class="hero-copy">Pricing Intelligence brings demand forecasting, price optimization, and model monitoring into one focused workspace.</p>
      <div class="hero-actions"><button class="primary-action" @click="router.push({ name: 'login' })">Open your workspace <n-icon><ArrowForwardOutline /></n-icon></button><span>No credit card or setup fee</span></div>
    </section>
    <section class="capabilities" aria-label="Platform capabilities">
      <article v-for="feature in features" :key="feature.title" class="capability"><n-icon class="feature-icon" :component="feature.icon" /><h2>{{ feature.title }}</h2><p>{{ feature.description }}</p></article>
    </section>
    <section class="workflow"><div><p class="eyebrow">One connected workflow</p><h2>From raw data to an approved price recommendation.</h2></div><ol><li v-for="(step, index) in steps" :key="step"><span>0{{ index + 1 }}</span>{{ step }}</li></ol></section>
  </main>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { AnalyticsOutline, ArrowForwardOutline, GitBranchOutline, TrendingUpOutline } from '@vicons/ionicons5'
const router = useRouter()
const features = [
  { icon: AnalyticsOutline, title: 'Forecast demand', description: 'Surface the trends, seasonality, and price sensitivity that shape demand.' },
  { icon: TrendingUpOutline, title: 'Optimize prices', description: 'Evaluate price points against revenue, margin, and units sold objectives.' },
  { icon: GitBranchOutline, title: 'Monitor and adapt', description: 'Detect drift, retrain models, and keep decisions grounded in fresh data.' }
]
const steps = ['Connect your product and order data', 'Train a model tailored to your business', 'Review recommendations with full context']
</script>

<style scoped>
.home { min-height: 100vh; color: #f7fbf9; background: #10251e; overflow: hidden; }
.home::before { content: ''; position: absolute; inset: 0 0 auto; height: 720px; background: radial-gradient(circle at 82% 10%, rgba(76,178,135,.22), transparent 31%), radial-gradient(circle at 28% 24%, rgba(32,112,86,.32), transparent 35%); pointer-events: none; }
.home-nav, .hero, .capabilities, .workflow { position: relative; max-width: 1180px; margin: 0 auto; }.home-nav { height: 82px; padding: 0 28px; display: flex; align-items: center; justify-content: space-between; }
.brand, .sign-in, .primary-action { border: 0; cursor: pointer; font: inherit; }.brand { padding: 0; display: inline-flex; gap: 11px; align-items: center; color: #fff; background: transparent; font-size: 15px; font-weight: 750; }.brand-mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; background: #21815f; font-size: 11px; letter-spacing: .04em; }.sign-in { display: inline-flex; align-items: center; gap: 8px; color: #d7e7df; background: transparent; font-size: 14px; font-weight: 650; }
.hero { padding: 116px 28px 124px; max-width: 930px; text-align: center; }.eyebrow { margin: 0 0 14px; color: #95d7ba; font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }.hero h1 { max-width: 820px; margin: 0 auto; font-size: clamp(42px, 6vw, 72px); line-height: 1.03; letter-spacing: -.055em; }.hero-copy { max-width: 650px; margin: 25px auto 0; color: #c2d6cc; font-size: 18px; line-height: 1.65; }.hero-actions { margin-top: 34px; display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 16px; color: #9fb8ac; font-size: 13px; }.primary-action { display: inline-flex; align-items: center; gap: 9px; border-radius: 10px; padding: 13px 17px; color: #113025; background: #bce5d0; font-size: 14px; font-weight: 750; transition: transform .2s, background .2s; }.primary-action:hover { background: #d9f2e4; transform: translateY(-1px); }
.capabilities { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; border: 1px solid rgba(215,231,223,.16); border-radius: 18px; overflow: hidden; background: rgba(215,231,223,.16); }.capability { padding: 34px; background: rgba(19,49,38,.88); }.feature-icon { color: #91d5b5; font-size: 25px; }.capability h2 { margin: 27px 0 10px; font-size: 17px; letter-spacing: -.025em; }.capability p { margin: 0; color: #b7cbbf; font-size: 14px; line-height: 1.6; }
.workflow { margin-top: 112px; padding: 0 28px 78px; display: grid; grid-template-columns: 1fr 1fr; gap: 80px; }.workflow h2 { max-width: 420px; margin: 0; font-size: 31px; line-height: 1.18; letter-spacing: -.035em; }.workflow ol { margin: 0; padding: 0; list-style: none; border-top: 1px solid rgba(215,231,223,.2); }.workflow li { display: flex; gap: 22px; padding: 20px 0; border-bottom: 1px solid rgba(215,231,223,.2); color: #d2e2d9; font-size: 15px; font-weight: 600; }.workflow li span { color: #7bcaa6; font-size: 12px; font-weight: 800; }
@media (max-width: 720px) { .hero { padding-top: 76px; }.capabilities, .workflow { grid-template-columns: 1fr; }.workflow { gap: 38px; margin-top: 72px; }.capability { padding: 28px; } }
</style>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { currentOrderId, setCurrentOrderId } from '../orderContext'

interface PendingLine { dish_id: number; portions: number }

const orders = ref<any[]>([])
const dishes = ref<any[]>([])
const lines = ref<any[]>([])
const pending = ref<PendingLine[]>([])
const newDish = ref<number | null>(null)
const newPortions = ref<number>(1)
const error = ref('')
const saving = ref(false)

async function loadLines() {
  if (currentOrderId.value == null) { lines.value = []; return }
  lines.value = await api('/orders/' + currentOrderId.value + '/lines')
}

async function selectOrder(id: number) {
  setCurrentOrderId(id)
  pending.value = []
  error.value = ''
  await loadLines()
}

function dishName(id: number) {
  return dishes.value.find(d => d.id === id)?.name ?? ('#' + id)
}

function addPending() {
  error.value = ''
  if (newDish.value == null) { error.value = '请先选择菜品'; return }
  const p = Number(newPortions.value)
  if (!Number.isInteger(p) || p <= 0) { error.value = '份数必须是大于 0 的整数'; return }
  pending.value.push({ dish_id: newDish.value, portions: p })
  newPortions.value = 1
}

function removePending(i: number) {
  pending.value.splice(i, 1)
}

function errDetail(e: unknown) {
  const msg = e instanceof Error ? e.message : String(e)
  try { return JSON.parse(msg).detail ?? msg } catch { return msg }
}

async function saveBatch() {
  if (currentOrderId.value == null || pending.value.length === 0 || saving.value) return
  saving.value = true
  error.value = ''
  try {
    // 整批原子保存：只发这一个写请求，不触发生成备料单、不扣库存。
    lines.value = await api('/orders/' + currentOrderId.value + '/lines', {
      method: 'POST',
      body: JSON.stringify({ lines: pending.value }),
    })
    pending.value = []
  } catch (e) {
    // 失败：后端整批退回，订单行不变；本地草稿保留以便修改后重试。
    error.value = '保存失败，整批已退回：' + errDetail(e)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const [os, ds] = await Promise.all([api<any[]>('/orders'), api<any[]>('/dishes')])
  orders.value = os
  dishes.value = ds
  if (currentOrderId.value == null && os.length) setCurrentOrderId(os[0].id)
  if (currentOrderId.value != null && newDish.value == null && ds.length) newDish.value = ds[0].id
  await loadLines()
})
</script>
<template>
  <h1>订单芯片</h1>
  <p class="sub">门店要货 · 点击芯片切换订单 · 加行整批保存，不影响已落备料单与库存</p>
  <div class="kp-chips" style="margin-bottom:1rem">
    <span v-for="o in orders" :key="o.id" class="kp-chip"
      :class="{ 'kp-chip-active': o.id === currentOrderId }"
      style="cursor:pointer" @click="selectOrder(o.id)">
      {{ o.code }} · {{ o.outlet }} · {{ o.status }}
    </span>
  </div>

  <div class="kp-worksheet">
    <h2>订单行</h2>
    <table>
      <thead><tr><th>菜品</th><th>份数</th></tr></thead>
      <tbody>
        <tr v-for="l in lines" :key="l.id"><td>{{ l.dish_name }}</td><td>{{ l.portions }}</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card" style="margin-top:1rem">
    <h2 style="margin-top:0">再加一行出品份数</h2>
    <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
      <select v-model.number="newDish">
        <option v-for="d in dishes" :key="d.id" :value="d.id">{{ d.code }} · {{ d.name }}</option>
      </select>
      <input v-model.number="newPortions" type="number" min="1" step="1" style="width:110px" />
      <button class="btn" type="button" @click="addPending">加一行</button>
    </div>

    <table v-if="pending.length" style="margin-top:0.75rem">
      <thead><tr><th>待保存菜品</th><th>份数</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(p, i) in pending" :key="i">
          <td>{{ dishName(p.dish_id) }}</td><td>{{ p.portions }}</td>
          <td><button class="btn btn-ghost" type="button" @click="removePending(i)">移除</button></td>
        </tr>
      </tbody>
    </table>

    <div style="margin-top:0.75rem;display:flex;gap:0.5rem;align-items:center">
      <button class="btn" type="button" :disabled="!pending.length || saving" @click="saveBatch">
        保存本批 ({{ pending.length }})
      </button>
      <span v-if="error" class="badge badge-bad">{{ error }}</span>
    </div>
  </div>
</template>

<style scoped>
.kp-chip-active {
  outline: 2px solid #b4632a;
  background: #f6ece2;
}
.btn-ghost {
  background: transparent;
  border: 1px solid #d8cfc4;
  color: #7a6f64;
}
</style>

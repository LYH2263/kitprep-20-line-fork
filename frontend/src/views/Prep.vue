<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { currentOrderId, setCurrentOrderId } from '../orderContext'
const tree = ref<any[]>([])
const data = ref<any>(null)
const shortages = ref<any[]>([])
const orders = ref<any[]>([])

async function loadLatest() {
  if (currentOrderId.value == null) { data.value = null; shortages.value = []; return }
  const q = '?order_id=' + currentOrderId.value
  data.value = await api('/prep/latest' + q)
  shortages.value = data.value.shortages || []
}

async function run() {
  if (currentOrderId.value == null) return
  // 唯一的重算入口：显式点击才现算并落一张新快照，旧快照保留不改。
  data.value = await api('/prep/run?order_id=' + currentOrderId.value, { method: 'POST' })
  shortages.value = data.value.shortages || []
}

onMounted(async () => {
  orders.value = await api('/orders')
  if (currentOrderId.value == null && orders.value.length) setCurrentOrderId(orders.value[0].id)
  tree.value = await api('/bom/tree')
  await loadLatest()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中已落备料单 · 右缺料便利贴 · 只有点「生成备料单」才按当前订单行重算</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:default">
      {{ o.code }} · {{ o.outlet }}
    </span>
  </div>
  <button class="btn" @click="run">生成备料单</button>
  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet" v-if="data && data.id != null">
      <h2>备料单 · {{ data.order?.code }} · {{ data.order?.outlet }}</h2>
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
            <td>{{ l.ingredient_name }}</td><td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.unit }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="kp-worksheet" v-else>
      <h2>备料单</h2>
      <p style="margin:0.5rem 0 0">尚未生成备料单。调整订单行后点击「生成备料单」，才会按当前行现算。</p>
    </section>
    <aside class="kp-shortage-sticky">
      <h2>⚠ 缺料便利贴</h2>
      <div v-for="r in shortages" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
      <p v-if="!shortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
    </aside>
  </div>
</template>

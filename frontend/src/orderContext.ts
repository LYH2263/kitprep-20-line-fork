import { ref } from 'vue'

// 跨页面共享的当前订单 id；刷新后重新取列表首个，不做持久化以免持有脏 id。
export const currentOrderId = ref<number | null>(null)

export function setCurrentOrderId(id: number | null) {
  currentOrderId.value = id
}

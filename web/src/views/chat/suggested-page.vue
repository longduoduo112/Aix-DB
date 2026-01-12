<script lang="ts" setup>
import { NButton } from 'naive-ui'

// 定义 props 接口以获取类型检查
interface Props {
  labels?: string[]
  disabled?: boolean
}

// 使用 withDefaults 提供默认值
const props = withDefaults(defineProps<Props>(), {
  labels: () => [],
  disabled: false,
})

// 自定义事件用于 子父组件传递事件信息
const emit = defineEmits(['suggested'])

// 定义默认按钮文案
const defaultLabels = []

// 计算属性用于决定实际使用的按钮文案
const buttonLabels = computed(() =>
  props.labels.length > 0 ? props.labels : defaultLabels,
)

// 点击事件处理函数
const handleClick = (index: number) => {
  if (props.disabled) {
    return
  }
  emit('suggested', index)
}
</script>

<template>
  <div class="suggested-container">
    <!-- 使用 v-for 指令循环渲染推荐问题，2x2网格布局 -->
    <div
      v-for="(text, index) in buttonLabels"
      :key="index"
      :class="['suggested-item', { 'suggested-item-disabled': disabled }]"
      @click="handleClick(index)"
    >
      {{ text }}
    </div>
  </div>
</template>

<style scoped>
.suggested-container {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 0 16px;
}

.suggested-item {
  background-color: #f5f5f5;
  border-radius: 8px;
  padding: 14px 16px;
  color: #2d3748;
  font-size: 14px;
  line-height: 1.6;
  font-weight: 400;
  font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 52px;
  display: flex;
  align-items: center;
  word-break: break-word;
  letter-spacing: 0;
  text-align: left;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.suggested-item:hover {
  background-color: #ebebeb;
  color: #1a202c;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.suggested-item:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  background-color: #e0e0e0;
}

.suggested-item-disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

.suggested-item-disabled:hover {
  background-color: #f5f5f5;
  transform: none;
  box-shadow: none;
}
</style>

<script lang="ts" setup>
import type { UploadFileInfo } from 'naive-ui'
import { computed, ref } from 'vue'
import FileUploadManager from './FileUploadManager.vue'

const emit = defineEmits(['submit'])

const inputValue = ref('')
const selectedMode = ref<{ label: string, value: string, icon: string, color: string } | null>(null)

// File Upload Logic
const fileUploadRef = ref<InstanceType<typeof FileUploadManager> | null>(null)
const pendingUploadFileInfoList = ref<UploadFileInfo[]>([])

const handleEnter = (e?: KeyboardEvent) => {
  if (e && e.shiftKey) {
    return
  }

  // Allow submit if there is text OR files
  if (!inputValue.value.trim() && pendingUploadFileInfoList.value.length === 0) {
    return
  }

  // Check if files are uploading
  const hasPendingFiles = pendingUploadFileInfoList.value.some((f) => f.status === 'uploading' || (f.status === 'finished' && f.percentage !== 100))
  if (hasPendingFiles) {
    window.$ModalMessage.warning('请等待文件上传完成')
    return
  }

  // Check if files failed
  const hasErrorFiles = pendingUploadFileInfoList.value.some((f) => f.status === 'error')
  if (hasErrorFiles) {
    window.$ModalMessage.warning('存在上传失败的文件，请移除后重试')
    return
  }

  emit('submit', {
    text: inputValue.value,
    mode: selectedMode.value?.value || 'COMMON_QA', // Default to Smart QA if nothing selected
  })
  // We don't clear inputValue here immediately because parent might handle it,
  // but typically we should.
  // However, pendingUploadFileInfoList should probably be cleared by parent or here?
  // Let's clear them here to reset state for next time if we stay on this page (unlikely)
  inputValue.value = ''
  pendingUploadFileInfoList.value = []
}

const chips = [
  { icon: 'i-hugeicons:ai-chat-02', label: '智能问答', value: 'COMMON_QA', color: '#7E6BF2', placeholder: '先思考后回答，解决更有难度的问题' },
  { icon: 'i-hugeicons:database-01', label: '数据问答', value: 'DATABASE_QA', color: '#10b981', placeholder: '连接数据源，进行自然语言查询' },
  { icon: 'i-hugeicons:table-01', label: '表格问答', value: 'FILEDATA_QA', color: '#f59e0b', placeholder: '上传表格文件，进行数据分析和图表生成' },
  { icon: 'i-hugeicons:search-02', label: '深度搜索', value: 'REPORT_QA', color: '#8b5cf6', placeholder: '输入研究主题，生成深度研究报告' },
]

const placeholderText = computed(() => {
  if (selectedMode.value) {
    const mode = chips.find((c) => c.value === selectedMode.value?.value)
    return mode?.placeholder || '先思考后回答，解决更有难度的问题'
  }
  return '先思考后回答，解决更有难度的问题'
})

const handleChipClick = (chip: typeof chips[0]) => {
  selectedMode.value = chip
}

const clearMode = () => {
  selectedMode.value = null
}

const bottomIcons = [
  // Define if needed, or remove if not used in new design
]
</script>

<template>
  <div class="default-page-container">
    <div class="content-wrapper">
      <!-- Title -->
      <div class="header-section">
        <h1 class="page-title">
          <span class="gradient-text">Aix</span> · 智能助手
        </h1>
        <!-- Removed subtitle -->
      </div>

      <!-- Search Box -->
      <div class="input-card">
        <!-- Top: File Uploads -->
        <FileUploadManager
          ref="fileUploadRef"
          v-model="pendingUploadFileInfoList"
          class="w-full"
        />

        <!-- Middle: Input -->
        <div class="input-wrapper w-full">
          <n-input
            v-model:value="inputValue"
            type="textarea"
            :placeholder="placeholderText"
            :autosize="{ minRows: 3, maxRows: 8 }"
            class="custom-input"
            @keydown.enter.prevent="handleEnter"
          />
        </div>

        <!-- Bottom: Footer Actions -->
        <div class="input-footer flex justify-between items-center mt-3">
          <!-- Left: Mode Pill or Chips -->
          <div class="left-actions flex items-center">
            <!-- If mode is selected, show it as a pill -->
            <div
              v-if="selectedMode"
              class="mode-pill"
              :style="{
                color: selectedMode.color,
                borderColor: `${selectedMode.color}30`,
                backgroundColor: `${selectedMode.color}10`,
              }"
            >
              <div
                :class="selectedMode.icon"
                class="text-16"
              ></div>
              <span class="font-medium">{{ selectedMode.label }}</span>
              <div
                class="i-hugeicons:cancel-01 text-14 ml-1 cursor-pointer opacity-60 hover:opacity-100"
                @click.stop="clearMode"
              ></div>
            </div>

            <!-- If NO mode selected, show chips row inside -->
            <div
              v-else
              class="flex items-center gap-2"
            >
              <div
                v-for="chip in chips"
                :key="chip.label"
                class="inner-chip"
                @click="handleChipClick(chip)"
              >
                <div
                  :class="chip.icon"
                  class="text-14"
                  :style="{ color: chip.color }"
                ></div>
                <span>{{ chip.label }}</span>
              </div>
            </div>
          </div>

          <!-- Right: Attachment + Send -->
          <div class="right-actions flex items-center gap-3">
            <!-- Attachment (Paperclip) -->
            <n-dropdown
              :options="fileUploadRef?.options || []"
              trigger="click"
              placement="top-end"
            >
              <div class="action-icon i-hugeicons:attachment-01 text-20 text-gray-400 hover:text-gray-600 cursor-pointer"></div>
            </n-dropdown>

            <!-- Send Button (Purple Circle) -->
            <div
              class="send-btn-circle"
              :class="{ disabled: !inputValue && !pendingUploadFileInfoList.length }"
              @click="handleEnter()"
            >
              <div class="i-hugeicons:arrow-up-01 text-white text-20 font-bold"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Removed External Chips Row -->
    </div>
  </div>
</template>

<style scoped lang="scss">
.default-page-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  width: 100%;
  background-color: #fff;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 800px;
  padding: 0 20px;
}

.header-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 24px; /* Reduced from 40px */
}

.page-title {
  font-size: 36px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.5px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.gradient-text {
  background: linear-gradient(135deg, #7E6BF2 0%, #a78bfa 100%);
  background-clip: text;
  -webkit-text-fill-color: transparent;
  font-weight: 800;
}

.subtitle {
  margin-top: 12px;
  font-size: 16px;
  color: #64748b;
  font-weight: 400;
  letter-spacing: 1px;
}

/* Input Card Styles matching chat.vue */

.input-card {
  width: 100%;
  max-width: 890px;
  background-color: #fff;
  border-radius: 24px;
  box-shadow: 0 10px 40px -10px rgb(0 0 0 / 8%);
  border: 1px solid #f1f5f9;
  padding: 24px;
  position: relative;
  display: flex;
  flex-direction: column;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    box-shadow: 0 20px 50px -12px rgb(0 0 0 / 12%);
    border-color: #e2e8f0;
    transform: translateY(-2px);
  }
}

.input-wrapper {
  width: 100%;
  margin: 8px 0;
}

.custom-input {
  --n-border: none !important;
  --n-border-hover: none !important;
  --n-border-focus: none !important;
  --n-box-shadow: none !important;
  --n-box-shadow-focus: none !important;

  background-color: transparent !important;
  font-size: 16px;
  padding: 0;
  flex: 1;

  :deep(.n-input__textarea-el) {
    padding: 0;
    min-height: 80px; /* Increased default height */
    line-height: 1.6;
    color: #334155;
  }

  :deep(.n-input__placeholder) {
    color: #94a3b8;
  }
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.mode-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 13px;
  border: 1px solid transparent;
  transition: all 0.2s;
  cursor: default;
}

.inner-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
  background-color: #f8fafc;
  border: 1px solid transparent;

  &:hover {
    background-color: #f1f5f9;
    color: #334155;
  }
}

.action-icon {
  font-size: 20px;
  color: #6b7280;
  cursor: pointer;
  transition: color 0.2s;

  &:hover {
    color: #374151;
  }
}

.send-btn-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: #7E6BF2;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgb(126 107 242 / 30%);

  &:hover {
    background-color: #6b5ae0;
    transform: scale(1.05);
  }

  &.disabled {
    background-color: #e5e7eb;
    cursor: not-allowed;
    box-shadow: none;

    .i-hugeicons:arrow-up-01 {
      color: #9ca3af;
    }
  }
}
</style>

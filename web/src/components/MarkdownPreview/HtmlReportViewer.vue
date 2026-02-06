<script lang="ts" setup>
const props = defineProps<{
  htmlContent: string
  ready: boolean
  generating: boolean
}>()

let blobUrl: string | null = null

onUnmounted(() => {
  if (blobUrl) {
    URL.revokeObjectURL(blobUrl)
    blobUrl = null
  }
})

const createBlobUrl = () => {
  if (blobUrl) {
    URL.revokeObjectURL(blobUrl)
  }
  const blob = new Blob([props.htmlContent], { type: 'text/html;charset=utf-8' })
  blobUrl = URL.createObjectURL(blob)
  return blobUrl
}

const previewReport = () => {
  const url = createBlobUrl()
  window.open(url, '_blank')
}

const downloadReport = () => {
  const url = createBlobUrl()
  const a = document.createElement('a')
  a.href = url
  a.download = `report_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// iframe 预览折叠状态
const showPreview = ref(false)
const iframeSrc = computed(() => {
  if (!showPreview.value || !props.ready)
    return ''
  return createBlobUrl() || ''
})

const togglePreview = () => {
  showPreview.value = !showPreview.value
}
</script>

<template>
  <div class="html-report-viewer">
    <!-- 生成中状态 -->
    <div v-if="generating && !ready" class="report-card report-generating">
      <div class="report-icon generating-icon">
        <div class="i-svg-spinners:3-dots-rotate text-20"></div>
      </div>
      <div class="report-info">
        <div class="report-title">正在生成报告...</div>
        <div class="report-desc">HTML 报告内容正在实时生成中，请稍候</div>
      </div>
    </div>

    <!-- 生成完毕状态 -->
    <div v-if="ready" class="report-card report-ready">
      <div class="report-icon ready-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M12 18V12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M9 15L12 12L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="report-info">
        <div class="report-title">HTML 报告已生成</div>
        <div class="report-desc">报告包含数据统计、可视化图表和详细数据表格</div>
      </div>
      <div class="report-actions">
        <button class="report-btn preview-btn" @click="previewReport">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1 12C1 12 5 4 12 4C19 4 23 12 23 12C23 12 19 20 12 20C5 20 1 12 1 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          预览报告
        </button>
        <button class="report-btn download-btn" @click="downloadReport">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M7 10L12 15L17 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 15V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          下载报告
        </button>
        <button class="report-btn toggle-btn" @click="togglePreview">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M8 21H16" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 17V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ showPreview ? '收起预览' : '内嵌预览' }}
        </button>
      </div>
    </div>

    <!-- 内嵌 iframe 预览 -->
    <div v-if="showPreview && ready" class="report-iframe-wrapper">
      <iframe
        :src="iframeSrc"
        class="report-iframe"
        sandbox="allow-scripts allow-same-origin"
        frameborder="0"
      ></iframe>
    </div>
  </div>
</template>

<style scoped>
.html-report-viewer {
  margin: 16px 0;
}

.report-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fafbfc;
  transition: all 0.2s ease;
}

.report-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.report-generating {
  border-color: #c7d2fe;
  background: linear-gradient(135deg, #f0f0ff 0%, #f8f9ff 100%);
}

.report-ready {
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #f0fdf4 0%, #f8fffe 100%);
  flex-wrap: wrap;
}

.report-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  flex-shrink: 0;
}

.generating-icon {
  background: #e0e7ff;
  color: #6366f1;
}

.ready-icon {
  background: #dcfce7;
  color: #16a34a;
}

.report-info {
  flex: 1;
  min-width: 0;
}

.report-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  line-height: 1.4;
}

.report-desc {
  font-size: 13px;
  color: #6b7280;
  margin-top: 2px;
  line-height: 1.4;
}

.report-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.report-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.preview-btn {
  background: #6366f1;
  color: white;
  border-color: #6366f1;
}

.preview-btn:hover {
  background: #4f46e5;
  border-color: #4f46e5;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}

.download-btn {
  background: white;
  color: #374151;
  border-color: #d1d5db;
}

.download-btn:hover {
  background: #f9fafb;
  border-color: #9ca3af;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.toggle-btn {
  background: white;
  color: #6b7280;
  border-color: #e5e7eb;
}

.toggle-btn:hover {
  background: #f3f4f6;
  color: #374151;
  border-color: #d1d5db;
}

.report-iframe-wrapper {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  background: white;
}

.report-iframe {
  width: 100%;
  height: 600px;
  border: none;
  display: block;
}

/* 响应式 */
@media (max-width: 640px) {
  .report-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .report-actions {
    width: 100%;
    margin-top: 8px;
  }

  .report-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>

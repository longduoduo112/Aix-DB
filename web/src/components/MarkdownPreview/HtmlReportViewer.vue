<script lang="ts" setup>
const props = defineProps<{
  htmlContent: string
  ready: boolean
  generating: boolean
}>()

// Tab 类型：source=HTML源码, preview=实时渲染, download=下载
type TabKey = 'source' | 'preview' | 'download'
const activeTab = ref<TabKey>('source')

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

// 当报告生成完毕后自动切换到实时渲染 tab
watch(() => props.ready, (newReady) => {
  if (newReady) {
    activeTab.value = 'preview'
  }
})

// iframe 的 src
const iframeSrc = computed(() => {
  if (activeTab.value !== 'preview' || !props.ready) return ''
  return createBlobUrl() || ''
})

// 下载报告
const downloadReport = () => {
  const url = createBlobUrl()
  const a = document.createElement('a')
  a.href = url
  a.download = `report_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// 在新窗口预览
const openInNewWindow = () => {
  const url = createBlobUrl()
  window.open(url, '_blank')
}

// 源码行数统计
const lineCount = computed(() => {
  if (!props.htmlContent) return 0
  return props.htmlContent.split('\n').length
})

// 源码大小
const contentSize = computed(() => {
  const bytes = new Blob([props.htmlContent]).size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
})
</script>

<template>
  <div class="html-report-viewer">
    <!-- Tab 头部 -->
    <div class="report-tabs">
      <div class="tab-header">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'source' }"
          @click="activeTab = 'source'"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="16 18 22 12 16 6" />
            <polyline points="8 6 2 12 8 18" />
          </svg>
          <span>HTML 源码</span>
          <span v-if="generating" class="tab-badge generating-badge">
            <span class="dot-pulse"></span>
          </span>
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'preview', disabled: !ready }"
          :disabled="!ready"
          @click="ready && (activeTab = 'preview')"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12C1 12 5 4 12 4C19 4 23 12 23 12C23 12 19 20 12 20C5 20 1 12 1 12Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <span>实时渲染</span>
          <span v-if="ready" class="tab-badge ready-badge">✓</span>
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'download', disabled: !ready }"
          :disabled="!ready"
          @click="ready && (activeTab = 'download')"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          <span>下载</span>
        </button>
      </div>

      <!-- 状态信息栏 -->
      <div class="tab-status">
        <template v-if="generating && !ready">
          <span class="status-dot generating"></span>
          <span class="status-text">正在生成中... {{ lineCount }} 行 · {{ contentSize }}</span>
        </template>
        <template v-else-if="ready">
          <span class="status-dot ready"></span>
          <span class="status-text">生成完毕 · {{ lineCount }} 行 · {{ contentSize }}</span>
        </template>
      </div>
    </div>

    <!-- Tab 内容区域 -->
    <div class="tab-content">
      <!-- HTML 源码 Tab -->
      <div v-show="activeTab === 'source'" class="tab-pane source-pane">
        <pre class="source-code"><code>{{ htmlContent }}</code></pre>
        <div v-if="generating && !ready" class="source-cursor">
          <span class="cursor-blink">▌</span>
        </div>
      </div>

      <!-- 实时渲染 Tab -->
      <div v-show="activeTab === 'preview'" class="tab-pane preview-pane">
        <div v-if="!ready" class="preview-placeholder">
          <div class="placeholder-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <path d="M8 21H16" />
              <path d="M12 17V21" />
            </svg>
          </div>
          <p class="placeholder-text">报告生成完毕后将自动渲染预览</p>
        </div>
        <iframe
          v-if="ready && iframeSrc"
          :src="iframeSrc"
          class="preview-iframe"
          sandbox="allow-scripts allow-same-origin"
          frameborder="0"
        ></iframe>
      </div>

      <!-- 下载 Tab -->
      <div v-show="activeTab === 'download'" class="tab-pane download-pane">
        <div v-if="!ready" class="download-placeholder">
          <p class="placeholder-text">等待报告生成完毕...</p>
        </div>
        <div v-else class="download-card">
          <div class="file-info">
            <div class="file-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" />
                <path d="M14 2V8H20" />
              </svg>
            </div>
            <div class="file-details">
              <div class="file-name">report_{{ new Date().toISOString().slice(0, 10) }}.html</div>
              <div class="file-meta">{{ lineCount }} 行 · {{ contentSize }} · HTML 报告</div>
            </div>
          </div>
          <div class="download-actions">
            <button class="action-btn primary-btn" @click="downloadReport">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              下载报告
            </button>
            <button class="action-btn secondary-btn" @click="openInNewWindow">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 13V19C18 19.5304 17.7893 20.0391 17.4142 20.4142C17.0391 20.7893 16.5304 21 16 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V8C3 7.46957 3.21071 6.96086 3.58579 6.58579C3.96086 6.21071 4.46957 6 5 6H11" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              新窗口打开
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.html-report-viewer {
  margin: 16px 0;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

/* Tab 头部 */
.report-tabs {
  background: #f8f9fb;
  border-bottom: 1px solid #e5e7eb;
}

.tab-header {
  display: flex;
  gap: 0;
  padding: 0 12px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.tab-btn:hover:not(.disabled) {
  color: #374151;
  background: rgba(0, 0, 0, 0.03);
}

.tab-btn.active {
  color: #6366f1;
  border-bottom-color: #6366f1;
  background: rgba(99, 102, 241, 0.04);
}

.tab-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  line-height: 1;
}

.generating-badge {
  color: #6366f1;
}

.ready-badge {
  color: #16a34a;
  font-size: 12px;
  font-weight: 700;
}

.dot-pulse {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6366f1;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* 状态信息栏 */
.tab-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  font-size: 12px;
  color: #9ca3af;
  border-top: 1px solid #f0f1f3;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.generating {
  background: #6366f1;
  animation: pulse 1.2s ease-in-out infinite;
}

.status-dot.ready {
  background: #16a34a;
}

.status-text {
  color: #6b7280;
}

/* Tab 内容区域 */
.tab-content {
  position: relative;
}

.tab-pane {
  width: 100%;
}

/* 源码 Tab */
.source-pane {
  position: relative;
  max-height: 500px;
  overflow: auto;
  background: #1e1e2e;
}

.source-code {
  margin: 0;
  padding: 16px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #cdd6f4;
  white-space: pre-wrap;
  word-break: break-all;
  tab-size: 2;
}

.source-code code {
  font-family: inherit;
}

.source-cursor {
  position: sticky;
  bottom: 8px;
  padding: 0 16px;
}

.cursor-blink {
  color: #6366f1;
  font-size: 16px;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 渲染预览 Tab */
.preview-pane {
  min-height: 400px;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.placeholder-icon {
  margin-bottom: 12px;
}

.placeholder-text {
  font-size: 14px;
  color: #9ca3af;
  margin: 0;
}

.preview-iframe {
  width: 100%;
  height: 600px;
  border: none;
  display: block;
}

/* 下载 Tab */
.download-pane {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.download-placeholder {
  padding: 40px 20px;
  text-align: center;
}

.download-card {
  width: 100%;
  padding: 24px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: #f8f9fb;
  border-radius: 10px;
  margin-bottom: 20px;
}

.file-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 12px;
  background: #eef2ff;
  color: #6366f1;
  flex-shrink: 0;
}

.file-details {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.file-meta {
  font-size: 13px;
  color: #9ca3af;
}

.download-actions {
  display: flex;
  gap: 10px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.primary-btn {
  background: #6366f1;
  color: white;
  border-color: #6366f1;
}

.primary-btn:hover {
  background: #4f46e5;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.secondary-btn {
  background: white;
  color: #374151;
  border-color: #d1d5db;
}

.secondary-btn:hover {
  background: #f9fafb;
  border-color: #9ca3af;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* 响应式 */
@media (max-width: 640px) {
  .tab-btn {
    padding: 8px 12px;
    font-size: 12px;
  }

  .tab-btn span:not(.tab-badge) {
    display: none;
  }

  .download-actions {
    flex-direction: column;
  }

  .action-btn {
    justify-content: center;
  }
}
</style>

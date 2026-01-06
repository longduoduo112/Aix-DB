<script lang="ts" setup>
import { useDebounceFn, useInfiniteScroll } from '@vueuse/core'
import { useDialog, useMessage } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import * as GlobalAPI from '@/api'

type RowData = {
  chat_id: string
  key?: string
  question?: string
  create_time?: string
}

interface Props {
  show: boolean
}

const props = withDefaults(defineProps<Props>(), { show: false })

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'delete', ids: string[]): void
}>()

const message = useMessage()
const dialog = useDialog()

const localShow = ref(props.show)
const listData = ref<RowData[]>([])
const loading = ref(false)
const checked = ref<Set<string>>(new Set())
const searchText = ref('')
const scrollEl = ref<HTMLElement | null>(null)

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const noMore = ref(false)

const modalTitle = computed(() => `管理对话记录 · 共${total.value}条`)
const hasSelection = computed(() => checked.value.size > 0)

watch(
  () => props.show,
  (v) => {
    localShow.value = v
    if (v) {
      resetAndFetch()
    }
  },
)

watch(
  () => localShow.value,
  (v) => emit('update:show', v),
)

const fetchData = async (append = false) => {
  if (loading.value || (append && noMore.value)) {
    return
  }

  loading.value = true
  try {
    const res = await GlobalAPI.query_user_qa_record(
      page.value,
      pageSize.value,
      searchText.value || undefined,
      undefined,
    )
    if (!res.ok) {
      throw new Error(`status ${res.status}`)
    }

    const data = await res.json()
    const records = data?.data?.records ?? []
    const totalCount = data?.data?.total_count ?? 0

    listData.value = append ? [...listData.value, ...records] : records
    total.value = totalCount
    noMore.value = listData.value.length >= totalCount || records.length === 0

    if (!append) {
      page.value = 2
    } else if (!noMore.value) {
      page.value += 1
    }
  } catch (err) {
    console.error('Error fetching data:', err)
    message.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

const resetAndFetch = () => {
  page.value = 1
  noMore.value = false
  listData.value = []
  checked.value.clear()
  fetchData(false)
}

const handleSearch = useDebounceFn(() => resetAndFetch(), 300)

useInfiniteScroll(
  scrollEl,
  () => {
    if (!loading.value && !noMore.value) {
      fetchData(true)
    }
  },
  { distance: 80 },
)

const close = () => {
  localShow.value = false
}

const toggleCheck = (id: string) => {
  if (checked.value.has(id)) {
    checked.value.delete(id)
  } else {
    checked.value.add(id)
  }
}

const toggleAll = () => {
  if (checked.value.size === listData.value.length) {
    checked.value.clear()
  } else {
    listData.value.forEach((item) => checked.value.add(item.chat_id))
  }
}

const deleteSelected = () => {
  if (checked.value.size === 0) {
    return
  }
  dialog.warning({
    title: '确认删除',
    content: `确定删除选中的 ${checked.value.size} 条记录吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const ids = Array.from(checked.value)
      try {
        const res = await GlobalAPI.delete_user_record(ids)
        if (res.ok) {
          message.success('删除成功')
          emit('delete', ids)
          listData.value = listData.value.filter((item) => !checked.value.has(item.chat_id))
          total.value = Math.max(total.value - ids.length, 0)
          checked.value.clear()
          if (listData.value.length < pageSize.value && !noMore.value) {
            fetchData(true)
          }
        } else {
          message.error('删除失败')
        }
      } catch (e) {
        message.error('删除请求出错')
      }
    },
  })
}

const deleteOne = (id: string) => {
  dialog.warning({
    title: '确认删除',
    content: '确定删除这条记录吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const res = await GlobalAPI.delete_user_record([id])
        if (res.ok) {
          message.success('删除成功')
          emit('delete', [id])
          listData.value = listData.value.filter((item) => item.chat_id !== id)
          total.value = Math.max(total.value - 1, 0)
          checked.value.delete(id)
          if (listData.value.length < pageSize.value && !noMore.value) {
            fetchData(true)
          }
        }
      } catch (e) {
        message.error('删除请求出错')
      }
    },
  })
}
</script>

<template>
  <n-modal
    v-model:show="localShow"
    :mask-closable="false"
    :on-after-leave="close"
    preset="card"
    :title="modalTitle"
    class="modal w-[900px] h-[720px] flex flex-col rounded-2xl overflow-hidden shadow-2xl"
    :header-style="{ padding: '18px 24px', borderBottom: '1px solid #f2f3f5' }"
    :content-style="{ padding: 0, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    :bordered="false"
  >
    <template #header-extra>
      <n-input
        v-model:value="searchText"
        placeholder="搜索对话记录..."
        clearable
        size="medium"
        class="w-72"
        @update:value="handleSearch"
      >
        <template #prefix>
          <div class="i-hugeicons:search-01 text-gray-400 text-lg"></div>
        </template>
      </n-input>
    </template>

    <div class="flex-1 flex flex-col min-h-0 bg-[#f8f9fb] overflow-hidden relative">
      <!-- Top bar -->
      <div class="sticky top-0 z-10 grid grid-cols-[42px_1fr_160px_56px] gap-3 items-center px-[21px] py-4 bg-white border-b border-gray-100">
        <div class="flex justify-center">
          <n-checkbox
            size="large"
            :checked="listData.length > 0 && checked.size === listData.length"
            :indeterminate="checked.size > 0 && checked.size < listData.length"
            :disabled="listData.length === 0"
            @update:checked="toggleAll"
          />
        </div>
      </div>

      <!-- List -->
      <div
        ref="scrollEl"
        class="flex-1 overflow-y-auto p-5 space-y-3 bg-gradient-to-b from-[#f8f9fb] via-white to-[#f8f9fb]"
      >
        <div
          v-for="item in listData"
          :key="item.chat_id"
          class="card group"
          :class="{ 'card--checked': checked.has(item.chat_id) }"
        >
          <div
            class="card__check"
            @click.stop
          >
            <n-checkbox
              size="large"
              :checked="checked.has(item.chat_id)"
              @update:checked="() => toggleCheck(item.chat_id)"
            />
          </div>

          <div
            class="card__content"
            @click="toggleCheck(item.chat_id)"
          >
            <div class="avatar">
              <div class="i-hugeicons:comment-01"></div>
            </div>
            <div
              class="card__text"
              :title="item.question || item.key"
            >
              {{ item.question || item.key || '无标题' }}
            </div>
          </div>

          <div class="card__time">
            {{ item.create_time || '刚刚' }}
          </div>

          <div class="card__actions">
            <button
              class="btn-icon"
              title="删除"
              @click.stop="deleteOne(item.chat_id)"
            >
              <div class="i-hugeicons:delete-02"></div>
            </button>
          </div>
        </div>

        <div
          v-if="loading"
          class="py-6 flex justify-center"
        >
          <n-spin size="medium" />
        </div>

        <div
          v-if="!loading && listData.length === 0"
          class="empty"
        >
          <div class="i-hugeicons:file-02"></div>
          <span>暂无相关记录</span>
        </div>

        <div
          v-else-if="noMore && listData.length > 0"
          class="bottom-tip"
        >
          - 到底了 -
        </div>
      </div>

      <!-- Footer -->
      <div class="footer flex items-center justify-between px-6 py-4 bg-white border-t border-gray-100">
        <div class="flex items-center gap-2 text-gray-600">
          <span>已选择</span>
          <span class="badge">{{ checked.size }}</span>
          <span>项</span>
        </div>
        <button
          class="btn-danger"
          :disabled="!hasSelection"
          @click="deleteSelected"
        >
          <div class="i-hugeicons:delete-02"></div>
          <span>删除所选</span>
        </button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped lang="scss">
.modal :deep(.n-modal-body-wrapper) {
  padding: 0;
}

.card {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 14px;
  transition: all 0.2s ease;

  &:hover {
    border-color: #dfe4f1;
    box-shadow: 0 8px 24px -10px rgb(31 41 55 / 25%);
  }

  &--checked {
    border-color: #c7d2fe;
    background: #f5f7ff;
  }

}

.card__check {
  width: 42px;
  display: flex;
  justify-content: center;
}

.card__content {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  cursor: pointer;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #f1f5f9;
  display: grid;
  place-items: center;
  color: #94a3b8;
  transition: all 0.2s;
}

.card:hover .avatar {
  background: #eef2ff;
  color: #6366f1;
}

.card__text {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  color: #1f2937;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card__time {
  width: 160px;
  text-align: right;
  font-size: 13px;
  color: #9ca3af;
  padding-right: 8px;
}

.card__actions {
  width: 56px;
  display: flex;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}

.card:hover .card__actions {
  opacity: 1;
}

.btn-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: transparent;
  color: #9ca3af;
  transition: all 0.2s;

  &:hover {
    background: #fef2f2;
    color: #ef4444;
  }
}

.empty {
  padding: 40px 0;
  display: grid;
  place-items: center;
  gap: 12px;
  color: #9ca3af;
  font-size: 15px;

  .i-hugeicons\\:file-02 {
    font-size: 52px;
    opacity: 0.6;
  }
}

.bottom-tip {
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  padding: 10px 0;
}

.footer {
  position: sticky;
  bottom: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
  font-size: 13px;
}

.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 12px;
  background: #fef2f2;
  color: #ef4444;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.2s;
  box-shadow: 0 6px 16px -10px rgb(239 68 68 / 50%);

  &:hover:not(:disabled) {
    background: #fee2e2;
    box-shadow: 0 10px 24px -12px rgb(239 68 68 / 55%);
  }

  &:active:not(:disabled) {
    transform: translateY(1px);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

/* Scrollbar */

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-thumb {
  background: #e5e7eb;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #d1d5db;
}
</style>

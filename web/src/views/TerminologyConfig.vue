<script lang="ts" setup>
import type { FormInst } from 'naive-ui'
import { NButton, NSpace, NTag, NSwitch, useDialog, NCheckboxGroup, NCheckbox, useMessage } from 'naive-ui'
import { h, onMounted, reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { queryTerminologyList, saveTerminology, deleteTerminology, enableTerminology, generateSynonyms } from '@/api/terminology'
import { fetch_datasource_list } from '@/api/datasource'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()

// State
const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const searchWord = ref('')

const datasourceList = ref<any[]>([])

const showModal = ref(false)
const modalType = ref<'add' | 'edit'>('add')
const formRef = ref<FormInst | null>(null)
const formModel = reactive({
  id: 0,
  word: '',
  description: '',
  other_words: [] as string[],
  specific_ds: false,
  datasource_ids: [] as number[],
  enabled: true
})

const generating = ref(false)
const showGenerateModal = ref(false)
const generatedWords = ref<string[]>([])
const selectedGeneratedWords = ref<string[]>([])

const rules = {
  word: { required: true, message: '请输入术语名称', trigger: 'blur' },
  description: { required: true, message: '请输入描述', trigger: 'blur' },
}

// Columns
const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '术语名称', key: 'word', width: 150 },
  { 
    title: '同义词', 
    key: 'other_words',
    render(row: any) {
      if (!row.other_words || row.other_words.length === 0) return '-'
      return row.other_words.map((w: string) => h(NTag, { style: { marginRight: '4px' }, size: 'small' }, { default: () => w }))
    }
  },
  { title: '描述', key: 'description', ellipsis: { tooltip: true } },
  { 
    title: '生效数据源', 
    key: 'datasource_names',
    render(row: any) {
      if (!row.specific_ds) return '全部数据源'
      if (!row.datasource_names || row.datasource_names.length === 0) return '未指定'
      return row.datasource_names.join(', ')
    }
  },
  {
    title: '状态',
    key: 'enabled',
    width: 100,
    render(row: any) {
      return h(NSwitch, {
        value: row.enabled,
        onUpdateValue: (value) => handleEnable(row, value)
      })
    }
  },
  { title: '创建时间', key: 'create_time', width: 180 },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    render(row: any) {
      return h(NSpace, {}, {
        default: () => [
          h(NButton, {
            size: 'small',
            type: 'primary',
            secondary: true,
            onClick: () => handleEdit(row),
          }, { default: () => '编辑' }),
          h(NButton, {
            size: 'small',
            type: 'error',
            secondary: true,
            onClick: () => handleDelete(row),
          }, { default: () => '删除' }),
        ],
      })
    },
  },
]

// Methods
const fetchDatasources = async () => {
    try {
        const res = await fetch_datasource_list()
        const result = await res.json()
        if (result.code === 200) {
            datasourceList.value = result.data.map((ds: any) => ({
                label: ds.name,
                value: ds.id
            }))
        }
    } catch (e) {
        console.error(e)
    }
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await queryTerminologyList(page.value, pageSize.value, searchWord.value)
    const result = await res.json()
    if (result.code === 200) {
      list.value = result.data.records
      total.value = result.data.total_count
    } else {
      message.error(result.msg || '查询失败')
    }
  } catch (e) {
    console.error(e)
    message.error('网络错误')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchData()
}

const handlePageChange = (p: number) => {
  page.value = p
  fetchData()
}

const handleAdd = () => {
  modalType.value = 'add'
  formModel.id = 0
  formModel.word = ''
  formModel.description = ''
  formModel.other_words = []
  formModel.specific_ds = false
  formModel.datasource_ids = []
  formModel.enabled = true
  showModal.value = true
}

const handleEdit = (row: any) => {
  modalType.value = 'edit'
  formModel.id = row.id
  formModel.word = row.word
  formModel.description = row.description
  formModel.other_words = row.other_words || []
  formModel.specific_ds = row.specific_ds
  formModel.datasource_ids = row.datasource_ids || [] // Note: ensure backend returns ids list
  formModel.enabled = row.enabled
  showModal.value = true
}

const handleDelete = (row: any) => {
  dialog.warning({
    title: '警告',
    content: `确定删除术语 ${row.word} 吗？`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const res = await deleteTerminology([row.id])
        const result = await res.json()
        if (result.code === 200) {
          message.success('删除成功')
          fetchData()
        } else {
          message.error(result.msg || '删除失败')
        }
      } catch (e) {
        console.error(e)
        message.error('网络错误')
      }
    },
  })
}

const handleEnable = async (row: any, value: boolean) => {
    try {
        const res = await enableTerminology(row.id, value)
        const result = await res.json()
    if (result.code === 200) {
      message.success(value ? '已启用' : '已禁用')
      row.enabled = value
    } else {
      message.error(result.msg || '操作失败')
    }
  } catch (e) {
    console.error(e)
    message.error('网络错误')
  }
}

const handleSave = async () => {
  formRef.value?.validate(async (errors) => {
    if (!errors) {
      if (formModel.specific_ds && formModel.datasource_ids.length === 0) {
          message.error('请选择生效数据源')
          return
      }

      try {
        const res = await saveTerminology(formModel)
        const result = await res.json()
        if (result.code === 200) {
          message.success('保存成功')
          showModal.value = false
          fetchData()
        } else {
          message.error(result.msg || '保存失败')
        }
      } catch (e) {
        console.error(e)
        message.error('网络错误')
      }
    }
  })
}

const handleGenerate = async () => {
    if (!formModel.word) {
        message.warning('请先输入术语名称')
        return
    }
    generating.value = true
    try {
        const res = await generateSynonyms(formModel.word)
        const result = await res.json()
        if (result.code === 200) {
            generatedWords.value = result.data
            selectedGeneratedWords.value = [...result.data]
            showGenerateModal.value = true
        } else {
            message.error(result.msg || '生成失败')
        }
    } catch (e) {
        console.error(e)
        message.error('网络错误')
    } finally {
        generating.value = false
    }
}

const confirmGenerate = () => {
    const currentWords = new Set(formModel.other_words)
    let addedCount = 0
    selectedGeneratedWords.value.forEach(w => {
        if (!currentWords.has(w)) {
            formModel.other_words.push(w)
            currentWords.add(w)
            addedCount++
        }
    })
    message.success(`已添加 ${addedCount} 个同义词`)
    showGenerateModal.value = false
}

onMounted(() => {
  fetchData()
  fetchDatasources()
})
</script>

<template>
  <div class="terminology-manager">
    <div class="header">
      <div class="title-section">
        <div class="i-carbon-term text-24 text-primary mr-2"></div>
        <h2>术语配置</h2>
      </div>
      <div class="actions">
        <n-input
          v-model:value="searchWord"
          placeholder="搜索术语..."
          clearable
          class="search-input"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <div class="i-carbon-search text-gray-400"></div>
          </template>
        </n-input>
        <n-button
          secondary
          @click="handleSearch"
        >
          <template #icon>
            <div class="i-carbon-search"></div>
          </template>
          搜索
        </n-button>
        <n-button
          type="primary"
          @click="handleAdd"
        >
          <template #icon>
            <div class="i-carbon-add"></div>
          </template>
          添加术语
        </n-button>
      </div>
    </div>

    <div class="content">
      <n-data-table
        :columns="columns"
        :data="list"
        :loading="loading"
        :pagination="false"
        class="term-table"
      />
      <div
        v-if="total > 0"
        class="pagination-container"
      >
        <n-pagination
          v-model:page="page"
          :page-size="pageSize"
          :item-count="total"
          @update:page="handlePageChange"
        />
      </div>
    </div>

    <n-modal
      v-model:show="showModal"
      preset="dialog"
      :title="modalType === 'add' ? '添加术语' : '编辑术语'"
      style="width: 600px"
    >
      <n-form
        ref="formRef"
        :model="formModel"
        :rules="rules"
        label-placement="left"
        label-width="100"
        require-mark-placement="right-hanging"
        class="mt-4"
      >
        <n-form-item label="术语名称" path="word">
          <n-input v-model:value="formModel.word" placeholder="请输入术语名称" />
        </n-form-item>
        
        <n-form-item label="同义词" path="other_words">
            <n-space vertical style="width: 100%">
                <n-dynamic-tags v-model:value="formModel.other_words" />
                <n-button 
                    size="small" 
                    type="primary" 
                    ghost 
                    :loading="generating"
                    @click="handleGenerate"
                >
                    <template #icon>
                        <div class="i-carbon-magic-wand"></div>
                    </template>
                    AI 自动生成
                </n-button>
            </n-space>
        </n-form-item>

        <n-form-item label="描述" path="description">
          <n-input
            v-model:value="formModel.description"
            type="textarea"
            placeholder="请输入描述"
            :autosize="{ minRows: 3, maxRows: 5 }"
          />
        </n-form-item>
        
        <n-form-item label="生效数据源" path="specific_ds">
            <n-space vertical>
                <n-switch v-model:value="formModel.specific_ds">
                    <template #checked>指定数据源</template>
                    <template #unchecked>全部数据源</template>
                </n-switch>
                <n-select
                    v-if="formModel.specific_ds"
                    v-model:value="formModel.datasource_ids"
                    multiple
                    filterable
                    placeholder="请选择数据源"
                    :options="datasourceList"
                />
            </n-space>
        </n-form-item>

      </n-form>
      <template #action>
        <n-space>
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" @click="handleSave">保存</n-button>
        </n-space>
      </template>
    </n-modal>
    
    <n-modal
      v-model:show="showGenerateModal"
      preset="dialog"
      title="选择生成的同义词"
      style="width: 500px"
    >
        <n-checkbox-group v-model:value="selectedGeneratedWords">
            <n-space>
                <n-checkbox v-for="word in generatedWords" :key="word" :value="word" :label="word" />
            </n-space>
        </n-checkbox-group>
        <template #action>
            <n-space>
                <n-button @click="showGenerateModal = false">取消</n-button>
                <n-button type="primary" @click="confirmGenerate">确定添加</n-button>
            </n-space>
        </template>
    </n-modal>
  </div>
</template>

<style lang="scss" scoped>
.terminology-manager {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #fff;

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    border-bottom: 1px solid #f3f4f6;

    .title-section {
      display: flex;
      align-items: center;

      h2 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
        color: #1f2937;
      }
    }

    .actions {
      display: flex;
      align-items: center;
      gap: 12px;

      .search-input {
        width: 260px;
      }
    }
  }

  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 16px 24px;

    .term-table {
      flex: 1;
    }

    .pagination-container {
      margin-top: 16px;
      display: flex;
      justify-content: flex-end;
    }
  }
}
</style>

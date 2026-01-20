<script lang="ts" setup>
import type { FormInst, FormRules } from 'naive-ui'
import { computed, reactive, ref, watch } from 'vue'
import {
  add_datasource,
  check_datasource_connection,
  fetch_datasource_detail,
  fetch_datasource_table_list,
  fetch_tables_by_conf,
  sync_datasource_tables,
  update_datasource,
} from '@/api/datasource'

interface Props {
  show: boolean
  datasource?: any
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  datasource: null,
})

const emit = defineEmits(['update:show', 'success'])

// 数据源类型选项
const datasourceTypes = [
  { label: 'MySQL', value: 'mysql' },
  { label: 'PostgreSQL', value: 'pg' },
  { label: 'Oracle', value: 'oracle' },
  { label: 'SQL Server', value: 'sqlServer' },
  { label: 'ClickHouse', value: 'ck' },
  { label: '达梦', value: 'dm' },
  { label: 'Apache Doris', value: 'doris' },
  { label: 'AWS Redshift', value: 'redshift' },
  { label: 'Elasticsearch', value: 'es' },
  { label: 'Kingbase', value: 'kingbase' },
  { label: 'StarRocks', value: 'starrocks' },
]

// 需要 Schema 的数据源类型
const needSchemaTypes = ['sqlServer', 'pg', 'oracle', 'dm', 'redshift', 'kingbase']

// 表单引用
const formRef = ref<FormInst | null>(null)

// 表单数据
const formData = reactive({
  name: '',
  description: '',
  type: 'mysql',
  host: '',
  port: 3306,
  username: '',
  password: '',
  database: '',
  dbSchema: '',
  extraJdbc: '',
  timeout: 30,
  mode: 'service_name', // Oracle 连接模式
})

// 表单验证规则
const rules: FormRules = {
  name: [
    { required: true, message: '请输入数据源名称', trigger: 'blur' },
    {
      validator: (rule: any, value: string) => {
        if (!value) {
          return true
        }
        if (value.length < 1 || value.length > 50) {
          return new Error('名称长度在1-50个字符')
        }
        return true
      },
      trigger: 'blur',
    },
  ],
  type: [
    { required: true, message: '请选择数据源类型', trigger: 'change' },
  ],
  host: [
    { required: true, message: '请输入主机地址', trigger: 'blur' },
  ],
  port: [
    {
      validator: (rule: any, value: any) => {
        if (value === null || value === undefined || value === '' || value === 0) {
          return new Error('请输入端口号')
        }
        const num = Number(value)
        if (Number.isNaN(num)) {
          return new Error('请输入有效的端口号')
        }
        if (num < 1 || num > 65535) {
          return new Error('端口号范围1-65535')
        }
        return true
      },
      trigger: ['blur', 'input'],
    },
  ],
  database: [
    { required: true, message: '请输入数据库名', trigger: 'blur' },
  ],
  dbSchema: [
    { required: true, message: '请输入Schema', trigger: 'blur' },
  ],
}

// 状态
const loading = ref(false)
const testing = ref(false)
const currentStep = ref(1) // 1: 基本信息, 2: 选择表
const tableList = ref<any[]>([])
const selectedTables = ref<string[]>([])
const tableListLoading = ref(false)

// 是否显示 Schema 字段
const showSchema = computed(() => needSchemaTypes.includes(formData.type))

// 是否显示 Oracle 连接模式
const showOracleMode = computed(() => formData.type === 'oracle')

// 监听数据源类型变化，设置默认端口
watch(() => formData.type, (newType) => {
  const defaultPorts: Record<string, number> = {
    mysql: 3306,
    pg: 5432,
    oracle: 1521,
    sqlServer: 1433,
    ck: 8123,
    dm: 5236,
    doris: 9030,
    redshift: 5439,
    es: 9200,
    kingbase: 54321,
    starrocks: 9030,
  }
  if (defaultPorts[newType]) {
    formData.port = defaultPorts[newType]
  }
})

// 初始化表单
const initForm = async () => {
  if (props.datasource) {
    // 编辑模式
    formData.name = props.datasource.name || ''
    formData.description = props.datasource.description || ''
    formData.type = props.datasource.type || 'mysql'

    try {
      const response = await fetch_datasource_detail(props.datasource.id)
      if (response.ok) {
        const result = await response.json()
        if (result.code === 200 && result.data) {
          const data = result.data
          formData.name = data.name
          formData.description = data.description
          formData.type = data.type
          if (data.configuration) {
            try {
              const config = JSON.parse(data.configuration)
              Object.assign(formData, config)
            } catch (e) {
              console.error('解析配置信息失败:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('获取数据源详情失败:', error)
    }
  } else {
    // 新建模式
    Object.assign(formData, {
      name: '',
      description: '',
      type: 'mysql',
      host: '',
      port: 3306,
      username: '',
      password: '',
      database: '',
      dbSchema: '',
      extraJdbc: '',
      timeout: 30,
      mode: 'service_name',
    })
  }
  currentStep.value = 1
  selectedTables.value = []
  tableList.value = []
}

// 测试连接
const testConnection = async () => {
  if (!formRef.value) {
    return
  }
  await formRef.value.validate((errors) => {
    if (errors) {
      window.$ModalMessage.error('请检查表单信息')
      return false
    }
  })

  testing.value = true
  try {
    const config = buildConfiguration()
    const response = await check_datasource_connection({
      id: props.datasource?.id,
      type: formData.type,
      configuration: JSON.stringify(config),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    if (result.code === 200 && result.data?.connected) {
      window.$ModalMessage.success('连接成功')
      await fetchTableList()
    } else {
      window.$ModalMessage.error(result.data?.error_message || '连接失败')
    }
  } catch (error) {
    console.error('测试连接失败:', error)
    window.$ModalMessage.error('测试连接失败')
  } finally {
    testing.value = false
  }
}

// 获取表列表
const fetchTableList = async () => {
  tableListLoading.value = true
  try {
    const config = buildConfiguration()
    const response = await fetch_tables_by_conf({
      type: formData.type,
      configuration: JSON.stringify(config),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    if (result.code === 200) {
      tableList.value = result.data || []
      // 如果是编辑模式，加载已选中的表
      if (props.datasource?.id) {
        const tablesResponse = await fetch_datasource_table_list(props.datasource.id)

        if (!tablesResponse.ok) {
          throw new Error(`HTTP error! status: ${tablesResponse.status}`)
        }

        const tablesResult = await tablesResponse.json()
        if (tablesResult.code === 200) {
          selectedTables.value = tablesResult.data
            .filter((t: any) => t.checked)
            .map((t: any) => t.table_name)
        }
      }
    } else {
      window.$ModalMessage.error(result.msg || '获取表列表失败')
    }
  } catch (error) {
    console.error('获取表列表失败:', error)
    window.$ModalMessage.error('获取表列表失败')
  } finally {
    tableListLoading.value = false
  }
}

// 构建配置对象
const buildConfiguration = () => {
  return {
    host: formData.host,
    port: formData.port,
    username: formData.username,
    password: formData.password,
    database: formData.database,
    dbSchema: formData.dbSchema || formData.database,
    extraJdbc: formData.extraJdbc,
    timeout: formData.timeout,
    mode: formData.mode,
  }
}

// 下一步（选择表）
const handleNext = async () => {
  if (!formRef.value) {
    return
  }
  await formRef.value.validate(async (errors) => {
    if (errors) {
      return
    }
    // 先测试连接
    await testConnection()
    if (tableList.value.length > 0) {
      currentStep.value = 2
    }
  })
}

// 上一步
const handlePrev = () => {
  currentStep.value = 1
}

// 全选/取消全选
const handleSelectAll = () => {
  if (selectedTables.value.length === tableList.value.length) {
    selectedTables.value = []
  } else {
    selectedTables.value = tableList.value.map((table) => table.tableName)
  }
}

// 是否全选
const isAllSelected = computed(() => {
  return tableList.value.length > 0 && selectedTables.value.length === tableList.value.length
})

// 保存数据源
const handleSave = async () => {
  if (selectedTables.value.length === 0) {
    window.$ModalMessage.warning('请至少选择一个表')
    return
  }

  loading.value = true
  try {
    const config = buildConfiguration()
    // TODO: 加密配置
    const configuration = JSON.stringify(config)

    const tables = selectedTables.value.map((tableName) => {
      const table = tableList.value.find((t) => t.tableName === tableName)
      return {
        table_name: tableName,
        table_comment: table?.tableComment || '',
      }
    })

    const requestData = {
      name: formData.name,
      description: formData.description,
      type: formData.type,
      type_name: datasourceTypes.find((t) => t.value === formData.type)?.label || formData.type,
      configuration,
      tables,
    }

    let response
    let dsId = props.datasource?.id
    if (props.datasource?.id) {
      // 更新
      response = await update_datasource({
        id: props.datasource.id,
        ...requestData,
      })
    } else {
      // 新建
      response = await add_datasource(requestData)
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const result = await response.json()
    if (result.code === 200) {
      dsId = result.data?.id || dsId
      if (dsId) {
        try {
          await sync_datasource_tables(dsId, tables)
        } catch (syncErr) {
          console.error('同步表列表失败:', syncErr)
        }
      }

      window.$ModalMessage.success(props.datasource?.id ? '更新成功' : '创建成功')
      emit('success')
      handleClose()
    } else {
      window.$ModalMessage.error(result.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存数据源失败:', error)
    window.$ModalMessage.error('保存数据源失败')
  } finally {
    loading.value = false
  }
}

// 关闭对话框
const handleClose = () => {
  emit('update:show', false)
  initForm()
}

// 监听 show 变化
watch(() => props.show, (newVal) => {
  if (newVal) {
    initForm()
  }
})
</script>

<template>
  <n-modal
    :show="show"
    :mask-closable="false"
    preset="card"
    :title="datasource ? '编辑数据源' : '新建数据源'"
    class="datasource-modal"
    :style="{ width: '700px' }"
    @update:show="(val) => emit('update:show', val)"
    @close="handleClose"
  >
    <div class="steps-wrapper">
      <n-steps
        :current="currentStep"
        size="small"
      >
        <n-step
          title="连接配置"
          description="配置数据库连接信息"
        />
        <n-step
          title="选择表"
          description="选择需要管理的表"
        />
      </n-steps>
    </div>

    <n-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-placement="left"
      label-width="100px"
      require-mark-placement="right-hanging"
      class="form-content"
    >
      <!-- 第一步：基本信息 -->
      <div
        v-show="currentStep === 1"
        class="step-content"
      >
        <n-grid
          :x-gap="24"
          :cols="1"
        >
          <n-grid-item>
            <n-form-item
              label="数据源名称"
              path="name"
            >
              <n-input
                v-model:value="formData.name"
                placeholder="例如：主业务库"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="描述">
              <n-input
                v-model:value="formData.description"
                type="textarea"
                placeholder="请输入描述（可选）"
                :rows="2"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item
              label="数据源类型"
              path="type"
            >
              <n-select
                v-model:value="formData.type"
                :options="datasourceTypes"
                placeholder="请选择数据源类型"
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <n-divider dashed>
          连接信息
        </n-divider>

        <n-grid
          :x-gap="24"
          :cols="2"
        >
          <n-grid-item>
            <n-form-item
              label="主机地址"
              path="host"
            >
              <n-input
                v-model:value="formData.host"
                placeholder="127.0.0.1"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item
              label="端口"
              path="port"
            >
              <n-input-number
                v-model:value="formData.port"
                :min="1"
                :max="65535"
                placeholder="3306"
                :show-button="false"
                style="width: 100%"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="用户名">
              <n-input
                v-model:value="formData.username"
                placeholder="root"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="密码">
              <n-input
                v-model:value="formData.password"
                type="password"
                placeholder="请输入密码"
                show-password-on="click"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item
              label="数据库名"
              path="database"
            >
              <n-input
                v-model:value="formData.database"
                placeholder="请输入数据库名"
                clearable
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="showSchema">
            <n-form-item
              label="Schema"
              path="dbSchema"
            >
              <n-input
                v-model:value="formData.dbSchema"
                placeholder="public"
                clearable
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <div v-if="showOracleMode || formData.extraJdbc || formData.timeout !== 30">
          <n-divider dashed>
            高级设置
          </n-divider>
          <n-grid
            :x-gap="24"
            :cols="1"
          >
            <n-grid-item v-if="showOracleMode">
              <n-form-item
                label="连接模式"
                path="mode"
              >
                <n-radio-group v-model:value="formData.mode">
                  <n-radio value="service_name">
                    Service Name
                  </n-radio>
                  <n-radio value="sid">
                    SID
                  </n-radio>
                </n-radio-group>
              </n-form-item>
            </n-grid-item>
            <n-grid-item>
              <n-form-item label="额外参数">
                <n-input
                  v-model:value="formData.extraJdbc"
                  placeholder="例如: useSSL=false&serverTimezone=UTC"
                  clearable
                />
              </n-form-item>
            </n-grid-item>
            <n-grid-item>
              <n-form-item label="超时时间">
                <n-input-number
                  v-model:value="formData.timeout"
                  :min="1"
                  :max="300"
                  placeholder="默认30秒"
                  style="width: 200px"
                >
                  <template #suffix>
                    秒
                  </template>
                </n-input-number>
              </n-form-item>
            </n-grid-item>
          </n-grid>
        </div>
      </div>

      <!-- 第二步：选择表 -->
      <div
        v-show="currentStep === 2"
        class="step-content"
      >
        <div class="table-selection-header">
          <n-text>
            已选择 <span class="highlight">{{ selectedTables.length }}</span> / {{ tableList.length }} 个表
          </n-text>
          <n-button
            size="small"
            secondary
            @click="handleSelectAll"
          >
            {{ isAllSelected ? '取消全选' : '全选' }}
          </n-button>
        </div>

        <n-spin :show="tableListLoading">
          <div class="table-list-wrapper">
            <n-checkbox-group v-model:value="selectedTables">
              <n-grid
                :x-gap="12"
                :y-gap="12"
                :cols="2"
              >
                <n-grid-item
                  v-for="table in tableList"
                  :key="table.tableName"
                >
                  <div class="table-item">
                    <n-checkbox
                      :value="table.tableName"
                      style="width: 100%"
                    >
                      <div class="checkbox-content">
                        <span class="table-name">{{ table.tableName }}</span>
                        <span
                          v-if="table.tableComment"
                          class="table-comment"
                        >{{ table.tableComment }}</span>
                      </div>
                    </n-checkbox>
                  </div>
                </n-grid-item>
              </n-grid>
            </n-checkbox-group>
            <n-empty
              v-if="tableList.length === 0"
              description="未找到数据表"
            />
          </div>
        </n-spin>
      </div>
    </n-form>

    <template #footer>
      <div class="modal-actions">
        <div class="left">
          <n-button
            v-if="currentStep === 1"
            secondary
            :loading="testing"
            @click="testConnection"
          >
            测试连接
          </n-button>
        </div>
        <div class="right">
          <n-button @click="handleClose">
            取消
          </n-button>

          <n-button
            v-if="currentStep === 2"
            @click="handlePrev"
          >
            上一步
          </n-button>

          <n-button
            v-if="currentStep === 1"
            type="primary"
            @click="handleNext"
          >
            下一步
          </n-button>

          <n-button
            v-if="currentStep === 2"
            type="primary"
            :loading="loading"
            @click="handleSave"
          >
            保存
          </n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style lang="scss" scoped>
.steps-wrapper {
  margin-bottom: 24px;
  padding: 0 12px;
}

.form-content {
  padding: 0 12px;
}

.step-content {
  min-height: 300px;
}

.table-selection-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 8px;

  .highlight {
    color: #18a058;
    font-weight: 600;
  }
}

.table-list-wrapper {
  max-height: 400px;
  overflow-y: auto;
  padding: 4px;

  .table-item {
    padding: 8px;
    border-radius: 6px;
    border: 1px solid #eee;
    transition: all 0.2s;

    &:hover {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    .checkbox-content {
      display: flex;
      flex-direction: column;
      width: 100%;
      overflow: hidden;

      .table-name {
        font-weight: 500;
        color: #374151;
        margin-bottom: 2px;
      }

      .table-comment {
        font-size: 12px;
        color: #9ca3af;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }
}

.modal-actions {
  display: flex;
  justify-content: space-between;
  width: 100%;

  .right {
    display: flex;
    gap: 12px;
  }
}
</style>

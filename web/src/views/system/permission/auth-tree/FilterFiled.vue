<template>
  <div class="white-nowrap">
    <div
      class="filed"
      :style="computedWidth"
      @mouseover="showDel = true"
      @mouseleave="showDel = false"
    >
      <n-select
        v-model:value="activeNameId"
        filterable
        placeholder="Conditional Filtering"
        style="width: 200px"
        :options="dimensionOptions"
        @update:value="selectItem"
      />
      <template v-if="item.field_id">
        <n-select
          v-model:value="item.filter_type"
          style="width: 120px; margin-left: 8px"
          placeholder="Filter Type"
          :options="filterList"
          @update:value="filterTypeChange"
        />
        <n-select
          v-if="['null', 'not_null', 'empty', 'not_empty'].includes(item.term)"
          v-model:value="item.term"
          style="width: 280px; margin-left: 8px"
          placeholder="Please Select"
          :options="operators"
        />
        <div v-else style="display: flex; margin-left: 8px; width: 280px;">
           <n-input-group>
              <n-select
                  v-model:value="item.term"
                  style="width: 100px"
                  placeholder="Select"
                  :options="operators"
                />
              <n-input
                v-model:value="item.value"
                style="flex: 1"
                placeholder="Please Enter"
                clearable
              />
           </n-input-group>
        </div>
      </template>
      <n-icon v-if="showDel" class="font16" @click="emits('del')">
        <Trash />
      </n-icon>
    </div>
  </div>
</template>

<script lang="ts">
export interface Item {
  term: string
  field_id: string
  filter_type: string
  enum_value: string
  name: string
  value: any
}
</script>

<script lang="ts" setup>
import {
  NIcon,
  NInput,
  NInputGroup,
  NSelect,
} from 'naive-ui'
import { computed, inject, onBeforeMount, ref, toRefs, type Ref } from 'vue'
import { allOptions } from '../options'
import Trash from '~icons/material-symbols/delete-outline'

export interface sysVariable {
  label: string
  value: string
  type: string
}

type Props = {
  index: number
  item: Item
}

const props = withDefaults(defineProps<Props>(), {
  index: 0,
  item: () => ({
    term: '',
    field_id: '',
    filter_type: '',
    enum_value: '',
    name: '',
    value: null,
  }) as Item,
})

const t = (key: string, args?: any) => {
  const map: Record<string, string> = {
    'permission.conditional_filtering': '条件过滤',
    'common.empty': '为空',
    'common.not_empty': '不为空',
    'common.is_null': '为空值',
    'common.is_not_null': '不为空值',
    'common.equal': '等于',
    'common.not_equal': '不等于',
    'common.contain': '包含',
    'common.not_contain': '不包含',
    'common.start_with': '开头是',
    'common.end_with': '结尾是',
    'common.gt': '大于',
    'common.lt': '小于',
    'common.ge': '大于等于',
    'common.le': '小于等于',
  }
  let text = map[key] || key
  if (args) {
    Object.keys(args).forEach(k => {
      text = text.replace(`{${k}}`, args[k])
    })
  }
  return text
}
const showDel = ref(false)
const keywords = ref('')
const activeNameId = ref<string | null>(null)
const checklist = ref<string[]>([])
const filterList = ref<any[]>([])

const { item } = toRefs(props)

const filedList = inject('filedList') as Ref<any[]>

const computedWidth = computed(() => {
  const { field_id } = item.value
  return {
    width: !field_id ? '270px' : '670px',
  }
})

const operators = computed(() => {
  return allOptions.map(opt => ({
      value: opt.value,
      label: t(opt.label) !== opt.label ? t(opt.label) : opt.value // Fallback if no translation
  }))
})

const computedFiledList = computed<any[]>(() => {
  return filedList.value || []
})

const dimensions = computed(() => {
  if (!keywords.value) return computedFiledList.value
  return computedFiledList.value.filter((ele) => ele.field_name.includes(keywords.value))
})

const dimensionOptions = computed(() => {
    return dimensions.value.map(ele => ({
        label: ele.field_name,
        value: ele.id
    }))
})

onBeforeMount(() => {
  initNameEnumName()
  filterListInit()
})

const initNameEnumName = () => {
  const { name, enum_value, field_id } = item.value
  // activeNameId should be the ID
  activeNameId.value = field_id ? String(field_id) : null
  
  const arr = enum_value && enum_value.trim() ? enum_value.split(',') : []
  if (!name && field_id) {
    checklist.value = arr
  }
  if (!name && !field_id) return
  initEnumOptions()
  checklist.value = arr
}

const filterTypeChange = () => {
  item.value.term = ''
  item.value.value = null
  initEnumOptions()
}
const initEnumOptions = () => {
  console.info('initEnumOptions')
}

const selectItem = (id: any) => {
  const selected = dimensions.value.find(ele => ele.id === id)
  if (selected) {
      Object.assign(item.value, {
        field_id: selected.id,
        name: selected.field_name,
        filter_type: 'logic',
        value: '',
        term: '',
      })
      filterListInit()
      checklist.value = []
  }
}

const filterListInit = () => {
  filterList.value = [
    {
      value: 'logic',
      label: t('permission.conditional_filtering'),
    },
  ]
}

const emits = defineEmits(['update:item', 'del'])
</script>

<style lang="scss" scoped>
.white-nowrap {
  white-space: nowrap;
}
.filed {
  height: 41.4px;
  padding: 1px 3px 1px 0;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  margin-left: 20px;
  min-width: 200px;
  justify-content: left;
  position: relative;
  white-space: nowrap;

  .filed-title {
    word-wrap: break-word;
    line-height: 28px;
    color: #7e7e7e;
    font-size: 14px;
    white-space: nowrap;
    box-sizing: border-box;
    margin-right: 5px;
    display: inline-block;
    min-width: 50px;
    text-align: right;
  }

  .font16 {
    font-size: 16px;
    margin: 0 10px;
    cursor: pointer;
  }
}
</style>

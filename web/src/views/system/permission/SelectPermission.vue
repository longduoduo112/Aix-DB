<template>
  <div class="select-user_permission">
    <p class="lighter-bold">{{ t('permission.select_restricted_user') }}</p>
    <n-spin :show="loading">
      <div class="flex border" style="height: 428px; border-radius: 6px">
        <div class="p-16 border-r flex-col" style="width: 50%">
          <n-input
            v-model:value="search"
            :placeholder="t('datasource.search')"
            style="width: 364px; margin-left: 16px"
            clearable
          >
            <template #prefix>
              <n-icon>
                <Search />
              </n-icon>
            </template>
          </n-input>
          <div class="mt-8 max-height_workspace">
            <n-checkbox
              v-model:checked="checkAll"
              class="mb-8"
              style="margin-left: 16px"
              :indeterminate="isIndeterminate"
              @update:checked="handleCheckAllChange"
            >
              {{ t('datasource.select_all') }}
            </n-checkbox>
            <n-checkbox-group
              v-model:value="checkedWorkspaceIds"
              class="checkbox-group-block"
              @update:value="handleCheckedWorkspaceChange"
            >
              <div
                v-for="space in workspaceWithKeywords"
                :key="space.id"
                class="hover-bg"
              >
                <n-checkbox :value="space.id" style="width: 100%; padding: 4px 0; margin-left: 16px;">
                   <div class="flex align-center">
                      <n-icon size="20" class="mr-2">
                        <Person />
                      </n-icon>
                      <span class="ml-4 ellipsis" :title="space.userName">
                        {{ space.userName }}</span
                      >
                      <span class="account ellipsis" :title="space.mobile"
                        >({{ space.mobile || 'No Mobile' }})</span
                      >
                    </div>
                </n-checkbox>
              </div>
            </n-checkbox-group>
          </div>
        </div>
        <div class="p-16 w-full flex-col" style="width: 50%">
          <div class="flex-between mb-16" style="margin: 0 16px">
            <span class="lighter">
              {{ t('workspace.selected_2_people', { msg: checkTableList.length }) }}
            </span>

            <n-button text @click="clearWorkspaceAll">
              {{ t('workspace.clear') }}
            </n-button>
          </div>
          <div class="selected-list" style="overflow-y: auto; height: 100%;">
               <div
                v-for="ele in checkTableList"
                :key="ele.id"
                style="margin: 0 16px; position: relative"
                class="flex-between align-center hover-bg_select py-2"
              >
                <div class="flex align-center ellipsis" style="width: 100%">
                  <n-icon size="20" class="mr-2">
                    <Person />
                  </n-icon>
                  <span class="ml-4 lighter ellipsis" :title="ele.userName">{{
                    ele.userName
                  }}</span>
                  <span class="account ellipsis" :title="ele.mobile"
                    >({{ ele.mobile }})</span
                  >
                </div>
                <n-button class="close-btn" text>
                  <n-icon size="16" @click="clearWorkspace(ele)"><Close /></n-icon>
                </n-button>
              </div>
          </div>
        </div>
      </div>
    </n-spin>
  </div>
</template>

<script lang="ts" setup>
import {
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NIcon,
  NInput,
  NSpin,
} from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { queryUserList } from '@/api/user'
import Search from '~icons/material-symbols/search'
import Person from '~icons/material-symbols/person'
import Close from '~icons/material-symbols/close'

const t = (key: string, args?: any) => {
  const map: Record<string, string> = {
    'permission.select_restricted_user': '选择受限用户',
    'datasource.search': '搜索',
    'datasource.select_all': '全选',
    'workspace.selected_2_people': '已选择 {msg} 人',
    'workspace.clear': '清空',
    'permission.conditional_filtering': '条件过滤',
  }
  let text = map[key] || key
  if (args) {
    Object.keys(args).forEach(k => {
      text = text.replace(`{${k}}`, args[k])
    })
  }
  return text
}

const checkAll = ref(false)
const isIndeterminate = ref(false)
const checkedWorkspaceIds = ref<number[]>([])
const workspace = ref<any[]>([])
const search = ref('')
const loading = ref(false)
const checkTableList = ref<any[]>([])

const workspaceWithKeywords = computed(() => {
  return workspace.value.filter((ele: any) => (ele.userName as string).includes(search.value))
})

watch(search, () => {
  // Update checked status based on current view
  const currentIds = workspaceWithKeywords.value.map((ele: any) => ele.id)
  const checkedInView = checkTableList.value.filter((ele: any) => currentIds.includes(ele.id))
  
  // We don't change checkedWorkspaceIds here because it tracks ALL checked items (conceptually)
  // But Naive UI checkbox group might need only IDs present in DOM if we rendered only filtered ones?
  // Actually, keeping checkedWorkspaceIds consistent with checkTableList is better.
})

const handleCheckAllChange = (val: boolean) => {
  const currentItems = workspaceWithKeywords.value
  const currentIds = currentItems.map((ele: any) => ele.id)
  
  if (val) {
     // Add all current view items to checked
     const newItems = currentItems.filter(item => !checkTableList.value.find(c => c.id === item.id))
     checkTableList.value = [...checkTableList.value, ...newItems]
     checkedWorkspaceIds.value = checkTableList.value.map(c => c.id)
  } else {
     // Remove all current view items from checked
     checkTableList.value = checkTableList.value.filter(c => !currentIds.includes(c.id))
     checkedWorkspaceIds.value = checkTableList.value.map(c => c.id)
  }
  isIndeterminate.value = false
}

const handleCheckedWorkspaceChange = (values: (number | string)[]) => {
  // values contains IDs
  checkedWorkspaceIds.value = values as number[]
  
  // Reconstruct checkTableList based on ALL workspace data available
  // But we might only have partial data if paged? 
  // For now assume we fetch all users (page=1, size=1000)
  
  checkTableList.value = workspace.value.filter(u => checkedWorkspaceIds.value.includes(u.id))
  
  const currentIds = workspaceWithKeywords.value.map(e => e.id)
  const checkedInViewCount = values.filter(v => currentIds.includes(v as number)).length
  
  checkAll.value = checkedInViewCount === currentIds.length && currentIds.length > 0
  isIndeterminate.value = checkedInViewCount > 0 && checkedInViewCount < currentIds.length
}

const open = async (userIds: number[]) => {
  loading.value = true
  search.value = ''
  checkedWorkspaceIds.value = []
  checkAll.value = false
  checkTableList.value = []
  isIndeterminate.value = false
  
  try {
    const res = await queryUserList(1, 1000)
    const json = await res.json()
    if (json.code === 200) {
        workspace.value = json.data.records
    }
  } catch(e) {
      console.error(e)
  }

  if (userIds?.length) {
    checkedWorkspaceIds.value = userIds
    checkTableList.value = workspace.value.filter((ele: any) => userIds.includes(ele.id))
    handleCheckedWorkspaceChange(checkedWorkspaceIds.value)
  }
  loading.value = false
}

const clearWorkspace = (val: any) => {
  checkedWorkspaceIds.value = checkedWorkspaceIds.value.filter((id) => id !== val.id)
  checkTableList.value = checkTableList.value.filter((ele: any) => ele.id !== val.id)
  handleCheckedWorkspaceChange(checkedWorkspaceIds.value)
}

const clearWorkspaceAll = () => {
  checkedWorkspaceIds.value = []
  handleCheckedWorkspaceChange([])
}

defineExpose({
  open,
  checkTableList,
})
</script>

<style lang="scss" scoped>
.select-user_permission {
  .lighter-bold {
    margin-bottom: 16px;
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
  }

  .mb-8 {
    margin-bottom: 8px;
  }
  
  .mr-2 {
    margin-right: 8px;
  }

  .hover-bg {
    &:hover {
        background-color: #f5f7fa;
        border-radius: 4px;
    }
  }

  .hover-bg_select {
    &:hover {
        background-color: #f5f7fa;
        border-radius: 4px;
    }
  }

  .mt-16 {
    margin-top: 16px;
  }

  .p-16 {
    padding: 16px 0;
  }

  .lighter {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
  }

  .checkbox-group-block {
    margin: 0 16px;
  }

  .close-btn {
    cursor: pointer;
  }

  .border {
    border: 1px solid #dee0e3;
  }
  
  .border-r {
    border-right: 1px solid #dee0e3;
  }

  .w-full {
    height: 100%;
    width: 50%;
  }

  .mt-8 {
    margin-top: 8px;
  }

  .max-height_workspace {
    max-height: calc(100% - 60px); // Adjusted for header
    overflow-y: auto;
  }

  .align-center {
    align-items: center;
  }

  .flex-between {
    display: flex;
    justify-content: space-between;
  }

  .ml-4 {
    margin-left: 4px;
  }

  .flex {
    display: flex;
  }
  
  .flex-col {
      display: flex;
      flex-direction: column;
  }
  
  .ellipsis {
      white-space: nowrap; 
      overflow: hidden;
      text-overflow: ellipsis;
  }
  
  .account {
        color: #8f959e;
  }
}
</style>

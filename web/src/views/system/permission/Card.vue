<script lang="ts" setup>
import LockClosed from '~icons/material-symbols/lock'
import { NButton, NIcon } from 'naive-ui'
import Key from '~icons/material-symbols/key'
import Person from '~icons/material-symbols/person'
import Trash from '~icons/material-symbols/delete-outline'

withDefaults(
  defineProps<{
    name: string
    type: string | number
    num: string | number
    id?: string | number
  }>(),
  {
    name: '-',
    type: '-',
    id: '-',
    num: '-',
  }
)

const emits = defineEmits(['edit', 'del', 'setUser', 'setRule'])

const handleEdit = () => {
  emits('edit')
}

const handleDel = () => {
  emits('del')
}

const setUser = () => {
  emits('setUser')
}

const t = (key: string, args?: any) => {
  const map: Record<string, string> = {
    'permission.permission_rule': '权限规则',
    'permission.2': '{msg}条',
    'permission.restricted_user': '受限用户',
    'permission.238_people': '{msg}人',
    'permission.set_rule': '设置规则',
    'permission.set_user': '设置用户',
    'dashboard.delete': '删除',
  }
  let text = map[key] || key
  if (args) {
    Object.keys(args).forEach(k => {
      text = text.replace(`{${k}}`, args[k])
    })
  }
  return text
}
</script>

<template>
  <div class="card">
    <div class="name-icon">
      <n-icon class="icon-primary" size="32" color="#2080f0">
        <LockClosed />
      </n-icon>
      <span class="name ellipsis" :title="name">{{ name }}</span>
    </div>
    <div class="type-value">
      <span class="type">{{ t('permission.permission_rule') }}</span>
      <span class="value"> {{ t('permission.2', { msg: num }) }}</span>
    </div>
    <div class="type-value">
      <span class="type">{{ t('permission.restricted_user') }}</span>
      <span class="value"> {{ t('permission.238_people', { msg: type }) }}</span>
    </div>
    <div class="methods">
      <n-button size="small" secondary @click="handleEdit">
        <template #icon>
          <n-icon><Key /></n-icon>
        </template>
        {{ t('permission.set_rule') }}
      </n-button>
      <n-button size="small" secondary @click="setUser" class="ml-2">
        <template #icon>
          <n-icon><Person /></n-icon>
        </template>
        {{ t('permission.set_user') }}
      </n-button>
      <n-button size="small" secondary @click="handleDel" class="ml-2">
        <template #icon>
          <n-icon><Trash /></n-icon>
        </template>
        {{ t('dashboard.delete') }}
      </n-button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.card {
  width: 100%;
  height: 176px;
  border: 1px solid #dee0e3;
  padding: 16px;
  border-radius: 12px;
  &:hover {
    box-shadow: 0px 6px 24px 0px #1f232914;
    .methods {
      display: flex;
    }
  }

  .name-icon {
    display: flex;
    align-items: center;
    margin-bottom: 12px;

    .name {
      margin-left: 12px;
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
      max-width: 250px;
    }
  }

  .type-value {
    margin-top: 8px;
    display: flex;
    align-items: center;
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    .type {
      color: #646a73;
    }

    .value {
      margin-left: 16px;
    }
  }

  .methods {
    margin-top: 16px;
    display: none;
  }
  
  .ml-2 {
      margin-left: 8px;
  }
  
  .ellipsis {
      white-space: nowrap; 
      overflow: hidden;
      text-overflow: ellipsis;
  }
}
</style>

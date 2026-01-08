<script lang="ts" setup>
import { computed, defineAsyncComponent, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const activeTab = ref('datasource')
const isSidebarCollapsed = ref(false)

// Dynamically import components to avoid circular dependencies and keep bundle size small
const DatasourceManager = defineAsyncComponent(() => import('@/views/DatasourceManager.vue'))
const UserManager = defineAsyncComponent(() => import('@/views/UserManager.vue'))
const LLMConfig = defineAsyncComponent(() => import('@/views/LLMConfig.vue'))
const PermissionConfig = defineAsyncComponent(() => import('@/views/system/permission/PermissionList.vue'))
const TerminologyConfig = defineAsyncComponent(() => import('@/views/TerminologyConfig.vue'))
const SqlExampleLibrary = defineAsyncComponent(() => import('@/views/SqlExampleLibrary.vue'))

const menuItems = [
  { key: 'datasource', label: '库表配置', icon: 'i-material-symbols:database-outline' },
  { key: 'llm', label: '模型配置', icon: 'i-material-symbols:settings-outline' },
  { key: 'user', label: '用户管理', icon: 'i-material-symbols:person-outline' },
  { key: 'permission', label: '权限配置', icon: 'i-material-symbols:lock-outline' },
  { key: 'terminology', label: '术语配置', icon: 'i-material-symbols:book-outline' },
  { key: 'sql', label: 'SQL示例', icon: 'i-material-symbols:code' },
]

const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// 返回对话页面
const handleBack = () => {
  router.push({ name: 'ChatIndex' })
}
</script>

<template>
  <div class="system-settings-page-container">
    <!-- Left Sidebar -->
    <div
      class="page-sidebar"
      :class="{ collapsed: isSidebarCollapsed }"
    >
      <div class="sidebar-header">
        <div
          v-show="!isSidebarCollapsed"
          class="title"
        >
          系统设置
        </div>
        <div
          class="collapse-btn"
          @click="toggleSidebar"
        >
          <div
            class="i-hugeicons:menu-01 text-20 transition-transform duration-300"
            :class="{ 'rotate-180': isSidebarCollapsed }"
          ></div>
        </div>
      </div>
      <div class="sidebar-menu">
        <div
          v-for="item in menuItems"
          :key="item.key"
          class="menu-item"
          :class="{ active: activeTab === item.key, collapsed: isSidebarCollapsed }"
          :title="isSidebarCollapsed ? item.label : ''"
          @click="activeTab = item.key"
        >
          <div class="icon-wrapper">
            <div :class="[item.icon, 'text-20']"></div>
          </div>
          <span
            v-show="!isSidebarCollapsed"
            class="label"
          >{{ item.label }}</span>
        </div>
      </div>

      <div class="sidebar-footer">
        <div
          class="menu-item"
          :class="{ collapsed: isSidebarCollapsed }"
          :title="isSidebarCollapsed ? '返回' : ''"
          @click="handleBack"
        >
          <div class="icon-wrapper">
            <div class="i-hugeicons:arrow-left-01 text-20"></div>
          </div>
          <span
            v-show="!isSidebarCollapsed"
            class="label"
          >返回</span>
        </div>
      </div>
    </div>

    <!-- Right Content -->
    <div class="page-content">
      <div
        v-if="activeTab === 'datasource'"
        class="h-full relative"
      >
        <!-- Masking the header of DatasourceManager via CSS is hacky, but since we are reusing the component -->
        <!-- Ideally DatasourceManager should accept a prop to hide header/back button, but for now we wrap it -->
        <DatasourceManager />
      </div>

      <div
        v-else-if="activeTab === 'llm'"
        class="h-full"
      >
        <LLMConfig />
      </div>

      <div
        v-else-if="activeTab === 'user'"
        class="h-full"
      >
        <UserManager />
      </div>

      <div
        v-else-if="activeTab === 'permission'"
        class="h-full"
      >
        <PermissionConfig />
      </div>

      <div
        v-else-if="activeTab === 'terminology'"
        class="h-full"
      >
        <TerminologyConfig />
      </div>

      <div
        v-else-if="activeTab === 'sql'"
        class="h-full"
      >
        <SqlExampleLibrary />
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.system-settings-page-container {
  display: flex;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background-color: #f9fafb;
}

.page-sidebar {
  width: 240px;
  background-color: #fff;
  border-right: 1px solid #f3f4f6;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  flex-shrink: 0;

  &.collapsed {
    width: 64px;

    .sidebar-header {
      padding: 20px 0;
      justify-content: center;
    }

    .sidebar-menu {
      padding: 12px 8px;
    }

    .menu-item {
      padding: 12px 0;
      justify-content: center;

      .icon-wrapper {
        margin-right: 0;
      }
    }
  }

  .sidebar-header {
    padding: 20px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #f3f4f6;
    color: #1f2937;
    white-space: nowrap;

    .title {
      font-size: 18px;
      font-weight: 600;
    }

    .collapse-btn {
      cursor: pointer;
      color: #6b7280;
      padding: 4px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;

      &:hover {
        background-color: #f3f4f6;
        color: #111827;
      }
    }
  }

  .sidebar-menu {
    padding: 12px;
    flex: 1;
    overflow: hidden auto;

    .menu-item {
      padding: 12px 16px;
      margin-bottom: 4px;
      border-radius: 8px;
      cursor: pointer;
      color: #4b5563;
      transition: all 0.2s;
      font-size: 14px;
      display: flex;
      align-items: center;
      white-space: nowrap;

      .icon-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 12px;
        transition: margin 0.3s;
      }

      &:hover {
        background-color: #f9fafb;
        color: #111827;
      }

      &.active {
        background-color: #eff6ff;
        color: #3b82f6;
        font-weight: 500;
      }
    }
  }

  .sidebar-footer {
    padding: 12px;
    border-top: 1px solid #f3f4f6;

    .menu-item {
      padding: 12px 16px;
      border-radius: 8px;
      cursor: pointer;
      color: #4b5563;
      transition: all 0.2s;
      font-size: 14px;
      display: flex;
      align-items: center;
      white-space: nowrap;

      &.collapsed {
        padding: 12px 0;
        justify-content: center;
        .icon-wrapper { margin-right: 0; }
      }

      .icon-wrapper {
        margin-right: 12px;
      }

      &:hover {
        background-color: #f9fafb;
        color: #111827;
      }
    }
  }
}

.page-content {
  flex: 1;
  height: 100%;
  overflow-y: auto;
  min-width: 0; // Prevent flex item from overflowing

  /* Hide the header and back button inside DatasourceManager and UserManager when displayed here */

  :deep(.datasource-manager .header .title-section .back-btn),
  :deep(.user-manager .header .title-section .back-btn),
  :deep(.llm-config .header .title-section .back-btn) {
    display: none !important;
  }

  /* Adjust padding if needed */

  :deep(.datasource-manager),
  :deep(.user-manager),
  :deep(.llm-config) {
    height: 100%;
    padding: 24px 32px;
  }
}
</style>

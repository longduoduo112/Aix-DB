<script lang="tsx" setup>
const props = withDefaults(defineProps<{
  mode?: string
  theme?: string
}>(), {
  mode: 'sidebar',
  theme: 'dark',
})
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 侧边栏图标组件
const SideBarItem = defineComponent({
  props: {
    label: {
      type: String,
      default: '',
    },
    fill: {
      type: Boolean,
      default: false,
    },
    active: {
      type: Boolean,
      default: false,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    theme: {
      type: String,
      default: 'dark',
    },
  },
  emits: ['click'],
  setup(props, { emit }) {
    const computedWrapperClassName = computed(() => {
      const isLight = props.theme === 'light'

      if (props.fill) {
        return isLight ? 'c-[#7E6BF2]' : 'c-white'
      }

      if (props.disabled) {
        return [
          'opacity-50',
        ]
      }

      return [
        isLight ? 'c-[#666] hover:c-[#333]' : 'c-#c6c4ff hover:c-white',
        props.active && (isLight ? 'c-[#7E6BF2]' : 'c-white'),
      ]
    })

    const computedInnerClassName = computed(() => {
      if (props.fill) {
        return
      }

      const isLight = props.theme === 'light'
      return [
        'p-10 rouned-50%',
        props.active && (isLight ? 'bg-[#F2F0FF]' : 'bg-#a6a2f3'),
      ]
    })

    const handleClick = () => {
      if (props.disabled) {
        return
      }
      emit('click')
    }

    return {
      computedWrapperClassName,
      computedInnerClassName,
      handleClick,
    }
  },
  render() {
    return (
      <div
        flex="~ col gap-10 items-center"
        class={[
          'select-none transition-all-260',
          this.disabled
            ? 'cursor-not-allowed'
            : 'cursor-pointer',
          this.computedWrapperClassName,
        ]}
        onClick={this.handleClick}
      >
        <div
          flex="~ justify-center items-center"
          class={[
            'transition-all-260',
            'size-40 rounded-50%',
            '[&>*]:size-full [&>*]:bg-no-repeat [&>*]:bg-center [&>*]:bg-cover',
            this.computedInnerClassName,
          ]}
        >
          {this.$slots.default?.()}
        </div>
        <div class="font-bold">{this.label}</div>
      </div>
    )
  },
})

const handleSidebarMenuSelect = (key: string) => {
  router.push({ name: key })
}

interface SidebarItemType {
  label: string
  key: string
  renderIcon: () => any
  onClick?: () => void
  children?: { label: string, key: string }[]
  props: Record<string, any>
}

const sidebarItems = ref<SidebarItemType[]>([
  {
    label: '数据源',
    key: 'DatasourceManager',
    renderIcon() {
      return (
        <div class="i-material-symbols:database-outline text-24"></div>
      )
    },
    onClick() {
      router.push({ name: 'DatasourceManager' })
    },
    props: {},
  },
  {
    label: '用户管理',
    key: 'UserManager',
    renderIcon() {
      return (
        <div class="i-material-symbols:person-outline text-24"></div>
      )
    },
    onClick() {
      router.push({ name: 'UserManager' })
    },
    props: {},
  },
  {
    label: '权限配置',
    key: 'PermissionConfig',
    renderIcon() {
      return (
        <div class="i-material-symbols:lock-outline text-24"></div>
      )
    },
    onClick() {
      router.push({ name: 'PermissionConfig' })
    },
    props: {},
  },
  {
    label: '术语配置',
    key: 'TerminologyConfig',
    renderIcon() {
      return (
        <div class="i-material-symbols:book-outline text-24"></div>
      )
    },
    onClick() {
      router.push({ name: 'TerminologyConfig' })
    },
    props: {},
  },
  {
    label: 'SQL 示例库',
    key: 'SqlExampleLibrary',
    renderIcon() {
      return (
        <div class="i-material-symbols:code text-24"></div>
      )
    },
    onClick() {
      router.push({ name: 'SqlExampleLibrary' })
    },
    props: {},
  },
])


const handleLogout = () => {
  userStore.logout()
  setTimeout(() => {
    router.replace('/login')
  }, 100)
}

// 头像菜单选项
const avatarMenuOptions = computed(() => {
  // Ensure dependency on userStore.role is tracked
  const role = userStore.role

  const options = [
    {
      label: '系统设置',
      key: 'systemSettings',
      icon: () => <div class="i-material-symbols:settings-outline text-16"></div>,
    },
    {
      label: '知识库管理',
      key: 'knowledgeManager',
      icon: () => <div class="i-material-symbols:library-books-outline text-16"></div>,
    },
    {
      label: '退出登录',
      key: 'logout',
      icon: () => <div class="i-material-symbols:logout text-16"></div>,
    },
  ]

  if (role !== 'admin') {
    return options.filter((opt) => opt.key === 'logout')
  }
  return options
})

// 处理菜单项选择
const handleMenuSelect = (key: string) => {
  console.log('Dropdown clicked, role:', userStore.role)
  switch (key) {
    case 'systemSettings':
      router.push({
        name: 'SystemSettings',
      })
      break
    case 'knowledgeManager':
      router.push({
        name: 'KnowledgeManager',
      })
      break
    case 'llmConfig':
      router.push({
        name: 'LLMConfig',
      })
      break
    case 'logout':
      handleLogout()
      break
    default:
      break
  }
}
</script>

<template>
  <template v-if="$props.mode === 'sidebar'">
    <section
      flex="~ col justify-between"
      w-70
      h-full
      overflow-hidden
      relative
      :style="{
        background: `linear-gradient(
          to bottom,
          #6754ff,
          #8478ff
        )`,
      }"
    >
      <!-- 最侧边图标设置 -->
      <div
        flex="1 ~ col gap-28"
        pt-24
      >
        <template
          v-for="(sidebarItem) in sidebarItems"
          :key="sidebarItem.key"
        >
          <n-dropdown
            v-if="sidebarItem.children"
            trigger="hover"
            placement="right-start"
            :options="sidebarItem.children"
            @select="handleSidebarMenuSelect"
          >
            <SideBarItem
              :label="sidebarItem.label"
              :active="(sidebarItem.children && sidebarItem.children.some(c => c.key === route.name)) || sidebarItem.key === route.name"
              v-bind="sidebarItem.props"
              :theme="$props.theme"
            >
              <component :is="sidebarItem.renderIcon" />
            </SideBarItem>
          </n-dropdown>
          <SideBarItem
            v-else
            :label="sidebarItem.label"
            :active="sidebarItem.key === route.name"
            v-bind="sidebarItem.props"
            :theme="$props.theme"
            @click="sidebarItem.onClick && sidebarItem.onClick.call(sidebarItem)"
          >
            <component :is="sidebarItem.renderIcon" />
          </SideBarItem>
        </template>
      </div>

      <n-dropdown
        trigger="hover"
        placement="right-start"
        :options="avatarMenuOptions"
        @select="handleMenuSelect"
        @click="() => console.log('Dropdown clicked, role:', userStore.role)"
      >
        <SideBarItem
          fill
          :theme="$props.theme"
        >
          <div class="size-35 i-my-svg:avatar"></div>
        </SideBarItem>
      </n-dropdown>
    </section>
  </template>
  <template v-else-if="$props.mode === 'avatar'">
    <n-popover
      trigger="hover"
      placement="right-end"
      :show-arrow="false"
      raw
      :style="{ padding: 0 }"
    >
      <template #trigger>
        <div class="user-info flex items-center gap-2 cursor-pointer transition-opacity hover:opacity-80">
          <!-- Avatar Icon -->
          <div class="i-hugeicons:user-circle text-28 text-[#7E6BF2]"></div>
        </div>
      </template>
      <div class="w-[300px] bg-white rounded-xl shadow-lg border border-gray-100 p-4">
        <!-- User Header -->
        <div class="flex items-center gap-3 mb-6 bg-gray-50/50 p-2 rounded-lg">
          <div class="i-hugeicons:user-circle text-40 text-[#7E6BF2]"></div>
          <div class="flex flex-col">
            <span class="text-[#333] font-bold text-16">{{ userStore.role === 'admin' ? '管理员' : '普通用户' }}</span>
            <span class="text-[#999] text-12">UID: y9no5hmtvo</span>
          </div>
        </div>

        <!-- Action Grid -->
        <div
          v-if="userStore.role === 'admin'"
          class="grid grid-cols-3 gap-y-6 gap-x-2 mb-6"
        >
          <div
            class="flex flex-col items-center gap-2 cursor-pointer group"
            @click="handleMenuSelect('systemSettings')"
          >
            <div class="relative">
              <div class="i-material-symbols:settings-outline text-20 text-[#666] group-hover:text-[#333] transition-colors"></div>
            </div>
            <span class="text-12 text-[#666] group-hover:text-[#333]">系统设置</span>
          </div>

          <div
            class="flex flex-col items-center gap-2 cursor-pointer group"
            @click="handleMenuSelect('knowledgeManager')"
          >
            <div class="relative">
              <div class="i-hugeicons:book-open-01 text-20 text-[#666] group-hover:text-[#333] transition-colors"></div>
            </div>
            <span class="text-12 text-[#666] group-hover:text-[#333]">知识库管理</span>
          </div>
        </div>

        <!-- Logout -->
        <div
          class="flex flex-col items-start gap-2 cursor-pointer group mt-4 pt-4 border-t border-gray-100 pl-4"
          @click="handleMenuSelect('logout')"
        >
          <div class="i-hugeicons:logout-01 text-20 text-red-500 group-hover:text-red-600 transition-colors"></div>
          <span class="text-12 text-red-500 group-hover:text-red-600">退出登录</span>
        </div>
      </div>
    </n-popover>
  </template>
</template>

<style lang="scss" scoped>

</style>

const LayoutDefault = () => import('@/components/Layout/default.vue')

const childrenRoutes: Array<RouteRecordRaw> = [
  {
    path: 'chat',
    meta: { requiresAuth: true },
    name: 'ChatRoot',
    redirect: {
      name: 'ChatIndex',
    },
    children: [
      {
        path: '',
        name: 'ChatIndex',
        component: () => import('@/views/chat.vue'),
      },
    ],
  },
  {
    path: 'datasource',
    name: 'DatasourceManager',
    component: () => import('@/views/DatasourceManager.vue'),
    meta: { requiresAuth: true }, // 标记需要认证
  },
  {
    path: 'datasource/table/:dsId/:dsName',
    name: 'DatasourceTableList',
    component: () => import('@/views/DatasourceTableList.vue'),
    meta: { requiresAuth: true }, // 标记需要认证
  },
  {
    path: 'user-manager',
    name: 'UserManager',
    component: () => import('@/views/UserManager.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'knowledge-manager',
    name: 'KnowledgeManager',
    component: () => import('@/views/KnowledgeManager.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'llm-config',
    name: 'LLMConfig',
    component: () => import('@/views/LLMConfig.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'permission-config',
    name: 'PermissionConfig',
    component: () => import('@/views/system/permission/PermissionList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'terminology-config',
    name: 'TerminologyConfig',
    component: () => import('@/views/TerminologyConfig.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'set/training',
    name: 'SqlExampleLibrary',
    component: () => import('@/views/SqlExampleLibrary.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: 'system-settings',
    name: 'SystemSettings',
    component: () => import('@/views/SystemSettings.vue'),
    meta: { requiresAuth: true },
  },
]

export default childrenRoutes

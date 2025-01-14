import childRoutes from '@/router/child-routes'

const routes: Array<RouteRecordRaw> = [
  ***REMOVED***
        path: '/',
        name: 'Root',
        redirect: {
            name: 'ChatRoot'
        ***REMOVED***,
        meta: { requiresAuth: true ***REMOVED*** // 标记需要认证
    ***REMOVED***,
    ...childRoutes,
  ***REMOVED***
        path: '/:pathMatch(.****REMOVED***',
        name: '404',
        component: (***REMOVED*** => import('@/components/404.vue'***REMOVED***
    ***REMOVED***,
  ***REMOVED***
        path: '/login',
        name: 'Login',
        component: (***REMOVED*** => import('@/views/Login.vue'***REMOVED***
    ***REMOVED***,
  ***REMOVED***
        path: '/testAssitant',
        name: 'TestAssitant',
        component: (***REMOVED*** => import('@/views/TestAssistant.vue'***REMOVED***,
        meta: { requiresAuth: true ***REMOVED*** // 标记需要认证
    ***REMOVED***
]

export default routes

const LayoutDefault = (***REMOVED*** => import('@/components/Layout/default.vue'***REMOVED***

const childrenRoutes: Array<RouteRecordRaw> = [
***REMOVED***
    path: '/chat',
    component: LayoutDefault,
    meta: { requiresAuth: true ***REMOVED***,
    name: 'ChatRoot',
    redirect: {
      name: 'ChatIndex',
    ***REMOVED***,
    children: [
    ***REMOVED***
        path: '',
        name: 'ChatIndex',
        component: (***REMOVED*** => import('@/views/chat.vue'***REMOVED***,
      ***REMOVED***,
***REMOVED***,
  ***REMOVED***,
]

export default childrenRoutes

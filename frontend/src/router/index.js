import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/employee/Dashboard.vue'),
        meta: { title: '个人看板', role: 'employee' }
      },
      {
        path: 'punches',
        name: 'Punches',
        component: () => import('@/views/employee/Punches.vue'),
        meta: { title: '打卡记录', role: 'employee' }
      },
      {
        path: 'anomalies',
        name: 'Anomalies',
        component: () => import('@/views/employee/Anomalies.vue'),
        meta: { title: '异常记录', role: 'employee' }
      },
      {
        path: 'approvals',
        name: 'Approvals',
        component: () => import('@/views/employee/Approvals.vue'),
        meta: { title: '审批申请', role: 'employee' }
      },
      {
        path: 'admin/dashboard',
        name: 'AdminDashboard',
        component: () => import('@/views/admin/Dashboard.vue'),
        meta: { title: '管理看板', role: 'admin' }
      },
      {
        path: 'admin/departments',
        name: 'AdminDepartments',
        component: () => import('@/views/admin/Departments.vue'),
        meta: { title: '部门考勤', role: 'admin' }
      },
      {
        path: 'admin/reports',
        name: 'AdminReports',
        component: () => import('@/views/admin/Reports.vue'),
        meta: { title: '月度报告', role: 'admin' }
      },
      {
        path: 'admin/scheduling',
        name: 'AdminScheduling',
        component: () => import('@/views/admin/Scheduling.vue'),
        meta: { title: '排班优化', role: 'admin' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - 考勤管理系统` : '考勤管理系统'
  
  const userStore = useUserStore()
  const token = localStorage.getItem('token')

  if (to.path === '/login') {
    if (token) {
      const user = userStore.user || JSON.parse(localStorage.getItem('user'))
      next(user?.role === 'admin' ? '/admin/dashboard' : '/dashboard')
    } else {
      next()
    }
    return
  }

  if (!token) {
    next('/login')
    return
  }

  if (!userStore.user) {
    try {
      await userStore.fetchUserInfo()
    } catch (e) {
      userStore.logout()
      next('/login')
      return
    }
  }

  if (to.meta.role && to.meta.role !== userStore.user?.role) {
    next(userStore.user?.role === 'admin' ? '/admin/dashboard' : '/dashboard')
    return
  }

  next()
})

export default router

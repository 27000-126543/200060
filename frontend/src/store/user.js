import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login, getCurrentUser } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const setToken = (t) => {
    token.value = t
    localStorage.setItem('token', t)
  }

  const setUser = (u) => {
    user.value = u
    localStorage.setItem('user', JSON.stringify(u))
  }

  const logout = () => {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  const handleLogin = async (data) => {
    const res = await login(data)
    setToken(res.access_token)
    const userInfo = {
      id: res.employee_id,
      name: res.name,
      role: res.role,
      department_id: res.department_id
    }
    setUser(userInfo)
    return userInfo
  }

  const fetchUserInfo = async () => {
    const res = await getCurrentUser()
    setUser(res)
    return res
  }

  return {
    token,
    user,
    setToken,
    setUser,
    logout,
    handleLogin,
    fetchUserInfo
  }
})

<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
      <div class="logo">
        <el-icon :size="48" color="#409EFF">
          <Clock />
        </el-icon>
        <h1>企业考勤智能管理系统</h1>
        <p>Enterprise Attendance Management System</p>
      </div>
    </div>
    <el-form
      ref="loginFormRef"
      :model="loginForm"
      class="login-form"
      label-width="0"
    >
      <el-form-item
        prop="username"
        :rules="[
          { required: true, message: '请输入工号', trigger: 'blur' }
        ]"
      >
        <el-input
          v-model="loginForm.username"
          placeholder="请输入工号"
          :prefix-icon="User"
          size="large"
          @keyup.enter="handleLogin"
        />
      </el-form-item>
      <el-form-item
        prop="password"
        :rules="[
          { required: true, message: '请输入密码', trigger: 'blur' }
        ]"
      >
        <el-input
          v-model="loginForm.password"
          type="password"
          placeholder="请输入密码"
          :prefix-icon="Lock"
          size="large"
          show-password
          @keyup.enter="handleLogin"
        />
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :loading="loading"
          @click="handleLogin"
        >
          登 录
        </el-button>
      </el-form-item>
    </el-form>
    <div class="login-tips">
      <p>默认工号: EMP0001 ~ EMP0048</p>
      <p>默认密码: 123456</p>
      <p>管理员: ADMIN001 / EMP0001</p>
    </div>
  </div>
</div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock, User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const loginFormRef = ref()
const loading = ref(false)

const loginForm = reactive({
  username: 'EMP0001',
  password: '123456'
})

const handleLogin = async () => {
  console.log('登录表单:', loginForm)
  loading.value = true
  try {
    const user = await userStore.handleLogin(loginForm)
    ElMessage.success('登录成功')
    router.push(user.role === 'admin' ? '/admin/dashboard' : '/dashboard')
  } catch (e) {
    console.error('登录失败:', e)
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  justify-content: center;
  align-items: center;
}

.login-box {
  width: 400px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  padding: 40px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo h1 {
  font-size: 24px;
  color: #303133;
  margin: 15px 0 8px;
}

.logo p {
  color: #909399;
  font-size: 12px;
}

.login-form {
  margin-bottom: 20px;
}

.login-btn {
  width: 100%;
}

.login-tips {
  text-align: center;
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}

.login-tips p {
  margin: 0;
}
</style>

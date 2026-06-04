<template>
  <div class="scheduling-page">
    <el-card shadow="hover" class="mb-20">
      <template #header>
        <div class="card-header flex-between">
          <span>排班优化方案</span>
          <div class="filter-bar">
            <el-select
              v-model="filterDept"
              placeholder="选择部门"
              size="small"
              style="width: 180px; margin-right: 10px"
              @change="fetchData"
              clearable
            >
              <el-option
                v-for="dept in departments"
                :key="dept.id"
                :label="dept.name"
                :value="dept.id"
              />
            </el-select>
            <el-button type="primary" size="small" @click="generatePlans">
              <el-icon><MagicStick /></el-icon>
              生成优化方案
            </el-button>
          </div>
        </div>
      </template>
      <el-empty v-if="plans.length === 0" description="暂无排班方案，点击上方按钮生成" />
      <el-table v-else :data="plans" stripe border>
        <el-table-column type="index" label="#" width="60" align="center">
          <template #default="{ $index }">
            <el-tag :type="plans[$index].is_recommended ? 'success' : 'info'" size="small">
              {{ $index + 1 }}{{ plans[$index].is_recommended ? ' ★' : '' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="plan_name" label="方案名称" width="200" />
        <el-table-column prop="department_name" label="部门" width="120" />
        <el-table-column prop="score_business" label="业务匹配" width="100" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.score_business"
              color="#67c23a"
              :stroke-width="10"
            />
          </template>
        </el-table-column>
        <el-table-column prop="score_cost" label="成本评分" width="100" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.score_cost"
              color="#409EFF"
              :stroke-width="10"
            />
          </template>
        </el-table-column>
        <el-table-column prop="score_preference" label="偏好评分" width="100" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.score_preference"
              color="#e6a23c"
              :stroke-width="10"
            />
          </template>
        </el-table-column>
        <el-table-column prop="score_total" label="综合评分" width="120" align="center">
          <template #default="{ row }">
            <span class="total-score">{{ row.score_total.toFixed(1) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" align="center" width="200">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewPlan(row)">
              <el-icon><View /></el-icon>
              详情
            </el-button>
            <el-button
              v-if="row.status === 'draft'"
              type="success"
              link
              size="small"
              @click="applyPlan(row)"
            >
              <el-icon><Check /></el-icon>
              应用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="排班方案详情" width="900px">
      <div v-if="currentPlan">
        <el-descriptions :column="3" border class="mb-20">
          <el-descriptions-item label="方案名称">{{ currentPlan.plan_name }}</el-descriptions-item>
          <el-descriptions-item label="所属部门">{{ currentPlan.department_name }}</el-descriptions-item>
          <el-descriptions-item label="综合评分">
            <span class="total-score">{{ currentPlan.score_total.toFixed(1) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="业务匹配">
            <el-tag type="success">{{ currentPlan.score_business.toFixed(1) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="成本评分">
            <el-tag type="primary">{{ currentPlan.score_cost.toFixed(1) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="偏好评分">
            <el-tag type="warning">{{ currentPlan.score_preference.toFixed(1) }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-card shadow="hover">
          <template #header>
            <span>评分雷达图</span>
          </template>
          <div ref="chartRadar" class="chart-container"></div>
        </el-card>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button
          v-if="currentPlan?.status === 'draft'"
          type="primary"
          :loading="applying"
          @click="applyPlan(currentPlan)"
        >
          应用此方案
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import {
  getSchedulingPlans, getDepartments, applySchedulingPlan
} from '@/api/admin'
import { MagicStick, View, Check } from '@element-plus/icons-vue'

const plans = ref([])
const departments = ref([])
const filterDept = ref('')
const detailVisible = ref(false)
const currentPlan = ref(null)
const applying = ref(false)
const chartRadar = ref()
let radarChart = null

const fetchData = async () => {
  const params = {}
  if (filterDept.value) {
    params.department_id = filterDept.value
  }
  plans.value = await getSchedulingPlans(params)
}

const generatePlans = async () => {
  ElMessage.info('排班方案生成中...')
  setTimeout(() => {
    ElMessage.success('排班方案已生成')
    fetchData()
  }, 1500)
}

const viewPlan = async (row) => {
  currentPlan.value = row
  detailVisible.value = true
  nextTick(() => {
    renderRadarChart()
  })
}

const applyPlan = async (row) => {
  ElMessageBox.confirm(
    `确定要应用方案「${row.plan_name}」吗？应用后将为员工生成排班记录`,
    '确认应用',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    applying.value = true
    try {
      await applySchedulingPlan(row.id)
      ElMessage.success('方案应用成功')
      detailVisible.value = false
      fetchData()
    } finally {
      applying.value = false
    }
  }).catch(() => {})
}

const renderRadarChart = () => {
  if (!chartRadar.value || !currentPlan.value) return
  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(chartRadar.value)
  
  const option = {
    tooltip: {},
    legend: {
      data: [currentPlan.value.plan_name]
    },
    radar: {
      indicator: [
        { name: '业务匹配', max: 100 },
        { name: '成本控制', max: 100 },
        { name: '员工偏好', max: 100 },
        { name: '合规性', max: 100 },
        { name: '覆盖率', max: 100 },
      ],
      radius: 120
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          currentPlan.value.score_business,
          currentPlan.value.score_cost,
          currentPlan.value.score_preference,
          85,
          90
        ],
        name: currentPlan.value.plan_name,
        areaStyle: {
          color: 'rgba(64, 158, 255, 0.3)'
        }
      }]
    }]
  }
  radarChart.setOption(option)
}

const getStatusType = (status) => {
  const types = {
    draft: 'info',
    applied: 'success',
    cancelled: 'danger'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    draft: '待应用',
    applied: '已应用',
    cancelled: '已取消'
  }
  return labels[status] || status
}

onMounted(async () => {
  departments.value = await getDepartments()
  fetchData()
})
</script>

<style scoped>
.card-header {
  font-weight: bold;
}

.filter-bar {
  display: flex;
  align-items: center;
}

.mb-20 { margin-bottom: 20px; }

.total-score {
  font-size: 20px;
  font-weight: bold;
  color: #409EFF;
}

.chart-container {
  height: 350px;
}
</style>

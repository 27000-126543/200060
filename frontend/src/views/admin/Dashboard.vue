<template>
  <div class="admin-dashboard">
    <el-row :gutter="20" class="mb-20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-blue">
            <el-icon :size="32"><User /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">员工总数</p>
            <p class="value">{{ overview.total_employees || 0 }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-green">
            <el-icon :size="32"><CircleCheck /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">已到岗</p>
            <p class="value">{{ overview.present_employees || 0 }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-purple">
            <el-icon :size="32"><Odometer /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">出勤率</p>
            <p class="value">{{ overview.overall_attendance_rate || '0%' }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-orange">
            <el-icon :size="32"><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">异常总数</p>
            <p class="value">{{ overview.anomaly_count || 0 }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header flex-between">
              <span>出勤率趋势</span>
              <el-button type="primary" link size="small" @click="refreshData">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <div ref="chartTrend" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>异常类型统计</span>
          </template>
          <div ref="chartAnomaly" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt-20">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>迟到/早退趋势</span>
          </template>
          <div ref="chartLateEarly" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header flex-between">
              <span>各部门出勤率排名</span>
              <el-button type="primary" link size="small" @click="$router.push('/admin/departments')">
                查看详情
              </el-button>
            </div>
          </template>
          <el-table :data="departmentRanking" stripe style="width: 100%">
            <el-table-column prop="rank" label="排名" width="60" align="center">
              <template #default="{ $index }">
                <el-tag :type="$index < 3 ? 'warning' : 'info'" size="small">
                  {{ $index + 1 }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="department_name" label="部门" />
            <el-table-column prop="attendance_rate" label="出勤率" width="100" align="center">
              <template #default="{ row }">
                <span :class="getRateClass(row.attendance_rate_value)">
                  {{ row.attendance_rate }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="anomaly_count" label="异常" width="60" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.anomaly_count > 0" type="danger" size="small">
                  {{ row.anomaly_count }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  getDashboardOverview, getAttendanceTrend, getDepartmentsDashboard
} from '@/api/admin'
import { User, CircleCheck, Odometer, Warning, Refresh } from '@element-plus/icons-vue'

const overview = reactive({})
const departmentRanking = ref([])
const attendanceTrend = ref([])

const chartTrend = ref()
const chartAnomaly = ref()
const chartLateEarly = ref()
let trendChart = null
let anomalyChart = null
let lateEarlyChart = null
let refreshTimer = null

const fetchData = async () => {
  const [ov, trend, depts] = await Promise.all([
    getDashboardOverview(),
    getAttendanceTrend({ days: 7 }),
    getDepartmentsDashboard()
  ])
  Object.assign(overview, ov)
  attendanceTrend.value = trend
  departmentRanking.value = depts.sort((a, b) => b.attendance_rate_value - a.attendance_rate_value)
  await nextTick()
  renderTrendChart()
  renderAnomalyChart()
  renderLateEarlyChart()
}

const renderTrendChart = () => {
  if (!chartTrend.value) return
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  trendChart = echarts.init(chartTrend.value, null, { renderer: 'canvas' })
  
  const trendData = attendanceTrend.value || []
  const xData = trendData.map(item => item.date ? item.date.slice(5) : '')
  const rateData = trendData.map(item => (item.attendance_rate !== undefined ? item.attendance_rate * 100 : 0))
  
  const option = {
    tooltip: {
      trigger: 'axis'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xData
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' }
    },
    series: [{
      type: 'line',
      smooth: true,
      data: rateData,
      lineStyle: { width: 3, color: '#409EFF' },
      itemStyle: { color: '#409EFF' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
          { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
        ])
      }
    }]
  }
  trendChart.setOption(option, true)
  trendChart.resize()
}

const renderAnomalyChart = () => {
  if (!chartAnomaly.value) return
  if (anomalyChart) {
    anomalyChart.dispose()
    anomalyChart = null
  }
  anomalyChart = echarts.init(chartAnomaly.value, null, { renderer: 'canvas' })
  
  const data = [
    { value: overview.late_count || 0, name: '迟到', itemStyle: { color: '#E6A23C' } },
    { value: overview.early_leave_count || 0, name: '早退', itemStyle: { color: '#F56C6C' } },
    { value: overview.no_punch_count || 0, name: '未打卡', itemStyle: { color: '#909399' } },
  ]
  
  const option = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 10 },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['50%', '40%'],
      data,
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      label: {
        formatter: '{b}: {c} ({d}%)'
      }
    }]
  }
  anomalyChart.setOption(option, true)
  anomalyChart.resize()
}

const renderLateEarlyChart = () => {
  if (!chartLateEarly.value) return
  if (lateEarlyChart) {
    lateEarlyChart.dispose()
    lateEarlyChart = null
  }
  lateEarlyChart = echarts.init(chartLateEarly.value, null, { renderer: 'canvas' })
  
  const trendData = attendanceTrend.value || []
  const xData = trendData.map(item => item.date ? item.date.slice(5) : '')
  const lateData = trendData.map(item => item.late_count || 0)
  const earlyData = trendData.map(item => item.early_leave_count || 0)
  
  const option = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['迟到', '早退'] },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: xData
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '迟到',
        type: 'bar',
        data: lateData,
        itemStyle: { color: '#E6A23C' },
        barMaxWidth: 30
      },
      {
        name: '早退',
        type: 'bar',
        data: earlyData,
        itemStyle: { color: '#F56C6C' },
        barMaxWidth: 30
      }
    ]
  }
  lateEarlyChart.setOption(option, true)
  lateEarlyChart.resize()
}

const getRateClass = (value) => {
  if (value >= 0.95) return 'text-green'
  if (value >= 0.9) return ''
  return 'text-red'
}

const refreshData = () => {
  fetchData()
}

const handleResize = () => {
  trendChart?.resize()
  anomalyChart?.resize()
  lateEarlyChart?.resize()
}

onMounted(() => {
  fetchData()
  refreshTimer = setInterval(fetchData, 60000)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  anomalyChart?.dispose()
  lateEarlyChart?.dispose()
})
</script>

<style scoped>
.stat-card {
  .el-card__body {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 20px;
  }
}

.stat-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.bg-blue { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.bg-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.bg-purple { background: linear-gradient(135deg, #8E2DE2 0%, #4A00E0 100%); }
.bg-orange { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }

.stat-content {
  flex: 1;
}

.stat-content .label {
  color: #909399;
  font-size: 13px;
  margin: 0 0 8px;
}

.stat-content .value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin: 0;
}

.card-header {
  font-weight: bold;
}

.chart-container {
  height: 320px;
  min-height: 320px;
}

.text-red { color: #f56c6c; font-weight: bold; }
.text-green { color: #67c23a; font-weight: bold; }

.mb-20 { margin-bottom: 20px; }
.mt-20 { margin-top: 20px; }
</style>

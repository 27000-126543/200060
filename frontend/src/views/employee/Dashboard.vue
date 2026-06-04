<template>
  <div class="employee-dashboard">
    <el-row :gutter="20" class="mb-20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-blue">
            <el-icon :size="32"><Timer /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">本月打卡次数</p>
            <p class="value">{{ dashboard.punch_count || 0 }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-orange">
            <el-icon :size="32"><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">本月异常次数</p>
            <p class="value">{{ dashboard.anomaly_count || 0 }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-red">
            <el-icon :size="32"><Bell /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">待处理异常</p>
            <p class="value">{{ dashboard.pending_anomalies || 0 }}</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon bg-green">
            <el-icon :size="32"><Document /></el-icon>
          </div>
          <div class="stat-content">
            <p class="label">审批中</p>
            <p class="value">{{ dashboard.pending_approvals || 0 }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>异常类型分布</span>
            </div>
          </template>
          <div ref="chartAnomaly" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>本月考勤统计</span>
            </div>
          </template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="工作日数">{{ monthlySummary.total_work_days }}</el-descriptions-item>
            <el-descriptions-item label="实际出勤">{{ monthlySummary.actual_work_days }}</el-descriptions-item>
            <el-descriptions-item label="总工时">{{ monthlySummary.total_work_hours }} 小时</el-descriptions-item>
            <el-descriptions-item label="迟到次数">
              <span :class="monthlySummary.late_count > 0 ? 'text-red' : ''">
                {{ monthlySummary.late_count }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="早退次数">
              <span :class="monthlySummary.early_leave_count > 0 ? 'text-red' : ''">
                {{ monthlySummary.early_leave_count }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="薪资调整">
              <span :class="monthlySummary.net_adjustment >= 0 ? 'text-green' : 'text-red'">
                {{ monthlySummary.net_adjustment >= 0 ? '+' : '' }}{{ monthlySummary.net_adjustment }} 元
              </span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt-20">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header flex-between">
              <span>最近异常记录</span>
              <el-button type="primary" link @click="$router.push('/anomalies')">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recentAnomalies" stripe>
            <el-table-column prop="anomaly_date" label="日期" width="120" />
            <el-table-column prop="anomaly_type_label" label="类型" width="100" />
            <el-table-column prop="status_label" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)">{{ row.status_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getEmployeeDashboard, getEmployeeMonthlySummary, getEmployeeAnomalies } from '@/api/employee'
import { Timer, Warning, Bell, Document } from '@element-plus/icons-vue'

const chartAnomaly = ref()
const dashboard = reactive({})
const monthlySummary = reactive({})
const recentAnomalies = ref([])
let anomalyChart = null

const fetchData = async () => {
  const [dashData, summaryData, anomalyData] = await Promise.all([
    getEmployeeDashboard(),
    getEmployeeMonthlySummary(),
    getEmployeeAnomalies({ page_size: 10 })
  ])
  Object.assign(dashboard, dashData)
  Object.assign(monthlySummary, summaryData)
  recentAnomalies.value = anomalyData.items || []
  nextTick(() => {
    renderAnomalyChart()
  })
}

const renderAnomalyChart = () => {
  if (!chartAnomaly.value) return
  if (anomalyChart) {
    anomalyChart.dispose()
  }
  anomalyChart = echarts.init(chartAnomaly.value)
  
  const data = dashboard.anomaly_distribution || []
  const option = {
    tooltip: {
      trigger: 'item'
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        data: data.map(item => ({
          value: item.count,
          name: item.type
        })),
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        label: {
          show: true
        }
      }
    ]
  }
  anomalyChart.setOption(option)
}

const getStatusType = (status) => {
  const types = {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    appealed: 'info',
    confirmed: 'info',
    auto_corrected: 'success'
  }
  return types[status] || 'info'
}

onMounted(() => {
  fetchData()
  window.addEventListener('resize', () => {
    anomalyChart?.resize()
  })
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
.bg-orange { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.bg-red { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
.bg-green { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }

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
  height: 300px;
}

.text-red { color: #f56c6c; font-weight: bold; }
.text-green { color: #67c23a; font-weight: bold; }

.mb-20 { margin-bottom: 20px; }
.mt-20 { margin-top: 20px; }
</style>

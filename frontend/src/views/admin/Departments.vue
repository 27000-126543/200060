<template>
  <div class="departments-page">
    <el-card shadow="hover" class="mb-20">
      <template #header>
        <div class="card-header flex-between">
          <span>部门考勤统计</span>
          <el-date-picker
            v-model="dashboardDate"
            type="date"
            placeholder="选择日期"
            size="small"
            @change="fetchData"
          />
        </div>
      </template>
      <el-table :data="departments" stripe border>
        <el-table-column prop="department_name" label="部门" width="150" />
        <el-table-column prop="total_employees" label="总人数" width="100" align="center" />
        <el-table-column prop="present_employees" label="已到岗" width="100" align="center" />
        <el-table-column prop="attendance_rate" label="出勤率" width="120" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="parseFloat(row.attendance_rate)"
              :color="getProgressColor(row.attendance_rate_value)"
              :stroke-width="12"
            />
          </template>
        </el-table-column>
        <el-table-column prop="no_punch_count" label="未打卡" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.no_punch_count > 0" type="danger" size="small">
              {{ row.no_punch_count }}
            </el-tag>
            <span v-else class="text-success">0</span>
          </template>
        </el-table-column>
        <el-table-column prop="late_count" label="迟到" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.late_count > 0" type="warning" size="small">
              {{ row.late_count }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="early_leave_count" label="早退" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.early_leave_count > 0" type="danger" size="small">
              {{ row.early_leave_count }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="anomaly_count" label="异常总计" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.anomaly_count > 0 ? 'danger' : 'info'" size="small">
              {{ row.anomaly_count }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>各部门出勤率对比</span>
          </template>
          <div ref="chartBar" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>异常分布</span>
          </template>
          <div ref="chartPie" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { getDepartmentsDashboard } from '@/api/admin'

const dashboardDate = ref(new Date())
const departments = ref([])
const chartBar = ref()
const chartPie = ref()
let barChart = null
let pieChart = null

const fetchData = async () => {
  const params = {
    dashboard_date: dashboardDate.value.toISOString().split('T')[0]
  }
  departments.value = await getDepartmentsDashboard(params)
  nextTick(() => {
    renderCharts()
  })
}

const renderCharts = () => {
  renderBarChart()
  renderPieChart()
}

const renderBarChart = () => {
  if (!chartBar.value) return
  if (barChart) barChart.dispose()
  barChart = echarts.init(chartBar.value)
  
  const sorted = [...departments.value].sort((a, b) => a.attendance_rate_value - b.attendance_rate_value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%' }
    },
    yAxis: {
      type: 'category',
      data: sorted.map(item => item.department_name)
    },
    series: [{
      type: 'bar',
      data: sorted.map(item => ({
        value: item.attendance_rate_value * 100,
        itemStyle: {
          color: getBarColor(item.attendance_rate_value)
        }
      })),
      label: {
        show: true,
        position: 'right',
        formatter: '{c}%'
      }
    }]
  }
  barChart.setOption(option)
}

const renderPieChart = () => {
  if (!chartPie.value) return
  if (pieChart) pieChart.dispose()
  pieChart = echarts.init(chartPie.value)
  
  const totalLate = departments.value.reduce((sum, d) => sum + d.late_count, 0)
  const totalEarly = departments.value.reduce((sum, d) => sum + d.early_leave_count, 0)
  const totalNoPunch = departments.value.reduce((sum, d) => sum + d.no_punch_count, 0)
  
  const option = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['40%', '50%'],
      data: [
        { value: totalLate, name: '迟到', itemStyle: { color: '#E6A23C' } },
        { value: totalEarly, name: '早退', itemStyle: { color: '#F56C6C' } },
        { value: totalNoPunch, name: '未打卡', itemStyle: { color: '#909399' } },
      ],
      label: {
        formatter: '{b}: {c} ({d}%)'
      }
    }]
  }
  pieChart.setOption(option)
}

const getProgressColor = (value) => {
  if (value >= 0.95) return '#67c23a'
  if (value >= 0.9) return '#409EFF'
  return '#F56C6C'
}

const getBarColor = (value) => {
  if (value >= 0.95) return '#67c23a'
  if (value >= 0.9) return '#409EFF'
  return '#F56C6C'
}

const handleResize = () => {
  barChart?.resize()
  pieChart?.resize()
}

onMounted(() => {
  fetchData()
  window.addEventListener('resize', handleResize)
})
</script>

<style scoped>
.card-header {
  font-weight: bold;
}

.chart-container {
  height: 300px;
}

.mb-20 { margin-bottom: 20px; }

.text-success {
  color: #67c23a;
  font-weight: bold;
}
</style>

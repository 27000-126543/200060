<template>
  <div class="reports-page">
    <el-card shadow="hover" class="mb-20">
      <template #header>
        <div class="card-header flex-between">
          <span>月度报告列表</span>
          <el-button type="primary" @click="openGenerateDialog">
            <el-icon><DocumentAdd /></el-icon>
            生成报告
          </el-button>
        </div>
      </template>
      <el-table :data="reports" stripe border>
        <el-table-column prop="year_month" label="月份" width="120">
          <template #default="{ row }">
            <el-tag type="primary" size="small">{{ row.month_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="employee_count" label="员工数" width="120" align="center" />
        <el-table-column label="操作" align="center" width="250">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="previewReport(row)">
              <el-icon><View /></el-icon>
              预览
            </el-button>
            <el-button type="success" link size="small" @click="downloadExcel(row)">
              <el-icon><Download /></el-icon>
              Excel
            </el-button>
            <el-button type="warning" link size="small" @click="downloadPdf(row)">
              <el-icon><Download /></el-icon>
              PDF
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="hover" v-if="currentReport">
      <template #header>
        <div class="card-header flex-between">
          <span>报告详情 - {{ currentReport?.month_label }}</span>
          <div>
            <el-button type="success" size="small" @click="downloadExcel(currentReport)">
              <el-icon><Download /></el-icon>
              下载 Excel
            </el-button>
            <el-button type="warning" size="small" @click="downloadPdf(currentReport)">
              <el-icon><Download /></el-icon>
              下载 PDF
            </el-button>
          </div>
        </div>
      </template>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="数据概览" name="overview">
          <el-row :gutter="20">
            <el-col :span="6">
              <el-statistic title="出勤总工时" :value="summary.total_work_hours" suffix="小时" />
            </el-col>
            <el-col :span="6">
              <el-statistic title="平日加班" :value="summary.overtime_hours_weekday" suffix="小时" />
            </el-col>
            <el-col :span="6">
              <el-statistic title="周末加班" :value="summary.overtime_hours_weekend" suffix="小时" />
            </el-col>
            <el-col :span="6">
              <el-statistic title="节假日加班" :value="summary.overtime_hours_holiday" suffix="小时" />
            </el-col>
          </el-row>
        </el-tab-pane>
        <el-tab-pane label="异常统计" name="anomaly">
          <el-row :gutter="20">
            <el-col :span="6">
              <el-statistic title="迟到次数" :value="summary.late_count">
                <template #suffix>
                  <span style="color: #F56C6C">次</span>
                </template>
              </el-statistic>
            </el-col>
            <el-col :span="6">
              <el-statistic title="早退次数" :value="summary.early_leave_count">
                <template #suffix>
                  <span style="color: #F56C6C">次</span>
                </template>
              </el-statistic>
            </el-col>
            <el-col :span="6">
              <el-statistic title="缺勤天数" :value="summary.absent_count">
                <template #suffix>
                  <span style="color: #F56C6C">天</span>
                </template>
              </el-statistic>
            </el-col>
            <el-col :span="6">
              <el-statistic title="缺卡次数" :value="summary.missing_punch_count">
                <template #suffix>
                  <span style="color: #F56C6C">次</span>
                </template>
              </el-statistic>
            </el-col>
          </el-row>
        </el-tab-pane>
        <el-tab-pane label="薪资调整" name="salary">
          <el-row :gutter="20">
            <el-col :span="8">
              <el-card shadow="hover" class="stat-card">
                <p class="label">薪资扣减</p>
                <p class="value red">-{{ summary.salary_deduction || 0 }} 元</p>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="hover" class="stat-card">
                <p class="label">加班补贴</p>
                <p class="value green">+{{ summary.overtime_allowance || 0 }} 元</p>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="hover" class="stat-card">
                <p class="label">净调整</p>
                <p class="value" :class="summary.net_adjustment >= 0 ? 'green' : 'red'">
                  {{ summary.net_adjustment >= 0 ? '+' : '' }}{{ summary.net_adjustment || 0 }} 元
                </p>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="generateDialogVisible" title="生成月度报告" width="400px">
      <el-form :model="generateForm" label-width="100px">
        <el-form-item label="选择月份">
          <el-date-picker
            v-model="generateForm.month"
            type="month"
            placeholder="选择月份"
            style="width: 100%"
            value-format="YYYY-MM"
          />
        </el-form-item>
        <el-form-item label="报告类型">
          <el-radio-group v-model="generateForm.report_type">
            <el-radio value="both">Excel + PDF</el-radio>
            <el-radio value="excel">仅 Excel</el-radio>
            <el-radio value="pdf">仅 PDF</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="handleGenerate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getMonthlyReports, generateMonthlyReport, downloadReport, getEmployees
} from '@/api/admin'
import { DocumentAdd, Download, View } from '@element-plus/icons-vue'

const reports = ref([])
const currentReport = ref(null)
const activeTab = ref('overview')
const generateDialogVisible = ref(false)
const generating = ref(false)
const summary = ref({
  total_work_hours: 0,
  overtime_hours_weekday: 0,
  overtime_hours_weekend: 0,
  overtime_hours_holiday: 0,
  late_count: 0,
  early_leave_count: 0,
  absent_count: 0,
  missing_punch_count: 0,
  salary_deduction: 0,
  overtime_allowance: 0,
  net_adjustment: 0
})

const generateForm = reactive({
  month: '',
  report_type: 'both'
})

const fetchData = async () => {
  reports.value = await getMonthlyReports()
  if (reports.value.length > 0) {
    previewReport(reports.value[0])
  }
}

const previewReport = async (row) => {
  currentReport.value = row
  const employees = await getEmployees({ page_size: 1000 })
  if (employees.items && employees.items.length > 0) {
    const emp = employees.items[0]
    summary.value = {
      total_work_hours: (emp.id * 176).toFixed(1),
      overtime_hours_weekday: (emp.id * 8).toFixed(1),
      overtime_hours_weekend: (emp.id * 4).toFixed(1),
      overtime_hours_holiday: (emp.id * 2).toFixed(1),
      late_count: emp.id * 2,
      early_leave_count: emp.id,
      absent_count: Math.floor(emp.id * 0.5),
      missing_punch_count: emp.id * 3,
      salary_deduction: (emp.id * 100).toFixed(2),
      overtime_allowance: (emp.id * 150).toFixed(2),
      net_adjustment: (emp.id * 50).toFixed(2)
    }
  }
}

const openGenerateDialog = () => {
  generateForm.month = ''
  generateForm.report_type = 'both'
  generateDialogVisible.value = true
}

const handleGenerate = async () => {
  if (!generateForm.month) {
    ElMessage.warning('请选择月份')
    return
  }
  generating.value = true
  try {
    await generateMonthlyReport({
      year_month: generateForm.month,
      report_type: generateForm.report_type
    })
    ElMessage.success('报告生成成功')
    generateDialogVisible.value = false
    fetchData()
  } finally {
    generating.value = false
  }
}

const downloadExcel = (row) => {
  downloadReport('excel', row.year_month)
  ElMessage.success('正在下载 Excel 报告...')
}

const downloadPdf = (row) => {
  downloadReport('pdf', row.year_month)
  ElMessage.success('正在下载 PDF 报告...')
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.card-header {
  font-weight: bold;
}

.mb-20 { margin-bottom: 20px; }

.stat-card {
  text-align: center;
}

.stat-card .label {
  color: #909399;
  font-size: 14px;
  margin: 0 0 10px;
}

.stat-card .value {
  font-size: 24px;
  font-weight: bold;
  margin: 0;
}

.stat-card .green { color: #67c23a; }
.stat-card .red { color: #f56c6c; }
</style>

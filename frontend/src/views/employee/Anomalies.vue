<template>
  <div class="anomalies-page">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header flex-between">
          <span>异常记录</span>
          <div class="filter-bar">
            <el-select v-model="statusFilter" placeholder="状态筛选" size="small" style="width: 120px; margin-right: 10px" @change="fetchData">
              <el-option label="全部" value="" />
              <el-option label="待确认" value="pending" />
              <el-option label="已申诉" value="appealed" />
              <el-option label="已通过" value="approved" />
              <el-option label="已驳回" value="rejected" />
              <el-option label="已自动修正" value="auto_corrected" />
            </el-select>
            <el-button type="primary" link size="small" @click="refreshData">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="tableData" stripe border>
        <el-table-column prop="anomaly_date" label="日期" width="120" />
        <el-table-column prop="anomaly_type_label" label="类型" width="100">
          <template #default="{ row }">
            <el-tag type="danger" size="small">{{ row.anomaly_type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_label" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="deviation_minutes" label="偏差(分钟)" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.deviation_minutes">{{ row.deviation_minutes }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" />
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              type="primary"
              link
              size="small"
              @click="openExplainDialog(row)"
            >
              提交说明
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @size-change="fetchData"
        @current-change="fetchData"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" title="提交异常说明" width="500px">
      <el-form :model="explainForm" label-width="100px">
        <el-form-item label="异常类型">
          <el-tag type="danger">{{ currentAnomaly?.anomaly_type_label }}</el-tag>
        </el-form-item>
        <el-form-item label="异常描述">
          <span>{{ currentAnomaly?.description }}</span>
        </el-form-item>
        <el-form-item label="说明" prop="reason">
          <el-input
            v-model="explainForm.reason"
            type="textarea"
            :rows="4"
            placeholder="请输入异常说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitExplain">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getEmployeeAnomalies, submitApproval } from '@/api/employee'
import { Refresh } from '@element-plus/icons-vue'

const tableData = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const dialogVisible = ref(false)
const currentAnomaly = ref(null)
const submitting = ref(false)
let refreshTimer = null

const explainForm = reactive({
  reason: ''
})

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

const fetchData = async () => {
  const params = {
    page: page.value,
    page_size: pageSize.value
  }
  if (statusFilter.value) {
    params.status = statusFilter.value
  }
  const res = await getEmployeeAnomalies(params)
  tableData.value = res.items || []
  total.value = res.total || 0
}

const refreshData = () => {
  fetchData()
}

const openExplainDialog = (row) => {
  currentAnomaly.value = row
  explainForm.reason = ''
  dialogVisible.value = true
}

const submitExplain = async () => {
  if (!explainForm.reason) {
    ElMessage.warning('请输入异常说明')
    return
  }
  submitting.value = true
  try {
    await submitApproval({
      approval_type: 'anomaly_explain',
      related_date: currentAnomaly.value.anomaly_date,
      reason: explainForm.reason
    })
    ElMessage.success('提交成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchData()
  refreshTimer = setInterval(fetchData, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.card-header {
  font-weight: bold;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

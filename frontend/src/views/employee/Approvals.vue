<template>
  <div class="approvals-page">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header flex-between">
          <span>审批申请</span>
          <el-button type="primary" @click="openApplyDialog">
            <el-icon><Plus /></el-icon>
            新申请
          </el-button>
        </div>
      </template>
      <el-table :data="tableData" stripe border>
        <el-table-column prop="approval_type_label" label="类型" width="120">
          <template #default="{ row }">
            <el-tag type="primary" size="small">{{ row.approval_type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_label" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="related_date" label="日期" width="120" />
        <el-table-column prop="reason" label="原因" />
        <el-table-column prop="created_at" label="提交时间" width="160" />
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

    <el-dialog v-model="dialogVisible" title="提交申请" width="500px">
      <el-form :model="applyForm" label-width="100px">
        <el-form-item label="申请类型">
          <el-radio-group v-model="applyForm.approval_type" @change="onTypeChange">
            <el-radio value="supplementary_punch">补卡申请</el-radio>
            <el-radio value="leave">请假</el-radio>
            <el-radio value="anomaly_explain">异常说明</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="日期" v-if="applyForm.approval_type">
          <el-date-picker
            v-model="applyForm.related_date"
            type="date"
            placeholder="选择日期"
            style="width: 100%"
          />
        </el-form-item>
        <template v-if="applyForm.approval_type === 'supplementary_punch'">
          <el-form-item label="补卡类型">
            <el-radio-group v-model="applyForm.supplementary_punch_type">
              <el-radio value="clock_in">上班卡</el-radio>
              <el-radio value="clock_out">下班卡</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="补卡时间">
            <el-time-picker
              v-model="applyForm.supplementary_punch_time"
              placeholder="选择时间"
              style="width: 100%"
            />
          </el-form-item>
        </template>
        <el-form-item label="申请原因">
          <el-input
            v-model="applyForm.reason"
            type="textarea"
            :rows="4"
            placeholder="请详细说明原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitApply">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { getEmployeeApprovals, submitApproval } from '@/api/employee'
import { Plus } from '@element-plus/icons-vue'

const tableData = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dialogVisible = ref(false)
const submitting = ref(false)

const applyForm = reactive({
  approval_type: '',
  related_date: '',
  reason: '',
  supplementary_punch_type: 'clock_in',
  supplementary_punch_time: ''
})

const getStatusType = (status) => {
  const types = {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    cancelled: 'info'
  }
  return types[status] || 'info'
}

const onTypeChange = () => {
  applyForm.supplementary_punch_time = ''
}

const fetchData = async () => {
  const res = await getEmployeeApprovals({
    page: page.value,
    page_size: pageSize.value
  })
  tableData.value = res.items || []
  total.value = res.total || 0
}

const openApplyDialog = () => {
  applyForm.approval_type = 'supplementary_punch'
  applyForm.related_date = new Date()
  applyForm.reason = ''
  applyForm.supplementary_punch_type = 'clock_in'
  applyForm.supplementary_punch_time = ''
  dialogVisible.value = true
}

const submitApply = async () => {
  if (!applyForm.approval_type || !applyForm.related_date || !applyForm.reason) {
    ElMessage.warning('请填写完整信息')
    return
  }

  const data = {
    approval_type: applyForm.approval_type,
    related_date: dayjs(applyForm.related_date).format('YYYY-MM-DD'),
    reason: applyForm.reason
  }

  if (applyForm.approval_type === 'supplementary_punch') {
    if (!applyForm.supplementary_punch_time) {
      ElMessage.warning('请选择补卡时间')
      return
    }
    const dateStr = dayjs(applyForm.related_date).format('YYYY-MM-DD')
    const timeStr = dayjs(applyForm.supplementary_punch_time).format('HH:mm:ss')
    data.supplementary_punch_time = `${dateStr} ${timeStr}`
    data.supplementary_punch_type = applyForm.supplementary_punch_type
  }

  submitting.value = true
  try {
    await submitApproval(data)
    ElMessage.success('申请提交成功')
    dialogVisible.value = false
    fetchData()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchData()
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

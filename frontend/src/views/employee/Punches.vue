<template>
  <div class="punches-page">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header flex-between">
          <span>打卡记录</span>
          <div class="filter-bar">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              size="small"
              style="margin-right: 10px"
            />
            <el-button type="primary" size="small" @click="fetchData">
              查询
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="tableData" stripe border>
        <el-table-column prop="punch_date" label="日期" width="120" />
        <el-table-column prop="punch_time" label="时间" width="100" />
        <el-table-column prop="punch_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.punch_type_code === 'clock_in' ? 'success' : 'info'">
              {{ row.punch_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column prop="is_supplementary" label="补卡" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_supplementary" color="#e6a23c">
              <Check />
            </el-icon>
            <span v-else>-</span>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getEmployeePunches } from '@/api/employee'
import { Check } from '@element-plus/icons-vue'

const tableData = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dateRange = ref([])

const fetchData = async () => {
  const params = {
    page: page.value,
    page_size: pageSize.value
  }
  if (dateRange.value && dateRange.value.length === 2) {
    params.start_date = dateRange.value[0]
    params.end_date = dateRange.value[1]
  }
  const res = await getEmployeePunches(params)
  tableData.value = res.items || []
  total.value = res.total || 0
}

onMounted(() => {
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

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

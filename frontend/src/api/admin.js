import request from '@/utils/request'

export function getDashboardOverview(params) {
  return request({
    url: '/admin/dashboard-overview',
    method: 'get',
    params
  })
}

export function getDepartmentsDashboard(params) {
  return request({
    url: '/admin/departments-dashboard',
    method: 'get',
    params
  })
}

export function getAttendanceTrend(params) {
  return request({
    url: '/admin/attendance-trend',
    method: 'get',
    params
  })
}

export function getMonthlyReports() {
  return request({
    url: '/admin/monthly-reports',
    method: 'get'
  })
}

export function generateMonthlyReport(data) {
  return request({
    url: '/admin/generate-report',
    method: 'post',
    data
  })
}

export function downloadReport(reportType, yearMonth) {
  const token = localStorage.getItem('token')
  const url = `/api/admin/reports/download/${reportType}/${yearMonth}`
  return fetch(url, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }).then(response => {
    if (!response.ok) {
      throw new Error('下载失败')
    }
    const filename = response.headers.get('Content-Disposition')
      ? response.headers.get('Content-Disposition').split('filename=')[1].replace(/"/g, '')
      : `attendance_report_${yearMonth}.${reportType === 'excel' ? 'xlsx' : 'pdf'}`
    
    return response.blob().then(blob => {
      const downloadUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(downloadUrl)
    })
  })
}

export function getSchedulingPlans(params) {
  return request({
    url: '/admin/scheduling-plans',
    method: 'get',
    params
  })
}

export function applySchedulingPlan(planId) {
  return request({
    url: `/admin/scheduling-plans/${planId}/apply`,
    method: 'post'
  })
}

export function getEmployees(params) {
  return request({
    url: '/admin/employees',
    method: 'get',
    params
  })
}

export function getDepartments() {
  return request({
    url: '/admin/departments',
    method: 'get'
  })
}

export function getHolidays(params) {
  return request({
    url: '/admin/holidays',
    method: 'get',
    params
  })
}

import request from '@/utils/request'

export function getEmployeeDashboard(params) {
  return request({
    url: '/employee/dashboard',
    method: 'get',
    params
  })
}

export function getEmployeePunches(params) {
  return request({
    url: '/employee/punches',
    method: 'get',
    params
  })
}

export function getEmployeeAnomalies(params) {
  return request({
    url: '/employee/anomalies',
    method: 'get',
    params
  })
}

export function getEmployeeApprovals(params) {
  return request({
    url: '/employee/approvals',
    method: 'get',
    params
  })
}

export function submitApproval(data) {
  return request({
    url: '/employee/approvals',
    method: 'post',
    data
  })
}

export function getEmployeeMonthlySummary(params) {
  return request({
    url: '/employee/monthly-summary',
    method: 'get',
    params
  })
}

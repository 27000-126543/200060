import requests
import json
import os

# 登录获取token
login_url = 'http://localhost:8000/api/auth/login'
login_data = {'username': 'EMP0001', 'password': '123456'}
response = requests.post(login_url, json=login_data)
data = response.json()
token = data['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 测试生成月度报告
print('=' * 60)
print('测试生成月度报告')
print('=' * 60)
generate_url = 'http://localhost:8000/api/admin/generate-report'
generate_data = {'year_month': '2026-06', 'report_type': 'attendance'}
response = requests.post(generate_url, json=generate_data, headers=headers)
print('生成报告状态:', response.status_code)
print('生成报告响应:', json.dumps(response.json(), ensure_ascii=False, indent=2))

# 测试下载Excel报告
print('\n' + '=' * 60)
print('测试下载Excel报告')
print('=' * 60)
download_url = f'http://localhost:8000/api/admin/reports/download/xlsx/2026-06'
response = requests.get(download_url, headers=headers)
print('下载Excel状态:', response.status_code)
print('Content-Type:', response.headers.get('Content-Type'))
print('Content-Disposition:', response.headers.get('Content-Disposition'))
if response.status_code == 200:
    with open('/tmp/test_report.xlsx', 'wb') as f:
        f.write(response.content)
    print(f'Excel报告已保存，大小: {len(response.content)} bytes')
    print(f'文件存在: {os.path.exists("/tmp/test_report.xlsx")}')

# 测试下载PDF报告
print('\n' + '=' * 60)
print('测试下载PDF报告')
print('=' * 60)
download_url = f'http://localhost:8000/api/admin/reports/download/pdf/2026-06'
response = requests.get(download_url, headers=headers)
print('下载PDF状态:', response.status_code)
print('Content-Type:', response.headers.get('Content-Type'))
print('Content-Disposition:', response.headers.get('Content-Disposition'))
if response.status_code == 200:
    with open('/tmp/test_report.pdf', 'wb') as f:
        f.write(response.content)
    print(f'PDF报告已保存，大小: {len(response.content)} bytes')
    print(f'文件存在: {os.path.exists("/tmp/test_report.pdf")}')

# 测试部门考勤数据
print('\n' + '=' * 60)
print('测试部门考勤数据')
print('=' * 60)
dept_url = 'http://localhost:8000/api/admin/departments-dashboard'
response = requests.get(dept_url, headers=headers)
print('部门考勤状态:', response.status_code)
result = response.json()
print('部门考勤数据:')
for dept in result[:3]:
    print(f'  {dept.get("department_name")}: 出勤率 {dept.get("attendance_rate_display")}')

# 测试月度报告列表
print('\n' + '=' * 60)
print('测试月度报告列表')
print('=' * 60)
reports_url = 'http://localhost:8000/api/admin/monthly-reports'
response = requests.get(reports_url, headers=headers)
print('月度报告列表状态:', response.status_code)
print('月度报告列表:', json.dumps(response.json(), ensure_ascii=False, indent=2))

import requests
import json

# 登录获取token
login_url = 'http://localhost:8000/api/auth/login'
login_data = {'username': 'EMP0001', 'password': '123456'}
response = requests.post(login_url, json=login_data)
print('登录状态:', response.status_code)
data = response.json()
print('登录响应:', json.dumps(data, ensure_ascii=False, indent=2))
token = data['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 测试员工Dashboard
dash_url = 'http://localhost:8000/api/employee/dashboard'
response = requests.get(dash_url, headers=headers)
print('\n员工Dashboard状态:', response.status_code)
print('员工Dashboard数据:', json.dumps(response.json(), ensure_ascii=False, indent=2))

# 测试管理员Dashboard
admin_url = 'http://localhost:8000/api/admin/dashboard-overview'
response = requests.get(admin_url, headers=headers)
print('\n管理员Dashboard状态:', response.status_code)
print('管理员Dashboard数据:', json.dumps(response.json(), ensure_ascii=False, indent=2))

# 测试出勤率趋势
trend_url = 'http://localhost:8000/api/admin/attendance-trend'
response = requests.get(trend_url, headers=headers)
print('\n出勤率趋势状态:', response.status_code)
print('出勤率趋势数据:', json.dumps(response.json(), ensure_ascii=False, indent=2))

# 测试打卡记录
punches_url = 'http://localhost:8000/api/employee/punches'
response = requests.get(punches_url, headers=headers)
print('\n打卡记录状态:', response.status_code)
result = response.json()
print(f'打卡记录总数: {result.get("total", 0)}')
if result.get("items"):
    print('前3条记录:', json.dumps(result["items"][:3], ensure_ascii=False, indent=2))

# 测试异常记录
anomalies_url = 'http://localhost:8000/api/employee/anomalies'
response = requests.get(anomalies_url, headers=headers)
print('\n异常记录状态:', response.status_code)
result = response.json()
print(f'异常记录总数: {result.get("total", 0)}')
if result.get("items"):
    print('前3条记录:', json.dumps(result["items"][:3], ensure_ascii=False, indent=2))

"""
组件配置API测试脚本
运行前请确保：
1. 已执行数据库迁移
2. Django开发服务器正在运行
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_create_component():
    """测试创建组件"""
    print("\n=== 测试创建组件 ===")
    
    # 创建一个下拉框组件
    data = {
        "name": "订单状态",
        "type": "select",
        "options": [
            {"value": "pending", "label": "待处理"},
            {"value": "processing", "label": "处理中"},
            {"value": "completed", "label": "已完成"},
            {"value": "cancelled", "label": "已取消"}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/components/save/",
        json=data
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    
    if response.status_code == 200:
        return response.json()['data']['id']
    return None

def test_get_components():
    """测试获取组件列表"""
    print("\n=== 测试获取组件列表 ===")
    
    response = requests.get(f"{BASE_URL}/api/components/")
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_get_component_detail(component_id):
    """测试获取组件详情"""
    print(f"\n=== 测试获取组件详情 (ID: {component_id}) ===")
    
    response = requests.get(f"{BASE_URL}/api/components/{component_id}/")
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_update_component(component_id):
    """测试更新组件"""
    print(f"\n=== 测试更新组件 (ID: {component_id}) ===")
    
    data = {
        "id": component_id,
        "name": "订单状态（已更新）",
        "type": "select",
        "options": [
            {"value": "pending", "label": "待处理"},
            {"value": "processing", "label": "处理中"},
            {"value": "completed", "label": "已完成"},
            {"value": "shipped", "label": "已发货"},
            {"value": "cancelled", "label": "已取消"}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/components/save/",
        json=data
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_create_radio_component():
    """测试创建单选框组件"""
    print("\n=== 测试创建单选框组件 ===")
    
    data = {
        "name": "是否启用",
        "type": "radio",
        "options": [
            {"value": "1", "label": "启用"},
            {"value": "0", "label": "禁用"}
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/components/save/",
        json=data
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_search_components():
    """测试搜索组件"""
    print("\n=== 测试搜索组件 ===")
    
    response = requests.get(f"{BASE_URL}/api/components/?search=订单")
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_get_usage(component_id):
    """测试获取使用情况"""
    print(f"\n=== 测试获取使用情况 (ID: {component_id}) ===")
    
    response = requests.get(f"{BASE_URL}/api/components/{component_id}/usage/")
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_delete_component(component_id):
    """测试删除组件"""
    print(f"\n=== 测试删除组件 (ID: {component_id}) ===")
    
    response = requests.delete(f"{BASE_URL}/api/components/delete/{component_id}/")
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    print("开始测试组件配置API...")
    
    # 1. 创建组件
    component_id = test_create_component()
    
    if component_id:
        # 2. 获取列表
        test_get_components()
        
        # 3. 获取详情
        test_get_component_detail(component_id)
        
        # 4. 更新组件
        test_update_component(component_id)
        
        # 5. 创建单选框组件
        test_create_radio_component()
        
        # 6. 搜索组件
        test_search_components()
        
        # 7. 获取使用情况
        test_get_usage(component_id)
        
        # 8. 删除组件
        test_delete_component(component_id)
    
    print("\n=== 测试完成 ===")

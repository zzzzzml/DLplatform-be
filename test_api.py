import requests
import json
import base64

# 基础URL
BASE_URL = "http://localhost:5000"

def test_init_database():
    """测试数据库初始化"""
    print("=== 测试数据库初始化 ===")
    response = requests.get(f"{BASE_URL}/init-db")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

def test_get_experiment_requirements():
    """测试获取实验要求"""
    print("=== 测试获取实验要求 ===")
    experiment_id = 1
    response = requests.get(f"{BASE_URL}/student/experiment/requirements?experiment_id={experiment_id}")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_publish_experiment():
    """测试发布实验要求"""
    print("=== 测试发布实验要求 ===")
    
    # 创建一个简单的测试文件内容
    test_content = "这是一个测试文件的内容"
    file_content_base64 = base64.b64encode(test_content.encode('utf-8')).decode('utf-8')
    
    data = {
        "experiment_name": "测试实验",
        "class_id": 1,
        "description": "这是一个测试实验的详细要求。",
        "deadline": "2024-12-31 23:59:59",
        "attachments": [
            {
                "file_name": "测试文件.txt",
                "file_content": file_content_base64
            }
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/teacher/experiment/publish",
        json=data,
        headers={'Content-Type': 'application/json'}
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_error_cases():
    """测试错误情况"""
    print("=== 测试错误情况 ===")
    
    # 测试缺少参数
    print("1. 测试缺少experiment_id参数:")
    response = requests.get(f"{BASE_URL}/student/experiment/requirements")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()
    
    # 测试不存在的实验ID
    print("2. 测试不存在的experiment_id:")
    response = requests.get(f"{BASE_URL}/student/experiment/requirements?experiment_id=999")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()
    
    # 测试发布实验时缺少必需参数
    print("3. 测试发布实验时缺少必需参数:")
    data = {
        "class_id": 1,
        "description": "测试描述"
        # 缺少experiment_name
    }
    response = requests.post(
        f"{BASE_URL}/teacher/experiment/publish",
        json=data,
        headers={'Content-Type': 'application/json'}
    )
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

if __name__ == "__main__":
    print("开始API测试...\n")
    
    try:
        # 初始化数据库
        test_init_database()
        
        # 测试获取实验要求
        test_get_experiment_requirements()
        
        # 测试发布实验要求
        test_publish_experiment()
        
        # 测试错误情况
        test_error_cases()
        
        print("API测试完成！")
        
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到服务器，请确保Flask应用正在运行。")
    except Exception as e:
        print(f"测试过程中发生错误: {e}") 
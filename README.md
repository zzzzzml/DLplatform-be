# DLplatform-be

DLplatform 后端服务，使用 Flask 框架开发，提供深度学习实验管理、用户注册、文件上传等功能。

## 功能特性
- 用户注册接口
- 学生端浏览实验要求
- 教师端发布实验要求
- 文件上传和管理
- 数据库支持

## 安装与运行

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 创建数据库
```sql
CREATE DATABASE dlplatform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. 运行应用
```bash
python app.py
```

应用将在 `http://localhost:5000` 启动。

## API 文档

### 系统接口
- 路径: `/init-db`
- 方法: `GET`
- 描述: 初始化数据库表

### 注册接口
- 路径: `/register`
- 方法: `POST`
- 描述: 用户注册
- 请求参数:
```json
{
    "username": "用户名",
    "password": "密码",
    "user_type": "用户类型(student/teacher)",
    "realname": "真实姓名",
    "email": "邮箱地址"
}
```
- 响应数据:
成功:
```json
{
    "code": 200,
    "message": "注册成功"
}
```
失败:
```json
{
    "code": 400/500,
    "message": "错误信息"
}
```

### 学生端接口
#### 获取实验要求
- URL: `/student/experiment/requirements`
- 方法: GET
- 参数: `experiment_id` (查询参数)
- 示例: `GET /student/experiment/requirements?experiment_id=1`

### 教师端接口
#### 发布实验要求
- URL: `/teacher/experiment/publish`
- 方法: POST
- 请求体: JSON格式
```json
{
    "experiment_name": "实验名称",
    "class_id": 1,
    "description": "实验详细要求",
    "deadline": "2024-12-31 23:59:59",
    "attachments": [
        {
            "file_name": "文件名.txt",
            "file_content": "base64编码的文件内容"
        }
    ]
}
```

#### 下载实验附件
- URL: `/download/attachment/<attachment_id>`
- 方法: GET

## 数据库结构

### 用户表 (users)
- user_id: 用户ID
- username: 用户名
- password: 密码
- user_type: 角色 (student/teacher)
- real_name: 真实姓名
- student_id: 学号
- profile_completed: 资料是否完善
- class_id: 所在班级ID
- email: 邮箱
- created_at: 创建时间

### 班级表 (classes)
- class_id: 班级ID
- class_name: 班级名称

### 实验表 (experiments)
- experiment_id: 实验ID
- experiment_name: 实验名称
- class_id: 所属班级
- description: 实验要求
- deadline: 截止时间
- created_at: 创建时间

### 实验附件表 (experiment_attachments)
- attachment_id: 附件ID
- experiment_id: 关联实验
- file_name: 文件名
- file_path: 存储路径
- created_at: 创建时间

## 文件结构
```
DLplatform-be/
├── app.py              # 主应用文件（包含数据库连接、模型和API）
├── requirements.txt    # 依赖项
├── README.md           # 说明文档
└── uploads/            # 文件上传目录
    └── experiments/    # 实验附件目录
```

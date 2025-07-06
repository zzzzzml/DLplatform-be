# DLplatform-be Flask后端

这是一个基于Flask的深度学习平台后端，提供实验管理功能。

## 功能特性

- 学生端浏览实验要求
- 教师端发布实验要求
- 文件上传和管理
- 数据库支持

## 安装和运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 数据库配置

确保MySQL数据库已安装并运行，创建数据库：

```sql
CREATE DATABASE dlplatform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. 初始化数据库

启动应用后，访问以下URL初始化数据库和测试数据：

```
http://localhost:5000/init-db
```

### 4. 运行应用

有两种方式启动应用：

**方式一：直接运行app.py**
```bash
python app.py
```

**方式二：使用启动脚本（推荐）**
```bash
python run.py
```

应用将在 `http://localhost:5000` 启动。

## API接口

### 学生端接口

#### 获取实验要求
- **URL**: `/student/experiment/requirements`
- **方法**: GET
- **参数**: `experiment_id` (查询参数)
- **示例**: `GET /student/experiment/requirements?experiment_id=1`

### 教师端接口

#### 发布实验要求
- **URL**: `/teacher/experiment/publish`
- **方法**: POST
- **请求体**:
```json
{
    "experiment_name": "实验名称",
    "class_id": 1,
    "description": "实验描述",
    "deadline": "2024-02-01 23:59:59",
    "attachments": [
        {
            "file_name": "文件名.pdf",
            "file_content": "base64编码的文件内容"
        }
    ]
}
```

## 数据库结构

### 用户表 (users)
- user_id: 用户ID
- username: 用户名
- password: 密码
- role: 角色 (student/teacher)
- created_time: 创建时间

### 班级表 (classes)
- class_id: 班级ID
- class_name: 班级名称
- teacher_id: 教师ID
- created_time: 创建时间

### 实验表 (experiments)
- experiment_id: 实验ID
- experiment_name: 实验名称
- class_id: 所属班级
- teacher_id: 发布教师
- description: 实验要求
- publish_time: 发布时间
- deadline: 截止时间

### 实验附件表 (experiment_attachments)
- attachment_id: 附件ID
- experiment_id: 关联实验
- file_name: 文件名
- file_path: 存储路径
- file_size: 文件大小(KB)
- upload_time: 上传时间

## 文件结构

```
DLplatform-be/
├── app.py              # 主应用文件
├── config.py           # 配置文件
├── run.py              # 启动脚本
├── test_api.py         # API测试脚本
├── requirements.txt    # 依赖项
├── README.md          # 说明文档
└── uploads/           # 文件上传目录
```

## 测试

运行测试脚本来验证API功能：

```bash
python test_api.py
```

确保在运行测试前，Flask应用已经启动。
# DLplatform-be

DLplatform 后端服务，使用 Flask 框架开发。

## 功能

- 用户注册接口

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

## API 文档

### 注册接口

- 路径: `/register`
- 方法: `POST`
- 描述: 用户注册

#### 请求参数

```json
{
    "username": "用户名",
    "password": "密码",
    "user_type": "用户类型(student/teacher)",
    "realname": "真实姓名",
    "email": "邮箱地址"
}
```

#### 响应数据

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
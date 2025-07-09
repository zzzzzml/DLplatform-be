from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timezone
import re
import os
import traceback
from config import config

app = Flask(__name__)

# 获取配置
config_name = os.environ.get('FLASK_CONFIG') or 'default'
app.config.from_object(config[config_name])

# 初始化扩展
db = SQLAlchemy(app)
CORS(app)

# 数据模型
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column('user_id', db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    real_name = db.Column(db.String(50))
    email = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'))
    role = db.Column('user_type', db.Enum('student', 'teacher'), nullable=False, default='student')
    password = db.Column(db.String(50), nullable=False)
    created_at = db.Column('created_at', db.TIMESTAMP, default=db.func.current_timestamp())

class Class(db.Model):
    __tablename__ = 'classes'
    
    id = db.Column('class_id', db.Integer, primary_key=True)
    name = db.Column('class_name', db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, nullable=False)

# 辅助函数
def validate_email(email):
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_current_user():
    """获取当前登录用户（简化处理，假设用户已登录）"""
    # 从请求头中获取用户信息
    user_id = request.headers.get('User-ID')
    if not user_id:
        # 如果没有提供User-ID，使用默认用户（假设已登录）
        return User.query.first()
    return User.query.get(int(user_id))

def check_email_conflict(email, current_user_id):
    """检查邮箱是否已被其他用户使用"""
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.id != current_user_id:
        return existing_user.email
    return None

def check_student_id_conflict(student_id, current_user_id):
    """检查学号是否已被其他用户使用"""
    existing_user = User.query.filter_by(student_id=student_id).first()
    if existing_user and existing_user.id != current_user_id:
        return existing_user.student_id
    return None

# 路由
@app.route('/profile/update', methods=['POST'])
def update_profile():
    """
    更新用户个人资料
    """
    try:
        # 获取当前用户（本地测试用第一个用户）
        current_user = User.query.first()
        if not current_user:
            return jsonify({
                'code': 500,
                'message': '数据库没有用户，请先初始化'
            }), 500

        data = request.get_json()
        if not data:
            return jsonify({
                'code': 400,
                'message': '请求数据不能为空'
            }), 400

        real_name = data.get('real_name')
        email = data.get('email')
        student_id = data.get('student_id')
        class_id = data.get('class_id')

        # 角色权限检查
        forbidden_fields = []
        if current_user.role == 'teacher':
            if student_id is not None:
                forbidden_fields.append('student_id')
            if class_id is not None:
                forbidden_fields.append('class_id')
        if forbidden_fields:
            return jsonify({
                'code': 403,
                'message': '无权修改学号/班级信息',
                'forbidden_fields': forbidden_fields
            }), 403

        # 邮箱格式校验
        if email and not validate_email(email):
            return jsonify({
                'code': 400,
                'message': '参数错误：邮箱格式不正确'
            }), 400

        # 邮箱冲突校验
        if email:
            conflict_email = check_email_conflict(email, current_user.id)
            if conflict_email:
                return jsonify({
                    'code': 409,
                    'message': '邮箱已被使用',
                    'conflict_email': conflict_email
                }), 409

        # 学号冲突校验（仅学生）
        if student_id and current_user.role == 'student':
            conflict_student_id = check_student_id_conflict(student_id, current_user.id)
            if conflict_student_id:
                return jsonify({
                    'code': 409,
                    'message': '学号已被使用',
                    'conflict_student_id': conflict_student_id
                }), 409

        # 班级存在性校验（仅学生，且有class_id时）
        if class_id and current_user.role == 'student':
            class_exists = Class.query.get(class_id)
            if not class_exists:
                return jsonify({
                    'code': 404,
                    'message': f'班级不存在，class_id: {class_id}'
                }), 404

        # 更新字段
        if real_name is not None:
            current_user.real_name = real_name
        if email is not None:
            current_user.email = email
        if student_id is not None and current_user.role == 'student':
            current_user.student_id = student_id
        if class_id is not None and current_user.role == 'student':
            current_user.class_id = class_id

        db.session.commit()
        update_time = datetime.now(timezone.utc)

        return jsonify({
            'code': 200,
            'message': '资料更新成功',
            'data': {
                'update_time': update_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        print("发生异常：", e)
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '服务器内部错误，资料更新失败'
        }), 500

# 测试路由
@app.route('/')
def hello_world():
    return 'Hello, Flask! 个人资料修改接口已就绪'

# 创建数据库表
@app.route('/init-db')
def init_db():
    """初始化数据库表"""
    try:
        print("检查数据库表...")
        
        # 检查是否已有数据
        existing_classes = Class.query.count()
        existing_users = User.query.count()
        
        print(f"现有班级数量: {existing_classes}")
        print(f"现有用户数量: {existing_users}")
        
        # 先创建用户数据（因为班级表需要引用教师）
        if existing_users == 0:
            print("开始创建用户数据...")
            user1 = User(
                username='student1',
                real_name='张三',
                email='zhangsan@example.com',
                student_id='2025001',
                role='student',
                password='123456'
            )
            user2 = User(
                username='teacher1',
                real_name='李老师',
                email='teacher@example.com',
                role='teacher',
                password='123456'
            )
            db.session.add(user1)
            db.session.add(user2)
            db.session.commit()
            print("用户数据创建成功")
        
        # 再创建班级数据（引用已存在的教师）
        if existing_classes == 0:
            print("开始创建班级数据...")
            # 获取教师用户ID
            teacher = User.query.filter_by(role='teacher').first()
            if teacher:
                class1 = Class(name='计算机科学1班', teacher_id=teacher.id)
                class2 = Class(name='计算机科学2班', teacher_id=teacher.id)
                db.session.add(class1)
                db.session.add(class2)
                db.session.commit()
                print("班级数据创建成功")
                
                # 更新学生用户的班级ID
                student = User.query.filter_by(role='student').first()
                if student:
                    student.class_id = class1.id
                    db.session.commit()
                    print("学生班级关联成功")
        
        return jsonify({
            'code': 200,
            'message': '数据库初始化成功'
        }), 200
        
    except Exception as e:
        print("数据库初始化异常：", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'数据库初始化失败: {str(e)}'
        }), 500

if __name__ == '__main__':
    print("启动Flask应用（数据库版本）...")
    print("访问地址: http://localhost:5000")
    print("个人资料修改接口: POST http://localhost:5000/profile/update")
    print("数据库初始化: http://localhost:5000/init-db")
    print("\n按 Ctrl+C 停止应用")
    
    app.run(debug=True, host='0.0.0.0', port=5000)

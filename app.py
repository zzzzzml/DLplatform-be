from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os
from dotenv import load_dotenv
import pymysql

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:zjz13931512208.@localhost/dlplatform'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# 初始化扩展
pymysql.install_as_MySQLdb()
db = SQLAlchemy(app)
CORS(app)

# 用户模型
class User(db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    user_type = db.Column(db.Enum('student', 'teacher'), nullable=False)
    real_name = db.Column(db.String(50))
    student_id = db.Column(db.String(20))
    profile_completed = db.Column(db.Boolean, default=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'))
    email = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'user_type': self.user_type,
            'real_name': self.real_name,
            'student_id': self.student_id,
            'profile_completed': self.profile_completed,
            'class_id': self.class_id,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# 班级模型（用于外键约束）
class Class(db.Model):
    __tablename__ = 'classes'
    
    class_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_name = db.Column(db.String(50), nullable=False)
    
    def __repr__(self):
        return f'<Class {self.class_name}>'

# 注册接口
@app.route('/register', methods=['POST'])
def register():
    try:
        # 获取请求数据
        data = request.get_json()
        
        # 验证必需字段
        required_fields = ['username', 'password', 'user_type', 'realname', 'email']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'code': 400,
                    'message': f'缺少必需字段: {field}'
                }), 400
        
        # 验证用户类型
        if data['user_type'] not in ['student', 'teacher']:
            return jsonify({
                'code': 400,
                'message': '用户类型必须是 student 或 teacher'
            }), 400
        
        # 检查用户名是否已存在
        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({
                'code': 400,
                'message': '用户名已存在'
            }), 400
        
        # 检查邮箱是否已存在
        existing_email = User.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({
                'code': 400,
                'message': '邮箱已被注册'
            }), 400
        
        # 创建新用户
        new_user = User(
            username=data['username'],
            password=data['password'],  # 注意：实际项目中应该加密密码
            user_type=data['user_type'],
            real_name=data['realname'],
            email=data['email'],
            profile_completed=False,  # 默认为False
            student_id=None,  # 默认为空
            class_id=None  # 默认为空
        )
        
        # 保存到数据库
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '注册成功'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"注册错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

# 获取用户信息接口
@app.route('/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'code': 404,
                'message': '用户不存在'
            }), 404
        
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': user.to_dict()
        })
        
    except Exception as e:
        print(f"获取用户信息错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

# 获取所有用户接口
@app.route('/users', methods=['GET'])
def get_users():
    try:
        users = User.query.all()
        users_data = [user.to_dict() for user in users]
        
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': users_data
        })
        
    except Exception as e:
        print(f"获取用户列表错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

# 健康检查接口
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'code': 200,
        'message': '服务器运行正常',
        'timestamp': datetime.utcnow().isoformat()
    })

# 登录接口
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({
                'code': 400,
                'message': '缺少用户名或密码'
            }), 200
        user = User.query.filter_by(username=username).first()
        if not user or user.password != password:
            return jsonify({
                'code': 401,
                'message': '用户名或密码错误'
            }), 200
        # 判断用户类型并返回不同重定向地址
        if user.user_type == 'student':
            return jsonify({
                'code': 200,
                'message': '登录成功',
                'data': {
                    'user_id': user.user_id,
                    'user_type': 'student',
                    'realname': user.real_name,
                    'email': user.email,
                    'redirect_url': '/student/dashboard'
                }
            }), 200
        elif user.user_type == 'teacher':
            return jsonify({
                'code': 200,
                'message': '登录成功，请前往验证界面',
                'data': {
                    'user_id': user.user_id,
                    'user_type': 'teacher',
                    'realname': user.real_name,
                    'email': user.email,
                    'redirect_url': '/teacher/verification'
                }
            }), 200
        else:
            return jsonify({
                'code': 401,
                'message': '用户类型错误'
            }), 200
    except Exception as e:
        print(f"登录错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 200

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'code': 404,
        'message': '请求的资源不存在'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'code': 500,
        'message': '服务器内部错误'
    }), 500

@app.route('/')
def index():
    return '后端服务已启动'

if __name__ == '__main__':
    # 创建数据库表
    with app.app_context():
        db.create_all()
        print("数据库表创建完成")
    app.run(debug=True, host='0.0.0.0', port=5000) 
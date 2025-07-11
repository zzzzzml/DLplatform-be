from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os
import pymysql
import sys
import base64

# 创建Flask应用
app = Flask(__name__)

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/dlplatform'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

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

# 实验模型
class Experiment(db.Model):
    __tablename__ = 'experiments'
    
    experiment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'))
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Experiment {self.experiment_name}>'
        
    def to_dict(self):
        return {
            'experiment_id': self.experiment_id,
            'experiment_name': self.experiment_name,
            'class_id': self.class_id,
            'description': self.description,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# 实验附件模型
class ExperimentAttachment(db.Model):
    __tablename__ = 'experiment_attachments'
    
    attachment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.experiment_id'))
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attachment {self.file_name}>'
        
    def to_dict(self):
        return {
            'attachment_id': self.attachment_id,
            'experiment_id': self.experiment_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# 初始化数据库接口
@app.route('/init-db', methods=['GET'])
def init_db():
    try:
        with app.app_context():
            db.create_all()
        return jsonify({
            'code': 200,
            'message': '数据库初始化成功'
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'数据库初始化失败: {str(e)}'
        }), 500

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
            password=data['password'],
            user_type=data['user_type'],
            real_name=data['realname'],
            email=data['email'],
            profile_completed=False,
            student_id=None, 
            class_id=None 
        )
        
        # 保存到数据库
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '注册成功'
        })
        
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

# 获取实验要求
@app.route('/student/experiment/requirements', methods=['GET'])
def get_experiment_requirements():
    try:
        experiment_id = request.args.get('experiment_id')
        
        # 验证参数
        if not experiment_id:
            return jsonify({
                'code': 400,
                'message': '缺少experiment_id参数'
            }), 400
            
        # 查询实验
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
            
        # 查询附件
        attachments = ExperimentAttachment.query.filter_by(experiment_id=experiment_id).all()
        attachments_data = [attachment.to_dict() for attachment in attachments]
            
        # 返回数据
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': {
                'experiment': experiment.to_dict(),
                'attachments': attachments_data
            }
        })
        
    except Exception as e:
        print(f"获取实验要求错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

# 发布实验要求
@app.route('/teacher/experiment/publish', methods=['POST'])
def publish_experiment():
    try:
        data = request.get_json()
        
        # 验证必需字段
        required_fields = ['experiment_name', 'class_id', 'description', 'deadline']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'code': 400,
                    'message': f'缺少必需字段: {field}'
                }), 400
                
        # 创建实验
        new_experiment = Experiment(
            experiment_name=data['experiment_name'],
            class_id=data['class_id'],
            description=data['description'],
            deadline=datetime.fromisoformat(data['deadline'].replace(' ', 'T'))
        )
        
        db.session.add(new_experiment)
        db.session.flush()  # 获取新实验ID
        
        # 处理附件
        attachments_data = []
        if 'attachments' in data and data['attachments']:
            for attachment in data['attachments']:
                if 'file_name' not in attachment or 'file_content' not in attachment:
                    continue
                    
                # 保存文件（这里简化处理，实际应该保存到文件系统）
                file_name = attachment['file_name']
                file_path = f"uploads/experiments/{new_experiment.experiment_id}/{file_name}"
                
                # 确保目录存在
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # 解码base64并保存
                file_content = base64.b64decode(attachment['file_content'])
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                
                # 创建附件记录
                new_attachment = ExperimentAttachment(
                    experiment_id=new_experiment.experiment_id,
                    file_name=file_name,
                    file_path=file_path
                )
                
                db.session.add(new_attachment)
                attachments_data.append(new_attachment.to_dict())
        
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '实验发布成功',
            'data': {
                'experiment': new_experiment.to_dict(),
                'attachments': attachments_data
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"发布实验错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

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

def init_database():
    """初始化数据库"""
    try:
        with app.app_context():
            db.create_all()
            print("数据库表创建成功！")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        sys.exit(1)

def run_app():
    """启动应用"""
    # 初始化数据库
    init_database()
    
    # 启动应用
    print("启动Flask应用...")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )

if __name__ == '__main__':
    run_app() 
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timezone
import os
import pymysql
import sys
import base64
from enum import Enum
import shutil
import zipfile
import re
import traceback
try:
    from pyunpack import Archive
except ImportError:
    print("警告：pyunpack未安装，解压rar/7z功能将不可用")
try:
    import pandas as pd
except ImportError:
    print("警告：pandas未安装，模型评测功能将不可用")
from contextlib import redirect_stdout, redirect_stderr
import io

# 创建Flask应用
app = Flask(__name__)

# 配置CORS
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})

# 简单的CORS支持
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/dlplatform'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['UPLOAD_FOLDER'] = 'uploads'

# 文件上传配置
ALLOWED_EXTENSIONS = {'zip','rar','7z'}

# 初始化扩展
pymysql.install_as_MySQLdb()
db = SQLAlchemy(app)

# 数据库直接连接函数
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        db='dlplatform',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 用户类型枚举
class UserType(Enum):
    STUDENT = 'student'
    TEACHER = 'teacher'

# 用户模型
class User(db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    user_type = db.Column(db.Enum(UserType, values_callable=lambda x: [e.value for e in UserType]), nullable=False)
    real_name = db.Column(db.String(50))
    student_id = db.Column(db.String(20))
    profile_completed = db.Column(db.Boolean, default=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'))
    email = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)

    # 关系
    submissions = db.relationship('Submission', backref='student', lazy=True)
    # 作为学生的成绩
    grades_as_student = db.relationship('Grade', backref='student', lazy=True, 
                                       foreign_keys='Grade.student_id')
    # 作为教师的评分
    grades_as_teacher = db.relationship('Grade', backref='teacher', lazy=True, 
                                       foreign_keys='Grade.graded_by')
    student_classes = db.relationship('StudentClass', backref='student', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'user_type': self.user_type.value if isinstance(self.user_type, UserType) else self.user_type,
            'real_name': self.real_name,
            'student_id': self.student_id,
            'profile_completed': self.profile_completed,
            'class_id': self.class_id,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# 班级模型
class Class(db.Model):
    __tablename__ = 'classes'
    
    class_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # 允许为空以兼容旧数据
    
    # 关系
    students = db.relationship('User', backref='class_info', lazy=True, 
                              foreign_keys='User.class_id')
    experiments = db.relationship('Experiment', backref='class_info', lazy=True)
    student_classes = db.relationship('StudentClass', backref='class_info', lazy=True)
    
    def __repr__(self):
        return f'<Class {self.class_name}>'

# 学生-班级关联表
class StudentClass(db.Model):
    __tablename__ = 'student_classes'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'), nullable=False)

# 实验模型
class Experiment(db.Model):
    __tablename__ = 'experiments'
    
    experiment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # 允许为空以兼容旧数据
    description = db.Column(db.Text, nullable=False)
    publish_time = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    deadline = db.Column(db.TIMESTAMP)
    
    # 关系
    attachments = db.relationship('ExperimentAttachment', backref='experiment', lazy=True)
    submissions = db.relationship('Submission', backref='experiment', lazy=True)
    grades = db.relationship('Grade', backref='experiment', lazy=True)
    
    def __repr__(self):
        return f'<Experiment {self.experiment_name}>'
        
    def to_dict(self):
        return {
            'experiment_id': self.experiment_id,
            'experiment_name': self.experiment_name,
            'class_id': self.class_id,
            'teacher_id': self.teacher_id,
            'description': self.description,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'publish_time': self.publish_time.isoformat() if self.publish_time else None
        }

# 实验附件模型
class ExperimentAttachment(db.Model):
    __tablename__ = 'experiment_attachments'
    
    attachment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.experiment_id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)  # 允许为空以兼容旧数据
    upload_time = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attachment {self.file_name}>'
        
    def to_dict(self):
        return {
            'attachment_id': self.attachment_id,
            'experiment_id': self.experiment_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None
        }

# 学生提交记录模型
class Submission(db.Model):
    __tablename__ = 'submissions'
    
    submission_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.experiment_id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    submit_time = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    
    # 关系
    grade = db.relationship('Grade', backref='submission', uselist=False, lazy=True)
    
    def to_dict(self):
        return {
            'submission_id': self.submission_id,
            'experiment_id': self.experiment_id,
            'student_id': self.student_id,
            'submit_time': self.submit_time.isoformat() if self.submit_time else None,
            'file_name': self.file_name,
            'file_path': self.file_path
        }

# 成绩模型
class Grade(db.Model):
    __tablename__ = 'grades'
    
    grade_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.submission_id'), nullable=False, unique=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.experiment_id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    score = db.Column(db.Numeric(5, 2), nullable=False)
    graded_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    graded_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'grade_id': self.grade_id,
            'submission_id': self.submission_id,
            'experiment_id': self.experiment_id,
            'student_id': self.student_id,
            'score': float(self.score),
            'graded_by': self.graded_by,
            'graded_at': self.graded_at.isoformat() if self.graded_at else None
        }

# 辅助函数
def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def insert_experiment_attachment(experiment_id, file_name, file_path, file_size):
    """插入实验附件记录"""
    try:
        attachment = ExperimentAttachment()
        attachment.experiment_id = int(experiment_id)
        attachment.file_name = str(file_name)
        attachment.file_path = str(file_path)
        attachment.file_size = int(file_size) if file_size else 0
        db.session.add(attachment)
        db.session.commit()
        return True
    except Exception as e:
        print(f"插入实验附件记录错误: {e}")
        db.session.rollback()
        return False

def insert_submission(experiment_id, student_id, file_name, file_path):
    """插入学生提交记录"""
    try:
        submission = Submission()
        submission.experiment_id = int(experiment_id)
        submission.student_id = int(student_id)
        submission.file_name = str(file_name)
        submission.file_path = str(file_path)
        db.session.add(submission)
        db.session.commit()
        return True
    except Exception as e:
        print(f"插入学生提交记录错误: {e}")
        db.session.rollback()
        return False

def execute_student_code(student_code_path):
    """
    执行学生提交的Python文件，生成测试CSV，与真实标签比对计算准确度
    """
    try:
        # 获取Flask应用的根目录（DLplatform-be的上级目录）
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 构建绝对路径
        absolute_student_code_path = os.path.join(app_root, student_code_path)
        
        # 检查文件是否存在
        if not os.path.exists(absolute_student_code_path):
            return {
                "score": 0.0,
                "message": f"学生代码文件不存在: {absolute_student_code_path}"
            }
        
        # 获取学生代码所在目录
        student_dir = os.path.dirname(absolute_student_code_path)
        
        # 切换到学生代码目录
        original_cwd = os.getcwd()
        os.chdir(student_dir)
        
        # 捕获输出
        output = io.StringIO()
        error_output = io.StringIO()
        
        try:
            with redirect_stdout(output), redirect_stderr(error_output):
                # 直接执行学生代码文件，模拟__main__环境
                with open(absolute_student_code_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                
                # 创建一个新的命名空间来执行代码，模拟__main__环境
                namespace = {'__name__': '__main__'}
                exec(code, namespace)
                
                # 检查是否生成了预测结果文件
                if not os.path.exists('all_preds.csv'):
                    # 如果没有生成文件，尝试直接调用evaluate_model函数
                    if 'evaluate_model' in namespace and callable(namespace['evaluate_model']):
                        print("找到evaluate_model函数，正在调用...")
                        namespace['evaluate_model']()
                    else:
                        return {"score": 0.0, "message": "学生代码中未找到evaluate_model函数且未生成预测结果"}
                
                # 检查是否生成了预测结果文件
                preds_file = 'all_preds.csv'
                if os.path.exists(preds_file):
                    # 读取学生生成的预测结果
                    preds_df = pd.read_csv(preds_file)
                    predictions = preds_df.iloc[:, 0].tolist()
                    
                    # 读取真实标签文件
                    labels_file = '../../testdata/all_labels.csv'
                    if os.path.exists(labels_file):
                        labels_df = pd.read_csv(labels_file)
                        true_labels = labels_df.iloc[:, 0].tolist()
                        print('预测值：',predictions)
                        print('真实值：',true_labels)
                        # 计算准确率
                        if len(predictions) == len(true_labels):
                            correct = sum(1 for pred, true in zip(predictions, true_labels) if pred == true)
                            total = len(true_labels)
                            accuracy = (correct / total) * 100
                            
                            return {
                                "score": round(accuracy, 2),
                                "message": f"评测成功，准确率: {accuracy:.2f}%",
                                "correct": correct,
                                "total": total,
                                "predictions_count": len(predictions),
                                "labels_count": len(true_labels)
                            }
                        else:
                            return {
                                "score": 0.0, 
                                "message": f"预测结果数量({len(predictions)})与真实标签数量({len(true_labels)})不匹配"
                            }
                    else:
                        return {"score": 0.0, "message": f"真实标签文件不存在: {labels_file}"}
                else:
                    return {"score": 0.0, "message": f"预测结果文件未生成: {preds_file}"}
                    
        except Exception as e:
            error_msg = error_output.getvalue()
            return {
                "score": 0.0, 
                "message": f"执行学生代码时发生错误: {str(e)}",
                "error_output": error_msg
            }
        finally:
            # 恢复原始工作目录
            os.chdir(original_cwd)
            
    except Exception as e:
        print(f"执行学生代码时发生错误: {e}")
        return {"score": 0.0, "message": f"执行学生代码失败: {str(e)}"}

def insert_grade(submission_id, experiment_id, student_id, score, graded_by):
    """插入成绩记录"""
    try:
        # 检查是否已存在成绩记录
        existing_grade = Grade.query.filter_by(submission_id=submission_id).first()
        
        if existing_grade:
            # 更新现有成绩
            existing_grade.score = score
            existing_grade.graded_by = graded_by
            existing_grade.graded_at = datetime.utcnow()
        else:
            # 插入新成绩
            grade = Grade()
            grade.submission_id = submission_id
            grade.experiment_id = experiment_id
            grade.student_id = student_id
            grade.score = score
            grade.graded_by = graded_by
            db.session.add(grade)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"插入成绩记录错误: {e}")
        db.session.rollback()
        return False

# 邮箱验证函数（从修改个人资料分支引入）
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
    if existing_user and existing_user.user_id != current_user_id:
        return existing_user.email
    return None

def check_student_id_conflict(student_id, current_user_id):
    """检查学号是否已被其他用户使用"""
    existing_user = User.query.filter_by(student_id=student_id).first()
    if existing_user and existing_user.user_id != current_user_id:
        return existing_user.student_id
    return None

# 路由
# 修改个人资料接口
@app.route('/profile/update', methods=['POST'])
def update_profile():
    """
    更新用户个人资料
    """
    try:
        # 获取当前用户
        current_user = get_current_user()
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
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type == 'teacher':
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
            conflict_email = check_email_conflict(email, current_user.user_id)
            if conflict_email:
                return jsonify({
                    'code': 409,
                    'message': '邮箱已被使用',
                    'conflict_email': conflict_email
                }), 409

        # 学号冲突校验（仅学生）
        if student_id and user_type == 'student':
            conflict_student_id = check_student_id_conflict(student_id, current_user.user_id)
            if conflict_student_id:
                return jsonify({
                    'code': 409,
                    'message': '学号已被使用',
                    'conflict_student_id': conflict_student_id
                }), 409

        # 班级存在性校验（仅学生，且有class_id时）
        if class_id and user_type == 'student':
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
        if student_id is not None and user_type == 'student':
            current_user.student_id = student_id
        if class_id is not None and user_type == 'student':
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
    return 'Hello, Flask! 个人资料修改接口已就绪，后端服务已启动'

# 初始化数据库接口
@app.route('/init-db', methods=['GET'])
def init_db():
    """初始化数据库表"""
    try:
        with app.app_context():
            db.create_all()
        
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
                user_type=UserType.STUDENT,
                password='123456'
            )
            user2 = User(
                username='teacher1',
                real_name='李老师',
                email='teacher@example.com',
                user_type=UserType.TEACHER,
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
            teacher = User.query.filter_by(user_type=UserType.TEACHER).first()
            if teacher:
                class1 = Class(class_name='计算机科学1班', teacher_id=teacher.user_id)
                class2 = Class(class_name='计算机科学2班', teacher_id=teacher.user_id)
                db.session.add(class1)
                db.session.add(class2)
                db.session.commit()
                print("班级数据创建成功")
                
                # 更新学生用户的班级ID
                student = User.query.filter_by(user_type=UserType.STUDENT).first()
                if student:
                    student.class_id = class1.class_id
                    db.session.commit()
                    print("学生班级关联成功")
        
        return jsonify({
            'code': 200,
            'message': '数据库初始化成功'
        }), 200
        
    except Exception as e:
        print("数据库初始化异常：", e)
        traceback.print_exc()
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
            user_type=UserType.STUDENT if data['user_type'] == 'student' else UserType.TEACHER,
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
        user_type = user.user_type.value if isinstance(user.user_type, UserType) else user.user_type
        if user_type == 'student':
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
        elif user_type == 'teacher':
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

# 学生端获取成绩信息
@app.route('/student/experiment/scores', methods=['POST'])
def student_experiment_scores():
    data = request.get_json()
    experiment_id = data.get('experiment_id')
    if not experiment_id:
        return jsonify({"code": 400, "message": "experiment_id is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 无论是否传入student_id，都返回该实验的所有学生成绩
    sql = """
        SELECT 
            u.user_id AS id,
            u.real_name AS name,
            c.class_name AS className,
            g.score
        FROM grades g
        JOIN users u ON g.student_id = u.user_id
        JOIN classes c ON u.class_id = c.class_id
        WHERE g.experiment_id = %s
        ORDER BY g.score DESC
    """
    cursor.execute(sql, (experiment_id,))
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({"code": 200, "message": "查询成功", "data": students})

# 教师端获取成绩信息
@app.route('/teacher/experiment/scores', methods=['POST'])
def teacher_experiment_scores():
    data = request.get_json()
    experiment_id = data.get('experiment_id')
    if not experiment_id:
        return jsonify({"code": 400, "message": "experiment_id is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    # 查询实验名称
    cursor.execute("SELECT experiment_name FROM experiments WHERE experiment_id = %s", (experiment_id,))
    exp_row = cursor.fetchone()
    experiment_name = exp_row['experiment_name'] if exp_row else ""

    # 查询学生成绩列表
    sql = """
        SELECT 
            u.user_id AS id,
            u.real_name AS name,
            c.class_name AS className,
            g.score
        FROM grades g
        JOIN users u ON g.student_id = u.user_id
        JOIN classes c ON u.class_id = c.class_id
        WHERE g.experiment_id = %s
        ORDER BY g.score DESC
    """
    cursor.execute(sql, (experiment_id,))
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({
        "code": 200,
        "message": "查询成功",
        "data": {
            "experiment_name": experiment_name,
            "students": students
        }
    })

# 发布实验要求
@app.route('/teacher/experiment/publish', methods=['POST'])
def publish_experiment():
    try:
        data = request.get_json()
        
        # 验证必需字段
        required_fields = ['experiment_name', 'class_id', 'description', 'deadline', 'teacher_id']
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
            teacher_id=data['teacher_id'],
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
                
                # 获取文件大小（KB）
                file_size = os.path.getsize(file_path) // 1024
                
                # 创建附件记录
                new_attachment = ExperimentAttachment(
                    experiment_id=new_experiment.experiment_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_size=file_size
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

# 学生提交实验作业
@app.route('/api/experiments/upload', methods=['POST'])
def submit():
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({
                'code': 400,
                'message': '没有上传文件'
            }), 400
        
        file = request.files['file']
        
        # 检查文件名是否为空
        if file.filename == '':
            return jsonify({
                'code': 400,
                'message': '没有选择文件'
            }), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            return jsonify({
                'code': 400,
                'message': '不支持的文件类型，只支持.zip/.rar/.7z文件'
            }), 400
        
        # 获取请求参数（支持两种参数名格式）
        experiment_id = request.form.get('experimentId')
        student_id = request.form.get('studentId')
        
        # 验证参数
        if not experiment_id or not student_id:
            return jsonify({
                'code': 400,
                'message': '缺少必要参数：experiment_id 或 student_id'
            }), 400
        
        # 验证实验和学生是否存在
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            return jsonify({
                'code': 400,
                'message': '实验不存在'
            }), 400
        
        student = User.query.get(student_id)
        if not student:
            return jsonify({
                'code': 400,
                'message': '学生不存在'
            }), 400
        
        # 验证学生是否为student类型
        user_type = student.user_type.value if isinstance(student.user_type, UserType) else student.user_type
        if user_type != 'student':
            return jsonify({
                'code': 400,
                'message': '只有学生可以提交作业'
            }), 400
        
        # 验证学生是否已提交过该实验
        existing_submission = Submission.query.filter_by(
            experiment_id=experiment_id, 
            student_id=student_id
        ).first()
        
        # 检查是否超过截止时间
        if experiment.deadline and datetime.utcnow() > experiment.deadline:
            return jsonify({
                'code': 400,
                'message': '实验已超过截止时间，无法提交'
            }), 400
            
        experiment_folder = os.path.join('lab'+str(experiment_id),'testcode')
        file_path = os.path.join(experiment_folder, str(file.filename))
        new_file_name = str(file.filename).split('.')[0]
        new_file_path = os.path.join(experiment_folder, new_file_name)
        
        if not os.path.exists(experiment_folder):
            os.makedirs(experiment_folder)
            
        if existing_submission:
            # 如果数据库中记录的旧文件存在，则删除旧文件，实现覆盖上传
            existing_experiment_attachment = ExperimentAttachment.query.filter_by(
                file_name=existing_submission.file_name,
                file_path=existing_submission.file_path
            ).first()
            old_file_path = existing_submission.file_path
            if old_file_path and os.path.exists(old_file_path):
                if os.path.isfile(old_file_path):
                    os.remove(old_file_path)
                elif os.path.isdir(old_file_path):
                    shutil.rmtree(old_file_path)
            # 保存文件
            file.save(file_path)
            # 获取文件大小（KB）
            file_size = os.path.getsize(file_path) // 1024
            # 覆盖数据库中的旧记录
            existing_submission.file_name = new_file_name
            existing_submission.file_path = new_file_path
            existing_submission.submit_time = datetime.utcnow()
            print(existing_experiment_attachment)
            if existing_experiment_attachment:
                existing_experiment_attachment.file_name = new_file_name
                existing_experiment_attachment.file_path = new_file_path
                existing_experiment_attachment.file_size = file_size
            db.session.commit()
        else:
            file.save(file_path)
            # 获取文件大小（KB）
            file_size = os.path.getsize(file_path) // 1024
            # 插入实验附件记录
            if not insert_experiment_attachment(experiment_id, new_file_name, new_file_path, file_size):
                # 删除已保存的文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({
                    'code': 500,
                    'message': '保存实验附件记录失败'
                }), 500
            # 插入学生提交记录
            if not insert_submission(experiment_id, student_id, new_file_name, new_file_path):
                # 删除已保存的文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({
                    'code': 500,
                    'message': '保存学生提交记录失败'
                }), 500
        
        # 解压文件
        if str(file.filename).lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(experiment_folder)
                print(file_path)
                os.remove(file_path)
            except Exception as e:
                # 解压失败，删除已保存的文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({
                    'code': 500,
                    'message': f'解压zip文件失败: {e}'
                }), 500
        elif str(file.filename).lower().endswith('.rar') or str(file.filename).lower().endswith('.7z'):
            try:
                Archive(file_path).extractall(experiment_folder)
                os.remove(file_path)
            except Exception as e:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({
                    'code': 500,
                    'message': f'解压压缩包失败: {e}'
                }), 500        
                
        return jsonify({
            'code': 200,
            'message': '提交成功'
        })
        
    except Exception as e:
        print(f"提交过程中发生错误: {e}")
        return jsonify({
            'code': 500,
            'message': '服务器内部错误'
        }), 500

# 获取实验提交记录
@app.route('/api/experiments/<int:experiment_id>/uploads', methods=['GET'])
def get_experiment_uploads(experiment_id):
    """
    获取实验的上传历史
    """
    try:
        # 获取该实验的所有提交记录
        submissions = Submission.query.filter_by(experiment_id=experiment_id).all()
        print(submissions)
        upload_history = []
        for submission in submissions:
            upload_history.append({
                'id': submission.submission_id,
                'fileName': submission.file_name,
                'fileSize': os.path.getsize(submission.file_path) if os.path.exists(submission.file_path) else 0,
                'uploadTime': submission.submit_time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'success'
            })
        
        return jsonify({
            'success': True,
            'data': upload_history
        })
        
    except Exception as e:
        app.logger.error(f"获取上传历史时发生错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': '获取上传历史失败'
        })

@app.route('/test', methods=['GET'])
def test_models():
    """
    评测模块接口
    根据实验ID，查找所有提交的模型文件，进行评测并保存成绩
    """
    try:
        # 获取实验ID参数
        experiment_id = request.args.get('experimentId')
        
        if not experiment_id:
            return jsonify({
                'code': 400,
                'message': '缺少实验ID参数'
            }), 400
        
        # 验证实验是否存在
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            return jsonify({
                'code': 400,
                'message': '实验不存在'
            }), 400
        
        # 获取该实验的所有提交记录，按时间降序排列
        submissions = Submission.query.filter_by(
            experiment_id=experiment_id
        ).order_by(Submission.submit_time.desc()).all()
        
        if not submissions:
            return jsonify({
                'code': 400,
                'message': '该实验暂无提交记录'
            }), 400
        
        # 创建临时评测目录
        temp_eval_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_eval')
        if not os.path.exists(temp_eval_dir):
            os.makedirs(temp_eval_dir)
        
        evaluated_count = 0
        print(submissions)
        for submission in submissions:
            try:
                # 检查学生代码文件是否存在
                student_code_path = os.path.join(submission.file_path, f"{submission.file_name}.py")
                if not os.path.exists(student_code_path):
                    print(f"学生代码文件不存在: {student_code_path}")
                    continue
                
                # 执行学生代码进行评测
                result = execute_student_code(student_code_path)
                score = result["score"]
                
                # 保存成绩到数据库
                if insert_grade(submission.submission_id, experiment_id, submission.student_id, score, experiment.teacher_id):
                    evaluated_count += 1
                    print(f"学生 {submission.student_id} 的模型评测完成，得分: {score}, 消息: {result['message']}")
                else:
                    print(f"保存学生 {submission.student_id} 的成绩失败")
                    
            except Exception as e:
                print(f"评测学生 {submission.student_id} 的模型时发生错误: {e}")
                continue
        
        # 清理临时目录
        if os.path.exists(temp_eval_dir):
            shutil.rmtree(temp_eval_dir)
        
        return jsonify({
            'code': 200,
            'message': f'评测完成，共评测了 {evaluated_count} 个模型'
        })
        
    except Exception as e:
        print(f"评测过程中发生错误: {e}")
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
    print("访问地址: http://localhost:5000")
    print("个人资料修改接口: POST http://localhost:5000/profile/update")
    print("数据库初始化: http://localhost:5000/init-db")
    print("\n按 Ctrl+C 停止应用")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )

@app.route('/classes', methods=['POST'])
def create_class():
    data = request.get_json()
    class_name = data.get('class_name') if data else None
    teacher_id = data.get('teacher_id') if data else None
    # 参数校验
    if not class_name or not isinstance(class_name, str) or len(class_name) > 100:
        return jsonify({
            "code": 400,
            "message": "参数错误：班级名称不能为空/长度超出限制"
        }), 400
    if teacher_id is None:
        return jsonify({
            "code": 400,
            "message": "参数错误：教师ID不能为空"
        }), 400
    try:
        teacher_id = int(teacher_id)
    except (TypeError, ValueError):
        return jsonify({
            "code": 400,
            "message": "参数错误：教师ID必须为整数"
        }), 400
    try:
        # 使用主分支中的Class模型而不是ClassInfo
        new_class = Class(class_name=class_name, teacher_id=teacher_id)
        db.session.add(new_class)
        db.session.commit()
        return jsonify({
            "code": 200,
            "message": "班级创建成功",
            "data": {
                "class_id": new_class.class_id,
                "class_name": class_name,
                "teacher_id": teacher_id
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print("数据库写入异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，班级创建失败，请重试"
        }), 500

if __name__ == '__main__':
    run_app()

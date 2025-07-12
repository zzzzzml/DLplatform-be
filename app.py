from flask import Flask, request, jsonify, send_file
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
import numpy as np
import importlib.util
import random

# 创建Flask应用
app = Flask(__name__)

# 配置CORS
CORS(app, resources={
    r"/api/*": {"origins": "http://localhost:5173"},
    r"/download/*": {"origins": "http://localhost:5173"},
    r"/experiments/*": {"origins": "http://localhost:5173"},
    r"/student/*": {"origins": "http://localhost:5173"},
    r"/teacher/*": {"origins": "http://localhost:5173"},
    r"/classes/*": {"origins": "http://localhost:5173"},
    r"/profile/*": {"origins": "http://localhost:5173"},
    r"/users/*": {"origins": "http://localhost:5173"},
    r"/login": {"origins": "http://localhost:5173"},
    r"/register": {"origins": "http://localhost:5173"},
    r"/health": {"origins": "http://localhost:5173"},
    r"/init-db": {"origins": "http://localhost:5173"},
    r"/evaluations": {"origins": "http://localhost:5173"},
    r"/results": {"origins": "http://localhost:5173"},
    r"/test": {"origins": "http://localhost:5173"},
    r"/auth/*": {"origins": "http://localhost:5173"},
    r"/courses": {"origins": "http://localhost:5173"}
}, supports_credentials=True)

# 简单的CORS支持
@app.after_request
def after_request(response):
    # 不再添加Access-Control-Allow-Origin，因为已经由flask-cors处理
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,User-ID,User-Type')
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
            'class_id': self.class_id,
            'email': self.email,
            'profile_completed': self.profile_completed,
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
        absolute_student_code_path = os.path.abspath(student_code_path)
        print(f"评测文件绝对路径: {absolute_student_code_path}")
        
        # 检查文件是否存在
        if not os.path.exists(absolute_student_code_path):
            return {
                "score": 0.0,
                "message": f"学生代码文件不存在: {absolute_student_code_path}"
            }
        
        # 获取学生代码所在目录和模块名称
        student_dir = os.path.dirname(absolute_student_code_path)
        module_name = os.path.basename(absolute_student_code_path).replace('.py', '')
        print(f"模块名称: {module_name}, 目录: {student_dir}")
        
        # 切换到学生代码目录
        original_cwd = os.getcwd()
        os.chdir(student_dir)
        
        # 捕获输出
        output = io.StringIO()
        error_output = io.StringIO()
        
        try:
            with redirect_stdout(output), redirect_stderr(error_output):
                # 动态导入学生的模块
                print(f"正在导入学生模块: {module_name}")
                spec = importlib.util.spec_from_file_location(module_name, absolute_student_code_path)
                if not spec:
                    return {"score": 0.0, "message": f"无法加载模块规范: {module_name}"}
                
                student_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(student_module)
                
                print(f"模块导入成功，可用函数: {dir(student_module)}")
                
                # 首先尝试调用evaluate_model函数
                if hasattr(student_module, 'evaluate_model') and callable(getattr(student_module, 'evaluate_model')):
                    print("调用学生的evaluate_model函数...")
                    student_module.evaluate_model()
                # 如果没有evaluate_model函数，尝试调用其他可能的函数
                elif hasattr(student_module, 'test') and callable(getattr(student_module, 'test')):
                    print("调用学生的test函数...")
                    student_module.test()
                elif hasattr(student_module, 'predict') and callable(getattr(student_module, 'predict')):
                    print("调用学生的predict函数...")
                    student_module.predict()
                elif not any(hasattr(student_module, func) and callable(getattr(student_module, func)) 
                           for func in ['evaluate_model', 'test', 'predict']):
                    print("未找到可调用的函数，尝试直接运行模块...")
                    # 如果没有找到特定函数，模块导入时可能已经执行了主要代码
                
                # 检查是否生成了预测结果文件
                preds_file = 'all_preds.csv'
                if not os.path.exists(preds_file):
                        # 尝试在当前目录和上级目录查找all_preds.csv文件
                        found = False
                        for search_dir in ['.', '..', '../..']:
                            search_path = os.path.join(search_dir, 'all_preds.csv')
                            if os.path.exists(search_path):
                                print(f"在 {search_path} 找到预测结果文件")
                                shutil.copy(search_path, 'all_preds.csv')
                                found = True
                                break
                        
                        if not found:
                            print("未生成预测结果文件，评测失败")
                            return {"score": 0.0, "message": "学生代码中未找到evaluate_model函数且未生成预测结果"}
                
                # 检查是否生成了预测结果文件
                preds_file = 'all_preds.csv'
                if os.path.exists(preds_file):
                    # 读取学生生成的预测结果
                    preds_df = pd.read_csv(preds_file)
                    predictions = preds_df.iloc[:, 0].tolist()
                    print(f"读取到 {len(predictions)} 个预测结果")
                    
                    # 读取真实标签文件
                    # 首先尝试相对于学生代码目录的路径
                    labels_file = '../../testdata/all_labels.csv'
                    # 如果不存在，尝试相对于实验目录的路径
                    if not os.path.exists(labels_file):
                        # 从学生代码路径提取实验ID
                        # 假设路径格式为 .../DLplatform-be/lab{experiment_id}/testcode/student_{student_id}_{timestamp}/...
                        path_parts = absolute_student_code_path.split(os.sep)
                        lab_index = -1
                        for i, part in enumerate(path_parts):
                            if part.startswith('lab'):
                                lab_index = i
                                break
                        
                        if lab_index >= 0:
                            lab_dir = os.path.join(*path_parts[:lab_index+1])
                            labels_file = os.path.join(lab_dir, 'testdata', 'all_labels.csv')
                    
                    if os.path.exists(labels_file):
                        labels_df = pd.read_csv(labels_file)
                        true_labels = labels_df.iloc[:, 0].tolist()
                        print(f"读取到 {len(true_labels)} 个真实标签")
                        
                        # 计算准确率
                        if len(predictions) == len(true_labels):
                            correct = sum(1 for pred, true in zip(predictions, true_labels) if pred == true)
                            total = len(true_labels)
                            accuracy = (correct / total) * 100
                            
                            print(f"评测结果: 总数 {total}, 正确 {correct}, 准确率 {accuracy:.2f}%")
                            
                            return {
                                "score": round(accuracy, 2),
                                "message": f"评测成功，准确率: {accuracy:.2f}%",
                                "correct": correct,
                                "total": total,
                                "predictions_count": len(predictions),
                                "labels_count": len(true_labels),
                                "stdout": output.getvalue(),
                                "stderr": error_output.getvalue()
                            }
                        else:
                            print(f"预测结果数量({len(predictions)})与真实标签数量({len(true_labels)})不匹配")
                            return {
                                "score": 0.0, 
                                "message": f"预测结果数量({len(predictions)})与真实标签数量({len(true_labels)})不匹配",
                                "predictions_count": len(predictions),
                                "labels_count": len(true_labels),
                                "stdout": output.getvalue(),
                                "stderr": error_output.getvalue()
                            }
                    else:
                        print(f"真实标签文件不存在: {labels_file}")
                        return {"score": 0.0, "message": f"真实标签文件不存在: {labels_file}"}
                else:
                    print(f"预测结果文件未生成: {preds_file}")
                    return {"score": 0.0, "message": f"预测结果文件未生成: {preds_file}"}
                    
        except Exception as e:
            error_msg = error_output.getvalue()
            print(f"执行错误: {str(e)}")
            print(f"错误输出: {error_msg}")
            return {
                "score": 0.0, 
                "message": f"执行学生代码时发生错误: {str(e)}",
                "error_output": error_msg,
                "stdout": output.getvalue()
            }
        finally:
            # 恢复原始工作目录
            os.chdir(original_cwd)
            
    except Exception as e:
        print(f"执行学生代码时发生错误: {e}")
        traceback.print_exc()
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
    """获取当前登录用户"""
    # 从请求头中获取用户信息
    auth_header = request.headers.get('Authorization')
    user_id_header = request.headers.get('User-ID')
    user_type_header = request.headers.get('User-Type')
    user_id = None
    
    # 先尝试从User-ID头获取（优先级最高，兼容旧版本）
    if user_id_header:
        try:
            user_id = int(user_id_header)
            print(f"从User-ID头获取到用户ID: {user_id}")
        except:
            print("User-ID头解析失败")
    
    # 如果没有从User-ID获取到，尝试从Authorization头解析用户ID
    if not user_id and auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            # 尝试从token中提取user_id（简化处理）
            if token.startswith('api_token_'):
                # 从当前登录的Cookie获取user_id（如果有的话）
                cookie_user_id = request.cookies.get('user_id')
                if cookie_user_id:
                    user_id = int(cookie_user_id)
                    print(f"从Cookie获取到用户ID: {user_id}")
            elif token.startswith('mock_token_'):
                # 处理前端模拟用户的情况
                if 'student' in token:
                    student = User.query.filter_by(user_type=UserType.STUDENT).first()
                    if student:
                        print(f"使用模拟学生账号: {student.user_id}")
                        return student
                elif 'teacher' in token:
                    teacher = User.query.filter_by(user_type=UserType.TEACHER).first()
                    if teacher:
                        print(f"使用模拟教师账号: {teacher.user_id}")
                        return teacher
        except Exception as e:
            print(f"解析Authorization头失败: {e}")
    
    # 如果找到了user_id，查询对应用户
    if user_id:
        user = User.query.get(user_id)
        if user:
            print(f"找到用户: {user.user_id}, {user.username}")
            
            # 如果请求头中包含用户类型，且与数据库中的不一致，尝试更新用户类型
            if user_type_header and user_type_header in ['student', 'teacher']:
                current_type = user.user_type.value if isinstance(user.user_type, UserType) else user.user_type
                if current_type != user_type_header:
                    print(f"用户类型不匹配，请求头: {user_type_header}, 数据库: {current_type}")
                    # 这里不直接修改数据库，而是临时调整返回的用户类型
                    if user_type_header == 'teacher':
                        # 如果请求头指定为教师，尝试查找教师账号
                        teacher = User.query.filter_by(user_type=UserType.TEACHER).first()
                        if teacher:
                            print(f"切换到教师账号: {teacher.user_id}, {teacher.username}")
                            return teacher
            
            return user
        else:
            print(f"找不到ID为{user_id}的用户")
    
    print("无法确定当前用户，尝试返回默认用户")
    # 如果无法确定用户，尝试返回第一个用户（仅用于测试）
    # 注意：实际生产环境应当返回None或抛出未授权错误
    first_user = User.query.first()
    if first_user:
        print(f"使用默认用户: {first_user.user_id}, {first_user.username}")
        return first_user
    
    print("找不到任何用户")
    return None

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
@app.route('/profile/update', methods=['POST', 'OPTIONS'])
def update_profile():
    """
    更新用户个人资料
    """
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
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

        # 学号冲突校验（仅对学生）
        if student_id and user_type == 'student':
            conflict_student_id = check_student_id_conflict(student_id, current_user.user_id)
            if conflict_student_id:
                return jsonify({
                    'code': 409,
                    'message': '学号已被使用',
                    'conflict_student_id': conflict_student_id
                }), 409

        # 班级存在性校验（仅对学生）
        if class_id and user_type == 'student':
            try:
                class_id = int(class_id)
                class_obj = Class.query.get(class_id)
                if not class_obj:
                    return jsonify({
                        'code': 404,
                        'message': '班级不存在'
                    }), 404
            except (TypeError, ValueError):
                return jsonify({
                    'code': 400,
                    'message': '参数错误：班级ID必须为整数'
                }), 400

        # 更新用户信息
        if real_name is not None:
            current_user.real_name = real_name
        if email is not None:
            current_user.email = email
        if student_id is not None and user_type == 'student':
            current_user.student_id = student_id
        if class_id is not None and user_type == 'student':
            current_user.class_id = class_id

        # 检查资料是否已完善
        profile_status_changed = False
        if not current_user.profile_completed:
            # 对于学生，检查是否已填写姓名、邮箱、学号和班级
            if user_type == 'student':
                if (current_user.real_name and current_user.email and
                        current_user.student_id and current_user.class_id):
                    current_user.profile_completed = True
                    profile_status_changed = True
            # 对于教师，检查是否已填写姓名和邮箱
            elif user_type == 'teacher':
                if current_user.real_name and current_user.email:
                    current_user.profile_completed = True
                    profile_status_changed = True

        # 保存更改
        db.session.commit()

        # 返回结果
        return jsonify({
            'code': 200,
            'message': '个人资料更新成功',
            'data': {
                'profile_completed': current_user.profile_completed,
                'profile_status_changed': profile_status_changed
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        print("更新个人资料异常：", e)
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '服务器内部错误，更新个人资料失败'
        }), 500

# 处理所有路径的OPTIONS请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    response = app.make_default_options_response()
    return response

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
@app.route('/auth/user-info', methods=['GET', 'OPTIONS'])
def get_user_info():
    """
    获取当前登录用户信息
    """
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        # 获取当前用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401

        # 构建用户信息
        user_info = {
            'user_id': current_user.user_id,
            'username': current_user.username,
            'user_type': current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type,
            'real_name': current_user.real_name,
            'email': current_user.email,
            'profile_completed': current_user.profile_completed,
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None
        }

        # 如果是学生，添加学生特有字段
        if user_info['user_type'] == 'student':
            user_info['student_id'] = current_user.student_id
            user_info['class_id'] = current_user.class_id

        return jsonify({
            'code': 200,
            'message': '获取用户信息成功',
            'data': user_info
        }), 200

    except Exception as e:
        print("获取用户信息异常：", e)
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '服务器内部错误，获取用户信息失败'
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
                    'student_id': user.student_id,
                    'class_id': user.class_id,
                    'profile_completed': user.profile_completed,
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
                    'profile_completed': True,  # 教师默认不需要强制完善资料
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
@app.route('/student/experiment/requirements', methods=['GET', 'OPTIONS'])
def get_experiment_requirements():
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        print("获取实验要求请求")
        experiment_id = request.args.get('experiment_id')
        print(f"请求参数: experiment_id={experiment_id}")
        
        # 验证参数
        if not experiment_id:
            print("缺少experiment_id参数")
            return jsonify({
                'code': 400,
                'message': '缺少experiment_id参数'
            }), 400
        
        # 尝试将experiment_id转换为整数
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            print(f"experiment_id不是有效的整数: {experiment_id}")
            return jsonify({
                'code': 400,
                'message': 'experiment_id必须是整数'
            }), 400
            
        # 查询实验
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            print(f"实验不存在: {experiment_id}")
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
            
        print(f"找到实验: {experiment.experiment_name}")
            
        # 查询附件
        attachments = ExperimentAttachment.query.filter_by(experiment_id=experiment_id).all()
        print(f"找到附件数量: {len(attachments)}")
        attachments_data = [attachment.to_dict() for attachment in attachments]
            
        # 返回数据
        response_data = {
            'code': 200,
            'message': '获取成功',
            'data': {
                'experiment': experiment.to_dict(),
                'attachments': attachments_data
            }
        }
        
        print(f"返回数据: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500

# 教师获取实验详情
@app.route('/teacher/experiment/detail', methods=['GET', 'OPTIONS'])
def get_teacher_experiment_detail():
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        print("教师获取实验详情请求")
        experiment_id = request.args.get('experiment_id')
        print(f"请求参数: experiment_id={experiment_id}")
        
        # 验证参数
        if not experiment_id:
            print("缺少experiment_id参数")
            return jsonify({
                'code': 400,
                'message': '缺少experiment_id参数'
            }), 400
        
        # 尝试将experiment_id转换为整数
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            print(f"experiment_id不是有效的整数: {experiment_id}")
            return jsonify({
                'code': 400,
                'message': 'experiment_id必须是整数'
            }), 400
            
        # 获取当前登录用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未授权访问'
            }), 401
        
        # 确保是教师用户
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type != 'teacher':
            return jsonify({
                'code': 403,
                'message': '只有教师可以访问此资源'
            }), 403
            
        # 查询实验
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            print(f"实验不存在: {experiment_id}")
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
            
        print(f"找到实验: {experiment.experiment_name}")
            
        # 查询附件
        attachments = ExperimentAttachment.query.filter_by(experiment_id=experiment_id).all()
        print(f"找到附件数量: {len(attachments)}")
        attachments_data = [attachment.to_dict() for attachment in attachments]
            
        # 返回数据
        response_data = {
            'code': 200,
            'message': '获取成功',
            'data': {
                'experiment': experiment.to_dict(),
                'attachments': attachments_data
            }
        }
        
        print(f"返回数据: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
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
    
    # 查询实验名称
    cursor.execute("SELECT experiment_name FROM experiments WHERE experiment_id = %s", (experiment_id,))
    exp_row = cursor.fetchone()
    experiment_name = exp_row['experiment_name'] if exp_row else "实验排名"
    
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
    
    # 计算统计数据
    avg_score = 0
    max_score = 0
    min_score = 100  # 假设分数最高为100
    
    if students:
        # 计算平均分
        total_score = sum(float(student['score']) for student in students)
        avg_score = total_score / len(students)
        
        # 计算最高分和最低分
        scores = [float(student['score']) for student in students]
        max_score = max(scores)
        min_score = min(scores)
    
    cursor.close()
    conn.close()
    
    # 返回与教师端一致的数据格式
    return jsonify({
        "code": 200, 
        "message": "查询成功", 
        "data": {
            "experiment_name": experiment_name,
            "students": students,
            "statistics": {
                "average_score": round(avg_score, 1),
                "max_score": max_score,
                "min_score": min_score,
                "student_count": len(students)
            }
        }
    })

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
    
    # 计算统计数据
    avg_score = 0
    max_score = 0
    min_score = 100  # 假设分数最高为100
    
    if students:
        # 计算平均分
        total_score = sum(float(student['score']) for student in students)
        avg_score = total_score / len(students)
        
        # 计算最高分和最低分
        scores = [float(student['score']) for student in students]
        max_score = max(scores)
        min_score = min(scores)
    
    cursor.close()
    conn.close()
    return jsonify({
        "code": 200,
        "message": "查询成功",
        "data": {
            "experiment_name": experiment_name,
            "students": students,
            "statistics": {
                "average_score": round(avg_score, 1),
                "max_score": max_score,
                "min_score": min_score,
                "student_count": len(students)
            }
        }
    })

# 下载提交文件
@app.route('/download/submission/<int:submission_id>', methods=['GET', 'OPTIONS'])
def download_submission(submission_id):
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        print(f"接收到下载请求，submission_id: {submission_id}")
        print(f"请求头: {dict(request.headers)}")
        
        # 查询提交记录
        submission = Submission.query.get(submission_id)
        if not submission:
            return jsonify({
                'code': 404,
                'message': '提交记录不存在'
            }), 404
        
        # 简化权限检查 - 移除用户认证要求
        # 在生产环境中，应该添加更严格的权限控制
        
        # 检查文件是否存在
        file_path = submission.file_path
        file_name = submission.file_name
        
        if not file_path or not file_name:
            return jsonify({
                'code': 404,
                'message': '文件信息不完整'
            }), 404
            
        print(f"尝试下载文件: {file_path}, 文件名: {file_name}")
        
        # 如果file_path不存在，尝试查找替代路径
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            print(f"当前工作目录: {os.getcwd()}")
            
            # 获取当前工作目录和后端目录
            current_dir = os.getcwd()
            backend_dir = os.path.join(current_dir, "DLplatform-be")
            
            # 尝试不同的文件路径
            experiment_id = submission.experiment_id
            possible_paths = [
                os.path.join(backend_dir, f"lab{experiment_id}", "testcode", file_name),
                os.path.join(current_dir, f"lab{experiment_id}", "testcode", file_name),
                os.path.join(f"lab{experiment_id}", "testcode", file_name),
                # 尝试查找学生ID命名的目录
                os.path.join(backend_dir, f"lab{experiment_id}", "testcode", str(submission.student_id)),
                os.path.join(current_dir, f"lab{experiment_id}", "testcode", str(submission.student_id)),
                os.path.join(f"lab{experiment_id}", "testcode", str(submission.student_id)),
            ]
            
            file_found = False
            for path in possible_paths:
                print(f"尝试替代路径: {path}")
                if os.path.exists(path):
                    print(f"找到文件在替代路径: {path}")
                    file_path = path
                    file_found = True
                    break
                    
            if not file_found:
                return jsonify({
                    'code': 404,
                    'message': f'文件不存在，file_path: {file_path}'
                }), 404
        
        # 如果file_path是目录，则压缩整个目录
        if os.path.isdir(file_path):
            # 创建临时ZIP文件
            temp_zip_path = os.path.join(os.getcwd(), f"temp_{submission_id}_{file_name}.zip")
            
            # 压缩目录
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_full_path = os.path.join(root, file)
                        # 计算相对路径，以便在ZIP文件中保持目录结构
                        rel_path = os.path.relpath(file_full_path, file_path)
                        zipf.write(file_full_path, rel_path)
            
            # 发送ZIP文件
            download_name = f"{file_name}.zip"
            try:
                response = send_file(
                    temp_zip_path,
                    as_attachment=True,
                    download_name=download_name,
                    mimetype='application/zip'
                )
                
                # 添加CORS头
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
                response.headers.add('Access-Control-Allow-Headers', '*')
                return response
            finally:
                # 发送完成后删除临时文件（在另一个线程中执行，以确保响应发送完成）
                def cleanup():
                    import time
                    time.sleep(5)  # 等待5秒，确保文件发送完成
                    if os.path.exists(temp_zip_path):
                        os.remove(temp_zip_path)
                
                import threading
                threading.Thread(target=cleanup).start()
        
        # 如果file_path是单个文件
        elif os.path.isfile(file_path):
            response = send_file(
                file_path,
                as_attachment=True,
                download_name=file_name,
                mimetype='application/octet-stream'
            )
            
            # 添加CORS头
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
            response.headers.add('Access-Control-Allow-Headers', '*')
            return response
        
        # 如果file_path既不是目录也不是文件
        else:
            return jsonify({
                'code': 404,
                'message': '文件不存在'
            }), 404
            
    except Exception as e:
        print(f"下载提交文件错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

# 更新实验
@app.route('/teacher/experiment/update', methods=['POST'])
def update_experiment():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            'code': 401,
            'message': '未登录或登录已过期'
        }), 401
    
    # 确保是教师用户
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            'code': 403,
            'message': '只有教师可以更新实验'
        }), 403
    
    # 获取请求数据
    data = request.get_json()
    if not data:
        return jsonify({
            'code': 400,
            'message': '请求数据为空'
        }), 400
    
    experiment_id = data.get('experiment_id')
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
    
    # 检查是否是实验的创建者
    if experiment.teacher_id != current_user.user_id:
        return jsonify({
            'code': 403,
            'message': '只有实验创建者可以更新实验'
        }), 403
    
    try:
        # 更新实验信息
        if 'experiment_name' in data and data['experiment_name']:
            experiment.experiment_name = data['experiment_name']
        
        if 'class_id' in data and data['class_id']:
            # 验证班级是否存在
            class_obj = Class.query.get(data['class_id'])
            if not class_obj:
                return jsonify({
                    'code': 404,
                    'message': f'班级不存在，class_id: {data["class_id"]}'
                }), 404
            experiment.class_id = data['class_id']
        
        if 'description' in data:
            experiment.description = data['description']
        
        if 'deadline' in data and data['deadline']:
            try:
                # 处理ISO格式日期字符串
                deadline = datetime.fromisoformat(data['deadline'].replace('Z', '+00:00'))
                experiment.deadline = deadline
            except ValueError:
                return jsonify({
                    'code': 400,
                    'message': '日期格式无效'
                }), 400
        
        # 保存更新
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '更新实验成功',
            'data': experiment.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"更新实验错误: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

# 删除实验
@app.route('/teacher/experiment/delete', methods=['POST'])
def delete_experiment():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            'code': 401,
            'message': '未登录或登录已过期'
        }), 401
    
    # 确保是教师用户
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            'code': 403,
            'message': '只有教师可以删除实验'
        }), 403
    
    # 获取请求数据
    data = request.get_json()
    if not data:
        return jsonify({
            'code': 400,
            'message': '请求数据为空'
        }), 400
    
    experiment_id = data.get('experiment_id')
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
    
    # 检查是否是实验的创建者
    if experiment.teacher_id != current_user.user_id:
        return jsonify({
            'code': 403,
            'message': '只有实验创建者可以删除实验'
        }), 403
    
    try:
        # 1. 删除实验相关的文件
        # 获取实验目录路径
        current_dir = os.getcwd()
        backend_dir = os.path.join(current_dir, "DLplatform-be")
        lab_folder = f"lab{experiment_id}"
        lab_path = os.path.join(backend_dir, lab_folder)
        
        # 记录操作
        print(f"准备删除实验 {experiment_id} 的文件: {lab_path}")
        
        # 如果目录存在，删除整个目录及其内容
        if os.path.exists(lab_path):
            try:
                shutil.rmtree(lab_path)
                print(f"成功删除实验目录: {lab_path}")
            except Exception as e:
                print(f"删除实验目录失败: {str(e)}")
                # 继续执行，即使文件删除失败，我们仍然可以删除数据库记录
        else:
            print(f"实验目录不存在: {lab_path}")
        
        # 2. 删除数据库中的相关记录
        # 2.1 删除实验附件
        attachments = ExperimentAttachment.query.filter_by(experiment_id=experiment_id).all()
        for attachment in attachments:
            db.session.delete(attachment)
        
        # 2.2 删除成绩记录
        grades = Grade.query.filter_by(experiment_id=experiment_id).all()
        for grade in grades:
            db.session.delete(grade)
        
        # 2.3 删除提交记录
        submissions = Submission.query.filter_by(experiment_id=experiment_id).all()
        for submission in submissions:
            db.session.delete(submission)
        
        # 2.4 最后删除实验本身
        db.session.delete(experiment)
        
        # 提交所有更改
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '实验删除成功，包括相关文件和数据'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"删除实验错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

# 发布实验要求
@app.route('/teacher/experiment/publish', methods=['POST'])
def publish_experiment():
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
            
        # 获取表单数据
        experiment_name = request.form.get('experiment_name')
        class_id = request.form.get('class_id')
        teacher_id = request.form.get('teacher_id')
        description = request.form.get('description')
        requirements = request.form.get('requirements')
        deadline = request.form.get('deadline')
        
        # 验证必需字段
        if not experiment_name or not class_id or not teacher_id or not description or not deadline:
            return jsonify({
                'code': 400,
                'message': '缺少必需字段'
            }), 400
            
        # 验证班级是否存在
        class_obj = Class.query.get(class_id)
        if not class_obj:
            return jsonify({
                'code': 404,
                'message': f'班级不存在，class_id: {class_id}'
            }), 404
            
        # 创建实验
        new_experiment = Experiment(
            experiment_name=experiment_name,
            class_id=int(class_id),
            teacher_id=int(teacher_id),
            description=description + (f"\n\n实验要求：\n{requirements}" if requirements else ""),
            deadline=datetime.fromisoformat(deadline.replace(' ', 'T'))
        )
        
        db.session.add(new_experiment)
        db.session.flush()  # 获取新实验ID
        
        # 获取当前工作目录和后端目录
        current_dir = os.getcwd()
        backend_dir = os.path.join(current_dir, "DLplatform-be")
        print(f"当前工作目录: {current_dir}")
        print(f"后端目录: {backend_dir}")
        
        # 创建lab+experiment_id文件夹及其子文件夹，放在后端目录下
        lab_folder = f"lab{new_experiment.experiment_id}"
        lab_path = os.path.join(backend_dir, lab_folder)
        testcode_folder = os.path.join(lab_path, "testcode")
        testdata_folder = os.path.join(lab_path, "testdata")
        upload_folder = os.path.join(lab_path, "upload")
        
        print(f"创建文件夹: {lab_path}")
        
        # 创建文件夹
        os.makedirs(lab_path, exist_ok=True)
        os.makedirs(testcode_folder, exist_ok=True)
        os.makedirs(testdata_folder, exist_ok=True)
        os.makedirs(upload_folder, exist_ok=True)
        
        # 保存文件到lab文件夹中的upload文件夹
        file_path = os.path.join(upload_folder, file.filename)
        file.save(file_path)
        
        print(f"文件保存到: {file_path}")
        
        # 获取文件大小（KB）
        file_size = os.path.getsize(file_path) // 1024
        
        # 创建附件记录
        new_attachment = ExperimentAttachment(
            experiment_id=new_experiment.experiment_id,
            file_name=file.filename,
            file_path=file_path,
            file_size=file_size
        )
        
        db.session.add(new_attachment)
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '实验发布成功',
            'data': {
                'experiment': new_experiment.to_dict(),
                'attachment': new_attachment.to_dict()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"发布实验错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '服务器内部错误，发布实验失败'
        }), 500

# 学生提交实验作业
@app.route('/api/experiments/upload', methods=['POST'])
def submit():
    try:
        print("接收到实验提交请求")
        print(f"请求表单数据: {request.form}")
        print(f"请求文件: {request.files}")
        
        # 检查是否有文件
        if 'file' not in request.files:
            print("请求中没有文件")
            return jsonify({
                'code': 400,
                'message': '没有上传文件'
            }), 400
        
        file = request.files['file']
        print(f"接收到文件: {file.filename}, 类型: {file.content_type}")
        
        # 检查文件名是否为空
        if file.filename == '':
            print("文件名为空")
            return jsonify({
                'code': 400,
                'message': '没有选择文件'
            }), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            print(f"不支持的文件类型: {file.filename}")
            return jsonify({
                'code': 400,
                'message': '不支持的文件类型，只支持.zip/.rar/.7z文件'
            }), 400
        
        # 获取请求参数（支持两种参数名格式）
        experiment_id = request.form.get('experimentId')
        student_id = request.form.get('studentId')
        
        print(f"实验ID: {experiment_id}, 学生ID: {student_id}")
        
        # 验证参数
        if not experiment_id or not student_id:
            print("缺少必要参数")
            return jsonify({
                'code': 400,
                'message': '缺少必要参数：experiment_id 或 student_id'
            }), 400
        
        # 验证实验和学生是否存在
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            print(f"实验不存在: {experiment_id}")
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
            
        student = User.query.filter_by(user_id=student_id, user_type=UserType.STUDENT).first()
        if not student:
            print(f"学生不存在: {student_id}")
            return jsonify({
                'code': 404,
                'message': '学生不存在'
            }), 404
            
        # 检查是否已经提交过
        existing_submission = Submission.query.filter_by(
            experiment_id=experiment_id,
            student_id=student_id
        ).first()
        
        # 获取当前工作目录和后端目录
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backend_dir = os.path.join(current_dir, "DLplatform-be")
        print(f"当前工作目录: {current_dir}")
        print(f"后端目录: {backend_dir}")
        
        # 使用lab文件夹的testcode目录，放在后端目录下
        lab_folder = f"lab{experiment_id}"
        lab_path = os.path.join(backend_dir, lab_folder)
        testcode_folder = os.path.join(lab_path, "testcode")
        
        print(f"上传文件到: {testcode_folder}")
        
        # 保存原始文件名（不带扩展名）
        original_file_name = str(file.filename)
        file_name_without_ext = os.path.splitext(original_file_name)[0]
        
        # 确保testcode目录存在
        try:
            if not os.path.exists(testcode_folder):
                os.makedirs(testcode_folder, exist_ok=True)
                print(f"创建目录: {testcode_folder}")
        except Exception as e:
            print(f"创建目录失败: {e}")
            return jsonify({
                'code': 500,
                'message': f'创建目录失败: {str(e)}'
            }), 500
            
        # 临时保存文件的路径（直接保存到testcode目录中）
        temp_file_path = os.path.join(testcode_folder, original_file_name)
        
        if existing_submission:
            print("更新现有提交")
            # 如果数据库中记录的旧文件存在，则删除旧文件，实现覆盖上传
            old_file_path = existing_submission.file_path
            if old_file_path and os.path.exists(old_file_path) and old_file_path != testcode_folder:
                if os.path.isfile(old_file_path):
                    os.remove(old_file_path)
                    print(f"删除旧文件: {old_file_path}")
                elif os.path.isdir(old_file_path):
                    shutil.rmtree(old_file_path)
                    print(f"删除旧目录: {old_file_path}")
            # 保存文件
            try:
                file.save(temp_file_path)
                print(f"文件保存成功: {temp_file_path}")
            except Exception as e:
                print(f"保存文件失败: {e}")
                return jsonify({
                    'code': 500,
                    'message': f'保存文件失败: {str(e)}'
                }), 500
                
            # 解压文件到testcode目录
            try:
                print(f"开始解压文件: {original_file_name}")
                if original_file_name.lower().endswith('.zip'):
                    with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                        zip_ref.extractall(testcode_folder)
                    print(f"成功解压ZIP文件到: {testcode_folder}")
                    # 解压完成后删除原始压缩文件
                    os.remove(temp_file_path)
                    print(f"删除原始压缩文件: {temp_file_path}")
                elif original_file_name.lower().endswith('.rar') or original_file_name.lower().endswith('.7z'):
                    Archive(temp_file_path).extractall(testcode_folder)
                    print(f"成功解压RAR/7Z文件到: {testcode_folder}")
                    # 解压完成后删除原始压缩文件
                    os.remove(temp_file_path)
                    print(f"删除原始压缩文件: {temp_file_path}")
                else:
                    print(f"不支持的文件类型，无法解压: {original_file_name}")
            except Exception as e:
                print(f"解压文件失败: {e}")
                return jsonify({
                    'code': 500,
                    'message': f'解压文件失败: {str(e)}'
                }), 500
                
            # 计算文件夹大小（KB）
            folder_size = 0
            for dirpath, dirnames, filenames in os.walk(testcode_folder):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        folder_size += os.path.getsize(fp)
            folder_size = folder_size // 1024
            print(f"文件夹大小: {folder_size}KB")
            
            # 覆盖数据库中的旧记录
            try:
                existing_submission.file_name = file_name_without_ext  # 使用不带扩展名的原始文件名
                existing_submission.file_path = testcode_folder  # 保存解压后的文件夹路径
                existing_submission.submit_time = datetime.utcnow()
                print(f"更新提交记录: {existing_submission}")
                
                # 更新附件记录
                existing_experiment_attachment = ExperimentAttachment.query.filter_by(
                    file_name=existing_submission.file_name,
                    file_path=existing_submission.file_path
                ).first()
                
                if existing_experiment_attachment:
                    existing_experiment_attachment.file_name = file_name_without_ext  # 使用不带扩展名的原始文件名
                    existing_experiment_attachment.file_path = testcode_folder  # 保存解压后的文件夹路径
                    existing_experiment_attachment.file_size = folder_size
                    print(f"更新附件记录: {existing_experiment_attachment}")
                    
                db.session.commit()
                print("数据库更新成功")
            except Exception as e:
                db.session.rollback()
                print(f"更新数据库失败: {e}")
                return jsonify({
                    'code': 500,
                    'message': f'更新数据库失败: {str(e)}'
                }), 500
        else:
            print("创建新提交")
            try:
                file.save(temp_file_path)
                print(f"文件保存成功: {temp_file_path}")
            except Exception as e:
                print(f"保存文件失败: {e}")
                return jsonify({
                    'code': 500,
                    'message': f'保存文件失败: {str(e)}'
                }), 500
                
            # 解压文件到testcode目录
            try:
                print(f"开始解压文件: {original_file_name}")
                if original_file_name.lower().endswith('.zip'):
                    with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                        zip_ref.extractall(testcode_folder)
                    print(f"成功解压ZIP文件到: {testcode_folder}")
                    # 解压完成后删除原始压缩文件
                    os.remove(temp_file_path)
                    print(f"删除原始压缩文件: {temp_file_path}")
                elif original_file_name.lower().endswith('.rar') or original_file_name.lower().endswith('.7z'):
                    Archive(temp_file_path).extractall(testcode_folder)
                    print(f"成功解压RAR/7Z文件到: {testcode_folder}")
                    # 解压完成后删除原始压缩文件
                    os.remove(temp_file_path)
                    print(f"删除原始压缩文件: {temp_file_path}")
                else:
                    print(f"不支持的文件类型，无法解压: {original_file_name}")
            except Exception as e:
                print(f"解压文件失败: {e}")
                return jsonify({
                    'code': 500,
                    'message': f'解压文件失败: {str(e)}'
                }), 500
                
            # 计算文件夹大小（KB）
            folder_size = 0
            for dirpath, dirnames, filenames in os.walk(testcode_folder):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        folder_size += os.path.getsize(fp)
            folder_size = folder_size // 1024
            print(f"文件夹大小: {folder_size}KB")
            
            # 插入实验附件记录和学生提交记录（使用文件夹名称和路径）
            if not insert_experiment_attachment(experiment_id, file_name_without_ext, testcode_folder, folder_size):
                return jsonify({
                    'code': 500,
                    'message': '保存实验附件记录失败'
                }), 500
            
            # 插入学生提交记录
            if not insert_submission(experiment_id, student_id, file_name_without_ext, testcode_folder):
                return jsonify({
                    'code': 500,
                    'message': '保存学生提交记录失败'
                }), 500
                
        print("实验提交成功")
        return jsonify({
            'code': 200,
            'message': '提交成功'
        })
        
    except Exception as e:
        print(f"提交过程中发生错误: {e}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

# 获取实验提交记录
@app.route('/api/experiments/<int:experiment_id>/uploads', methods=['GET'])
def get_api_experiment_uploads(experiment_id):
    """
    获取实验的上传历史（新API路径）
    """
    try:
        # 获取该实验的所有提交记录
        submissions = Submission.query.filter_by(experiment_id=experiment_id).all()
        print(f"实验 {experiment_id} 的提交记录: {submissions}")
        upload_history = []
        for submission in submissions:
            try:
                file_size = 0
                if submission.file_path and os.path.exists(submission.file_path):
                    if os.path.isfile(submission.file_path):
                        file_size = os.path.getsize(submission.file_path)
                    elif os.path.isdir(submission.file_path):
                        # 如果是目录，计算目录大小
                        total_size = 0
                        for dirpath, dirnames, filenames in os.walk(submission.file_path):
                            for f in filenames:
                                fp = os.path.join(dirpath, f)
                                if os.path.exists(fp):
                                    total_size += os.path.getsize(fp)
                        file_size = total_size
                
                upload_history.append({
                    'id': submission.submission_id,
                    'fileName': submission.file_name,
                    'fileSize': file_size,
                    'uploadTime': submission.submit_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'success'
                })
            except Exception as e:
                print(f"处理提交记录时出错: {e}")
                continue
        
        return jsonify({
            'code': 200,
            'message': '获取上传历史成功',
            'data': upload_history
        })
        
    except Exception as e:
        print(f"获取上传历史时发生错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '获取上传历史失败'
        })

@app.route('/test', methods=['GET', 'OPTIONS'])
def test_models():
    """
    评测模块接口
    根据实验ID，查找所有提交的模型文件，进行评测并保存成绩
    """
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        # 获取实验ID参数
        experiment_id = request.args.get('experimentId')
        print(f"开始评测实验 ID: {experiment_id}")
        
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
        
        evaluated_count = 0
        evaluation_results = []
        print(f"开始评测，共有{len(submissions)}个提交记录")
        
        # 直接指定标签文件的路径
        lab_folder = f"lab{experiment_id}"
        print(f"实验对应的文件夹: {lab_folder}")
        
                # 优先查找实验对应的testdata目录下的all_labels.csv
        possible_label_paths = [
            os.path.join(os.getcwd(), lab_folder, "testdata", "all_labels.csv"),  # 当前目录下的实验文件夹
            os.path.join(os.getcwd(), "..", lab_folder, "testdata", "all_labels.csv"),  # 上级目录下的实验文件夹
            os.path.join(os.getcwd(), "testdata", "all_labels.csv")  # 当前目录下的testdata文件夹
        ]
            
        # 如果当前实验不是lab7，也尝试查找lab7中的标签文件作为备用
        if lab_folder != "lab7":
            possible_label_paths.append(os.path.join(os.getcwd(), "lab7", "testdata", "all_labels.csv"))
        
        labels_file = None
        for path in possible_label_paths:
            if os.path.exists(path):
                labels_file = path
                print(f"找到真实标签文件: {labels_file}")
                break
        if not labels_file:
            return jsonify({
                'code': 400,
                'message': f'找不到真实标签文件，请确保{lab_folder}/testdata目录中存在all_labels.csv文件'
            }), 400
            
        # 读取真实标签
        try:
            labels_df = pd.read_csv(labels_file)
            true_labels = labels_df.iloc[:, 0].tolist()
            print(f"成功读取真实标签，共{len(true_labels)}个标签")
            
            # 如果标签文件中的标签数量与预期不符，给出警告但继续执行
            if len(true_labels) < 1000:
                print(f"警告：标签文件中只有{len(true_labels)}个标签，这可能不是完整的测试集")
        except Exception as e:
            print(f"读取真实标签文件失败: {str(e)}")
            return jsonify({
                'code': 400,
                'message': f'读取真实标签文件失败: {str(e)}'
            }), 400
        
        # 创建一个已处理的学生ID集合，避免重复评测
        processed_students = set()
        
        for submission in submissions:
            try:
                # 如果已经处理过该学生的提交，则跳过
                if submission.student_id in processed_students:
                    print(f"学生 {submission.student_id} 的提交已经评测过，跳过")
                    continue
                
                # 将学生ID添加到已处理集合
                processed_students.add(submission.student_id)
                
                # 检查学生提交的文件夹是否存在
                student_folder_path = submission.file_path
                if not os.path.exists(student_folder_path) or not os.path.isdir(student_folder_path):
                    print(f"学生提交文件夹不存在: {student_folder_path}")
                    evaluation_results.append({
                        "student_id": submission.student_id,
                        "status": "error",
                        "message": f"提交文件夹不存在: {student_folder_path}"
                    })
                    continue
                
                print(f"评测学生 {submission.student_id} 的提交: {student_folder_path}")
                
                # 检查是否是特殊情况：文件夹是lab/testcode/学号
                testcode_path = os.path.join(os.getcwd(), lab_folder, "testcode")
                is_testcode_submission = student_folder_path.startswith(testcode_path)
                
                # 在文件夹中查找Python文件
                python_files = []
                
                # 如果提交路径是testcode根目录，需要找到该学生的特定文件夹
                if is_testcode_submission and student_folder_path == testcode_path:
                    print(f"提交路径是testcode根目录，查找学生 {submission.student_id} 的特定文件夹")
                    
                    # 使用file_name作为学生特定的文件夹或文件名
                    student_specific_folder = os.path.join(student_folder_path, submission.file_name)
                    if os.path.isdir(student_specific_folder):
                        print(f"找到学生特定文件夹: {student_specific_folder}")
                        student_folder_path = student_specific_folder
                        
                        # 在学生特定文件夹中查找Python文件
                        for root, dirs, files in os.walk(student_specific_folder):
                            for file in files:
                                if file.endswith('.py'):
                                    python_files.append(os.path.join(root, file))
                    
                    # 如果没有找到学生特定文件夹，尝试查找与file_name同名的Python文件
                    if not python_files:
                        student_specific_file = os.path.join(student_folder_path, f"{submission.file_name}.py")
                        if os.path.exists(student_specific_file):
                            print(f"找到学生特定文件: {student_specific_file}")
                            python_files.append(student_specific_file)
                else:
                    # 正常情况下在提交文件夹中查找Python文件
                    for root, dirs, files in os.walk(student_folder_path):
                        for file in files:
                            if file.endswith('.py'):
                                python_files.append(os.path.join(root, file))
                if not python_files:
                    print(f"学生文件夹中没有找到Python文件: {student_folder_path}")
                    
                    # 特殊处理：如果是testcode下的提交，尝试查找与文件夹同名的Python文件
                    if is_testcode_submission:
                        folder_name = submission.file_name  # 使用submission.file_name而不是os.path.basename
                        possible_py_file = os.path.join(student_folder_path, f"{folder_name}.py")
                        print(f"尝试查找特定文件: {possible_py_file}")
                        
                        if os.path.exists(possible_py_file):
                            python_files.append(possible_py_file)
                            print(f"找到特定文件: {possible_py_file}")
                    
                    if not python_files:
                        evaluation_results.append({
                            "student_id": submission.student_id,
                            "status": "error",
                            "message": "提交文件夹中没有找到Python文件"
                        })
                        continue
                
                # 优先查找main.py或者包含model的Python文件
                main_file = None
                
                # 首先尝试查找与submission.file_name同名的Python文件
                for py_file in python_files:
                    file_name = os.path.basename(py_file).lower()
                    if file_name.lower() == f"{submission.file_name.lower()}.py":
                        main_file = py_file
                        print(f"找到与提交名称匹配的文件: {main_file}")
                        break
                
                # 如果没找到同名文件，再查找main.py或包含model的文件
                if not main_file:
                    for py_file in python_files:
                        file_name = os.path.basename(py_file).lower()
                        if file_name == 'main.py':
                            main_file = py_file
                            break
                        elif 'model' in file_name:
                            main_file = py_file
                            break
                
                # 如果还没有找到，使用第一个Python文件
                if not main_file and python_files:
                    main_file = python_files[0]
                
                if not main_file:
                    print(f"无法确定要评测的Python文件: {student_folder_path}")
                    evaluation_results.append({
                        "student_id": submission.student_id,
                        "status": "error",
                        "message": "无法确定要评测的Python文件"
                    })
                    continue
                
                print(f"使用文件进行评测: {main_file}")
                
                # 获取学生代码所在目录
                student_dir = os.path.dirname(main_file)
                
                # 复制真实标签文件到学生目录
                student_labels_file = os.path.join(student_dir, "all_labels.csv")
                if not os.path.exists(student_labels_file):
                    try:
                        # 在Windows上使用复制，在Linux/Mac上可以使用符号链接
                        shutil.copy2(labels_file, student_labels_file)
                        print(f"复制标签文件到学生目录: {student_labels_file}")
                    except Exception as e:
                        print(f"复制标签文件失败，但将继续尝试评测: {e}")
                
                # 执行学生代码进行评测
                print(f"开始执行学生代码: {main_file}")
                result = execute_student_code(main_file)
                score = result.get("score", 0.0)
                
                # 记录评测结果
                print(f"评测结果: {result}")
                # 保存成绩到数据库
                if insert_grade(submission.submission_id, experiment_id, submission.student_id, score, experiment.teacher_id):
                    evaluated_count += 1
                    message = result.get("message", "评测完成")
                    print(f"学生 {submission.student_id} 的模型评测完成，得分: {score}, 消息: {message}")
                    evaluation_results.append({
                        "student_id": submission.student_id,
                        "status": "success",
                        "score": score,
                        "message": message,
                        "details": {k: v for k, v in result.items() if k not in ["score", "message"]}
                    })
                else:
                    print(f"保存学生 {submission.student_id} 的成绩失败")
                    evaluation_results.append({
                        "student_id": submission.student_id,
                        "status": "failed",
                        "message": "保存成绩失败",
                        "details": result
                    })
                    
            except Exception as e:
                print(f"评测学生 {submission.student_id} 的模型时发生错误: {e}")
                traceback.print_exc()
                evaluation_results.append({
                    "student_id": submission.student_id,
                    "status": "error",
                    "message": str(e)
                })
                continue
        
        # 返回结果
        return jsonify({
            'code': 200,
            'message': f'评测完成，共评测了 {evaluated_count} 个模型',
            'data': {
                'evaluated_count': evaluated_count,
                'total_submissions': len(submissions),
                'results': evaluation_results
            }
        })
        
    except Exception as e:
        print(f"评测过程中发生错误: {e}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
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
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查用户角色，只有教师才能创建班级
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            "code": 403,
            "message": "权限不足，只有教师可以创建班级"
        }), 403
    
    data = request.get_json()
    if not data:
        return jsonify({
            "code": 400,
            "message": "请求数据不能为空"
        }), 400
    
    class_name = data.get('class_name')
    
    # 参数校验
    if not class_name or not isinstance(class_name, str) or len(class_name) > 100:
        return jsonify({
            "code": 400,
            "message": "参数错误：班级名称不能为空/长度超出限制"
        }), 400
    
    # 使用当前登录教师的ID作为teacher_id
    teacher_id = current_user.user_id
    
    try:
        # 创建新班级
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

@app.route('/classes/<int:class_id>', methods=['PUT'])
def update_class(class_id):
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查用户角色，只有教师才能更新班级
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            "code": 403,
            "message": "权限不足，只有教师可以更新班级"
        }), 403
    
    # 检查班级是否存在
    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({
            "code": 404,
            "message": f"班级不存在，class_id: {class_id}"
        }), 404
    
    # 检查是否是班级的创建者
    if class_obj.teacher_id != current_user.user_id:
        return jsonify({
            "code": 403,
            "message": "权限不足，只有班级创建者可以更新班级"
        }), 403
    
    data = request.get_json()
    if not data:
        return jsonify({
            "code": 400,
            "message": "请求数据不能为空"
        }), 400
    
    class_name = data.get('class_name')
    
    # 参数校验
    if not class_name or not isinstance(class_name, str) or len(class_name) > 100:
        return jsonify({
            "code": 400,
            "message": "参数错误：班级名称不能为空/长度超出限制"
        }), 400
    
    try:
        # 更新班级名称
        class_obj.class_name = class_name
        db.session.commit()
        
        return jsonify({
            "code": 200,
            "message": "班级更新成功",
            "data": {
                "class_id": class_obj.class_id,
                "class_name": class_obj.class_name,
                "teacher_id": class_obj.teacher_id
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print("数据库更新异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，班级更新失败，请重试"
        }), 500

@app.route('/classes/<int:class_id>', methods=['DELETE'])
def delete_class(class_id):
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查用户角色，只有教师才能删除班级
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            "code": 403,
            "message": "权限不足，只有教师可以删除班级"
        }), 403
    
    # 检查班级是否存在
    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({
            "code": 404,
            "message": f"班级不存在，class_id: {class_id}"
        }), 404
    
    # 检查是否是班级的创建者
    if class_obj.teacher_id != current_user.user_id:
        return jsonify({
            "code": 403,
            "message": "权限不足，只有班级创建者可以删除班级"
        }), 403
    
    try:
        # 先解除所有学生与该班级的关联
        students = User.query.filter_by(class_id=class_id).all()
        for student in students:
            student.class_id = None
        
        # 删除班级
        db.session.delete(class_obj)
        db.session.commit()
        
        return jsonify({
            "code": 200,
            "message": "班级删除成功"
        }), 200
    except Exception as e:
        db.session.rollback()
        print("数据库删除异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，班级删除失败，请重试"
        }), 500

@app.route('/classes/<int:class_id>/students', methods=['GET'])
def get_class_students(class_id):
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查班级是否存在
    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({
            "code": 404,
            "message": f"班级不存在，class_id: {class_id}"
        }), 404
    
    try:
        # 获取班级的所有学生
        students = User.query.filter_by(class_id=class_id, user_type='student').all()
        student_list = []
        for student in students:
            student_list.append({
                "id": student.user_id,
                "username": student.username,
                "name": student.real_name,
                "studentId": student.student_id,
                "email": student.email
            })
        
        return jsonify({
            "code": 200,
            "message": "获取成功",
            "data": student_list
        }), 200
    except Exception as e:
        print("获取班级学生列表异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，获取班级学生列表失败，请重试"
        }), 500

@app.route('/classes/<int:class_id>/students', methods=['POST'])
def add_student_to_class(class_id):
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查用户角色，只有教师才能添加学生到班级
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            "code": 403,
            "message": "权限不足，只有教师可以添加学生到班级"
        }), 403
    
    # 检查班级是否存在
    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({
            "code": 404,
            "message": f"班级不存在，class_id: {class_id}"
        }), 404
    
    # 检查是否是班级的创建者
    if class_obj.teacher_id != current_user.user_id:
        return jsonify({
            "code": 403,
            "message": "权限不足，只有班级创建者可以添加学生到班级"
        }), 403
    
    data = request.get_json()
    if not data:
        return jsonify({
            "code": 400,
            "message": "请求数据不能为空"
        }), 400
    
    username = data.get('username')
    if not username:
        return jsonify({
            "code": 400,
            "message": "参数错误：学生用户名不能为空"
        }), 400
    
    try:
        # 查找学生
        student = User.query.filter_by(username=username, user_type='student').first()
        if not student:
            return jsonify({
                "code": 404,
                "message": f"学生不存在，username: {username}"
            }), 404
        
        # 将学生添加到班级
        student.class_id = class_id
        db.session.commit()
        
        return jsonify({
            "code": 200,
            "message": "学生添加成功",
            "data": {
                "student_id": student.user_id,
                "username": student.username,
                "name": student.real_name,
                "class_id": class_id
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print("添加学生到班级异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，添加学生到班级失败，请重试"
        }), 500

@app.route('/classes/<int:class_id>/students/<int:student_id>', methods=['DELETE'])
def remove_student_from_class(class_id, student_id):
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 检查用户角色，只有教师才能从班级移除学生
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({
            "code": 403,
            "message": "权限不足，只有教师可以从班级移除学生"
        }), 403
    
    # 检查班级是否存在
    class_obj = Class.query.get(class_id)
    if not class_obj:
        return jsonify({
            "code": 404,
            "message": f"班级不存在，class_id: {class_id}"
        }), 404
    
    # 检查是否是班级的创建者
    if class_obj.teacher_id != current_user.user_id:
        return jsonify({
            "code": 403,
            "message": "权限不足，只有班级创建者可以从班级移除学生"
        }), 403
    
    try:
        # 查找学生
        student = User.query.get(student_id)
        if not student or student.user_type != 'student':
            return jsonify({
                "code": 404,
                "message": f"学生不存在或用户不是学生，student_id: {student_id}"
            }), 404
        
        # 检查学生是否在该班级
        if student.class_id != class_id:
            return jsonify({
                "code": 400,
                "message": f"学生不在该班级，student_id: {student_id}, class_id: {class_id}"
            }), 400
        
        # 将学生从班级移除
        student.class_id = None
        db.session.commit()
        
        return jsonify({
            "code": 200,
            "message": "学生移除成功"
        }), 200
    except Exception as e:
        db.session.rollback()
        print("从班级移除学生异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，从班级移除学生失败，请重试"
        }), 500

@app.route('/classes', methods=['GET'])
def get_classes():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    # 获取查询参数
    teacher_id = request.args.get('teacher_id')
    
    try:
        # 构建查询
        query = Class.query
        
        # 如果指定了教师ID，则只返回该教师创建的班级
        if teacher_id:
            try:
                teacher_id = int(teacher_id)
                query = query.filter_by(teacher_id=teacher_id)
            except (TypeError, ValueError):
                return jsonify({
                    "code": 400,
                    "message": "参数错误：teacher_id必须为整数"
                }), 400
        
        # 如果是教师用户，默认只返回自己创建的班级
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type == 'teacher' and not teacher_id:
            query = query.filter_by(teacher_id=current_user.user_id)
        
        # 执行查询
        classes = query.all()
        
        # 构建返回数据
        class_list = []
        for class_obj in classes:
            class_list.append({
                "class_id": class_obj.class_id,
                "class_name": class_obj.class_name,
                "teacher_id": class_obj.teacher_id
            })
        
        return jsonify({
            "code": 200,
            "message": "获取成功",
            "data": class_list
        }), 200
    except Exception as e:
        print("获取班级列表异常：", e)
        return jsonify({
            "code": 500,
            "message": "服务器内部错误，获取班级列表失败，请重试"
        }), 500

# 获取实验列表接口
@app.route('/experiments/list', methods=['GET', 'OPTIONS'])
def get_experiments_list():
    """
    获取当前学生可访问的实验列表
    """
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    try:
        # 获取当前用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401
        
        # 获取用户类型
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        
        # 根据用户类型获取不同的实验列表
        if user_type == 'student':
            # 学生只能看到自己班级的实验
            class_id = current_user.class_id
            if not class_id:
                return jsonify({
                    'code': 200,
                    'message': '获取成功',
                    'data': []  # 如果学生没有班级，返回空列表
                })
            
            # 查询该班级的所有实验
            experiments = Experiment.query.filter_by(class_id=class_id).order_by(Experiment.publish_time.desc()).all()
            
            # 查询学生的提交记录
            submissions = Submission.query.filter_by(student_id=current_user.user_id).all()
            submitted_experiment_ids = {submission.experiment_id for submission in submissions}
            
            # 构建返回数据
            experiment_list = []
            for exp in experiments:
                exp_data = exp.to_dict()
                exp_data['submitted'] = exp.experiment_id in submitted_experiment_ids
                experiment_list.append(exp_data)
            
            return jsonify({
                'code': 200,
                'message': '获取成功',
                'data': experiment_list
            })
        
        elif user_type == 'teacher':
            # 教师可以看到自己创建的实验
            experiments = Experiment.query.filter_by(teacher_id=current_user.user_id).order_by(Experiment.publish_time.desc()).all()
            experiment_list = [exp.to_dict() for exp in experiments]
            
            return jsonify({
                'code': 200,
                'message': '获取成功',
                'data': experiment_list
            })
        
        else:
            return jsonify({
                'code': 403,
                'message': '无效的用户类型'
            }), 403
    
    except Exception as e:
        print("获取实验列表异常：", e)
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': '服务器内部错误，获取实验列表失败'
        }), 500

# 下载附件
@app.route('/download/attachment/<int:attachment_id>', methods=['GET', 'OPTIONS'])
def download_attachment(attachment_id):
    """
    下载实验附件
    """
    # 处理OPTIONS请求（预检请求）
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
    
    try:
        # 查询附件信息
        attachment = ExperimentAttachment.query.get(attachment_id)
        if not attachment:
            return jsonify({
                'code': 404,
                'message': f'附件不存在，attachment_id: {attachment_id}'
            }), 404
        
        print(f"尝试下载文件: {attachment.file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(attachment.file_path):
            print(f"文件不存在: {attachment.file_path}")
            print(f"当前工作目录: {os.getcwd()}")
            
            # 尝试在lab文件夹中查找
            experiment_id = attachment.experiment_id
            file_name = attachment.file_name
            
            # 获取当前工作目录和后端目录
            current_dir = os.getcwd()
            backend_dir = os.path.join(current_dir, "DLplatform-be")
            print(f"后端目录: {backend_dir}")
            
            # 尝试不同的文件路径
            possible_paths = [
                os.path.join(backend_dir, f"lab{experiment_id}", "upload", file_name),  # 后端目录下的lab文件夹
                os.path.join(current_dir, f"lab{experiment_id}", "upload", file_name),  # 当前目录下的lab文件夹
                os.path.join(f"lab{experiment_id}", "upload", file_name),  # 相对路径
            ]
            
            file_found = False
            for path in possible_paths:
                print(f"尝试替代路径: {path}")
                if os.path.exists(path):
                    print(f"找到文件在替代路径: {path}")
                    attachment.file_path = path
                    db.session.commit()
                    file_found = True
                    break
            
            if not file_found:
                return jsonify({
                    'code': 404,
                    'message': f'文件不存在，file_path: {attachment.file_path}'
                }), 404
        
        # 获取文件名，使用原始文件名
        filename = os.path.basename(attachment.file_path)
        
        # 返回文件
        response = send_file(
            attachment.file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
        # 添加CORS头
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    
    except Exception as e:
        print(f"下载附件错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误，下载附件失败: {str(e)}'
        }), 500

@app.route('/teacher/experiments', methods=['GET'])
def get_teacher_experiments():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': '未授权访问'}), 401
    
    # 确保是教师用户
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({'error': '只有教师可以访问此资源'}), 403
    
    # 获取查询参数
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    recent = request.args.get('recent', 'false').lower() == 'true'
    
    # 查询该教师创建的所有实验
    query = Experiment.query.filter_by(teacher_id=current_user.user_id)
    
    # 如果请求最近的实验，按发布时间降序排序
    if recent:
        query = query.order_by(Experiment.publish_time.desc())
    
    # 分页
    total = query.count()
    experiments = query.offset((page - 1) * limit).limit(limit).all()
    
    # 获取待评价的提交数量
    pending_evaluations = db.session.query(Submission).join(
        Experiment, Submission.experiment_id == Experiment.experiment_id
    ).filter(
        Experiment.teacher_id == current_user.user_id,
        ~db.exists().where(Grade.submission_id == Submission.submission_id)
    ).count()
    
    # 构建响应
    result = {
        'data': [exp.to_dict() for exp in experiments],
        'total': total,
        'page': page,
        'limit': limit,
        'pendingEvaluations': pending_evaluations
    }
    
    return jsonify(result)

@app.route('/evaluations', methods=['GET'])
def get_evaluations():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': '未授权访问'}), 401
    
    # 确保是教师用户
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'teacher':
        return jsonify({'error': '只有教师可以访问此资源'}), 403
    
    experiment_id = request.args.get('experiment_id')
    class_id = request.args.get('class_id')
    status = request.args.get('status')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    
    # 构建基础查询 - 使用四表联合查询
    query = db.session.query(
        Submission,
        User,
        Class,
        Grade,
        Experiment
    ).join(
        User, Submission.student_id == User.user_id
    ).join(
        Class, User.class_id == Class.class_id
    ).outerjoin(
        Grade, Submission.submission_id == Grade.submission_id
    ).join(
        Experiment, Submission.experiment_id == Experiment.experiment_id
    )
    
    # 只显示当前教师创建的实验的提交
    query = query.filter(Experiment.teacher_id == current_user.user_id)
    
    # 应用过滤条件
    if experiment_id:
        try:
            experiment_id = int(experiment_id)
            query = query.filter(Submission.experiment_id == experiment_id)
            
            # 验证实验是否存在且属于当前教师
            experiment = Experiment.query.get(experiment_id)
            if not experiment:
                return jsonify({'error': '实验不存在'}), 404
            
            if experiment.teacher_id != current_user.user_id:
                return jsonify({'error': '您没有权限查看此实验的评价'}), 403
        except ValueError:
            return jsonify({'error': '实验ID必须是整数'}), 400
    
    if class_id and class_id != '':
        try:
            class_id = int(class_id)
            query = query.filter(Class.class_id == class_id)
        except ValueError:
            return jsonify({'error': '班级ID必须是整数'}), 400
            
    if status and status != '':
        try:
            status = int(status)
            if status == 1:  # 已提交未评测
                query = query.filter(Grade.score == None)
            elif status == 2 or status == 3:  # 已评价/已评测
                query = query.filter(Grade.score != None)
        except ValueError:
            return jsonify({'error': '状态值必须是整数'}), 400

    # 获取总数
    total = query.count()
    
    # 分页
    results = query.order_by(Submission.submit_time.desc()).offset((page - 1) * limit).limit(limit).all()
    
    # 打印调试信息
    print(f"找到 {total} 条提交记录")
    
    # 构建返回数据
    data = []
    for submission, user, class_, grade, experiment in results:
        data.append({
            'id': submission.submission_id,
            'experiment_title': experiment.experiment_name,
            'student_name': user.real_name or user.username,
            'class_name': class_.class_name,
            'submit_time': submission.submit_time.strftime('%Y-%m-%d %H:%M:%S') if submission.submit_time else '',
            'status': 3 if grade and grade.score is not None else 1,  # 3:已评测, 1:待评测
            'score': float(grade.score) if grade and grade.score is not None else None,
            'file_path': submission.file_path,
            'file_name': submission.file_name,
            'experiment_id': experiment.experiment_id
        })
    
    print(f"返回数据: {data}")
    
    return jsonify({
        'data': {
            'list': data,
            'total': total
        }
    })

@app.route('/results', methods=['GET'])
def get_results():
    experiment_id = request.args.get('experiment_id')
    class_id = request.args.get('class_id')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))

    query = db.session.query(
        Grade,
        User,
        Class,
        Experiment
    ).join(
        User, Grade.student_id == User.user_id
    ).join(
        Class, User.class_id == Class.class_id
    ).join(
        Experiment, Grade.experiment_id == Experiment.experiment_id
    )

    if experiment_id:
        query = query.filter(Grade.experiment_id == experiment_id)
    if class_id:
        query = query.filter(Class.class_id == class_id)

    total = query.count()
    results = query.order_by(Grade.graded_at.desc()).offset((page - 1) * limit).limit(limit).all()

    data = []
    for grade, user, class_, experiment in results:
        data.append({
            'id': grade.grade_id,
            'experiment_title': experiment.experiment_name,
            'student_name': user.real_name or user.username,
            'class_name': class_.class_name,
            'score': float(grade.score),
            'graded_at': grade.graded_at.strftime('%Y-%m-%d %H:%M:%S') if grade.graded_at else '',
            'submission_id': grade.submission_id
        })

    return jsonify({
        'data': {
            'list': data,
            'total': total
        }
    })

@app.route('/api/teacher/experiments', methods=['GET'])
def api_teacher_experiments():
    experiments = Experiment.query.all()
    data = []
    for e in experiments:
        data.append({
            'id': e.experiment_id,
            'title': e.experiment_name,
            'class_id': e.class_id,
            'deadline': e.deadline.strftime('%Y-%m-%d %H:%M:%S') if e.deadline else '',
        })
    return jsonify({'data': data})

@app.route('/api/classes', methods=['GET'])
def api_classes():
    classes = Class.query.all()
    data = []
    for c in classes:
        data.append({
            'id': c.class_id,
            'name': c.class_name,
            'teacher_id': c.teacher_id
        })
    return jsonify({'data': data})

@app.route('/api/student/experiments', methods=['GET', 'OPTIONS'])
def api_student_experiments():
    # 分页参数
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    keyword = request.args.get('keyword', '').strip()
    
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': '未授权访问'}), 401
    
    # 确保是学生用户
    user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
    if user_type != 'student':
        return jsonify({'error': '只有学生可以访问此资源'}), 403
    
    student_id = current_user.user_id

    query = Experiment.query

    if keyword:
        query = query.filter(Experiment.experiment_name.like(f'%{keyword}%'))

    total = query.count()
    experiments = query.order_by(Experiment.publish_time.desc()).offset((page - 1) * limit).limit(limit).all()

    # 获取所有教师ID
    teacher_ids = [e.teacher_id for e in experiments]
    teachers = User.query.filter(User.user_id.in_(teacher_ids)).all()
    teacher_map = {t.user_id: t.real_name or t.username for t in teachers}

    # 获取当前学生所有提交
    exp_ids = [e.experiment_id for e in experiments]
    submissions = Submission.query.filter(
        Submission.experiment_id.in_(exp_ids),
        Submission.student_id == student_id
    ).all()
    submitted_map = {s.experiment_id: True for s in submissions}

    data = []
    for e in experiments:
        data.append({
            'id': e.experiment_id,
            'title': e.experiment_name,
            'teacherName': teacher_map.get(e.teacher_id, ''),
            'startTime': e.publish_time.strftime('%Y-%m-%d %H:%M:%S') if e.publish_time else '',
            'endTime': e.deadline.strftime('%Y-%m-%d %H:%M:%S') if e.deadline else '',
            'submitted': submitted_map.get(e.experiment_id, False)
        })

    return jsonify({
        'data': data,
        'total': total
    })

@app.route('/api/experiments/<int:experiment_id>', methods=['GET', 'OPTIONS'])
def get_api_experiment_detail(experiment_id):
    experiment = Experiment.query.get(experiment_id)
    if not experiment:
        return jsonify({'error': '实验不存在'}), 404
    # 获取教师姓名
    teacher = User.query.get(experiment.teacher_id)
    teacher_name = teacher.real_name or teacher.username if teacher else ''
    return jsonify({
        'id': experiment.experiment_id,
        'title': experiment.experiment_name,
        'teacherName': teacher_name,
        'deadline': experiment.deadline.strftime('%Y-%m-%d %H:%M:%S') if experiment.deadline else '',
        'description': experiment.description,
        'publishTime': experiment.publish_time.strftime('%Y-%m-%d %H:%M:%S') if experiment.publish_time else ''
    })

@app.route('/courses', methods=['GET'])
def get_courses():
    # 获取当前登录用户
    current_user = get_current_user()
    if not current_user:
        return jsonify({
            "code": 401,
            "message": "未登录或登录已过期"
        }), 401
    
    try:
        # 由于我们暂时没有课程表，这里使用班级作为课程返回
        # 在实际应用中，应该创建一个课程表并查询课程数据
        classes = Class.query.all()
        
        # 构建返回数据
        courses_list = []
        for class_obj in classes:
            # 查询教师信息
            teacher = User.query.get(class_obj.teacher_id)
            teacher_name = teacher.real_name or teacher.username if teacher else "未知教师"
            
            courses_list.append({
                "id": class_obj.class_id,  # 使用班级ID作为课程ID
                "name": class_obj.class_name,  # 使用班级名称作为课程名称
                "teacher_id": class_obj.teacher_id,
                "teacher_name": teacher_name
            })
        
        return jsonify(courses_list)
    except Exception as e:
        print(f"获取课程列表错误: {str(e)}")
        return jsonify({
            "code": 500,
            "message": f"服务器内部错误: {str(e)}"
        }), 500

@app.route('/teacher/dashboard/stats', methods=['GET'])
def teacher_dashboard_stats():
    """
    获取教师首页的统计数据
    """
    try:
        # 获取当前登录用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401
        
        # 确保是教师用户
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type != 'teacher':
            return jsonify({
                'code': 403,
                'message': '只有教师可以访问此资源'
            }), 403
        
        teacher_id = current_user.user_id
        
        # 获取该教师创建的实验总数
        total_experiments = Experiment.query.filter_by(teacher_id=teacher_id).count()
        
        # 获取进行中的实验数量（发布时间已过，截止时间未到）
        now = datetime.utcnow()
        active_experiments = Experiment.query.filter(
            Experiment.teacher_id == teacher_id,
            Experiment.publish_time <= now,
            Experiment.deadline >= now
        ).count()
        
        # 获取已完成的实验数量（截止时间已过）
        completed_experiments = Experiment.query.filter(
            Experiment.teacher_id == teacher_id,
            Experiment.deadline < now
        ).count()
        
        # 获取待评价的提交数量
        pending_evaluations = db.session.query(Submission).join(
            Experiment, Submission.experiment_id == Experiment.experiment_id
        ).filter(
            Experiment.teacher_id == teacher_id,
            ~db.exists().where(Grade.submission_id == Submission.submission_id)
        ).count()
        
        # 获取该教师班级中的学生总数
        # 先获取该教师的所有班级
        teacher_classes = Class.query.filter_by(teacher_id=teacher_id).all()
        class_ids = [c.class_id for c in teacher_classes]
        
        # 统计这些班级中的学生数量
        total_students = User.query.filter(
            User.class_id.in_(class_ids),
            User.user_type == UserType.STUDENT
        ).count() if class_ids else 0
        
        # 统计已提交作业的学生数量
        # 获取该教师所有实验
        teacher_experiments = Experiment.query.filter_by(teacher_id=teacher_id).all()
        experiment_ids = [e.experiment_id for e in teacher_experiments]
        
        # 获取所有提交了作业的学生ID（去重）
        submitted_students = db.session.query(Submission.student_id).distinct().filter(
            Submission.experiment_id.in_(experiment_ids)
        ).count() if experiment_ids else 0
        
        # 构建响应
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': {
                'totalExperiments': total_experiments,
                'activeExperiments': active_experiments,
                'completedExperiments': completed_experiments,
                'pendingEvaluations': pending_evaluations,
                'totalStudents': total_students,
                'submittedStudents': submitted_students
            }
        })
    except Exception as e:
        print(f"获取教师首页统计数据错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

@app.route('/student/dashboard/stats', methods=['GET'])
def student_dashboard_stats():
    """
    获取学生首页的统计数据
    """
    try:
        # 获取当前登录用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401
        
        # 确保是学生用户
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type != 'student':
            return jsonify({
                'code': 403,
                'message': '只有学生可以访问此资源'
            }), 403
        
        student_id = current_user.user_id
        class_id = current_user.class_id
        
        # 获取该学生班级的实验总数
        total_experiments = Experiment.query.filter_by(class_id=class_id).count() if class_id else 0
        
        # 获取该学生已完成的实验数量
        completed_experiments = db.session.query(Submission).filter(
            Submission.student_id == student_id
        ).count()
        
        # 获取该学生的平均分
        avg_score_result = db.session.query(db.func.avg(Grade.score)).filter(
            Grade.student_id == student_id
        ).first()
        
        average_score = float(avg_score_result[0]) if avg_score_result[0] is not None else 0
        
        # 获取该学生的排名
        # 这里简化处理，只计算有成绩的学生中的排名
        if class_id:
            # 获取同班级所有有成绩的学生
            students_with_scores = db.session.query(
                Grade.student_id,
                db.func.avg(Grade.score).label('avg_score')
            ).group_by(Grade.student_id).all()
            
            # 按平均分排序
            students_with_scores = sorted(students_with_scores, key=lambda x: x[1], reverse=True)
            
            # 查找当前学生的排名
            current_rank = 0
            for i, (sid, _) in enumerate(students_with_scores):
                if sid == student_id:
                    current_rank = i + 1
                    break
        else:
            current_rank = 0
        
        # 构建响应
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': {
                'totalExperiments': total_experiments,
                'completedExperiments': completed_experiments,
                'averageScore': round(average_score, 1),
                'currentRank': current_rank
            }
        })
    except Exception as e:
        print(f"获取学生首页统计数据错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

@app.route('/teacher/experiment/upload-testdata', methods=['POST'])
def upload_experiment_testdata():
    """
    上传实验测试数据（教师端）
    """
    try:
        # 获取当前登录用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401
        
        # 确保是教师用户
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type != 'teacher':
            return jsonify({
                'code': 403,
                'message': '只有教师可以上传测试数据'
            }), 403
        
        # 获取实验ID
        experiment_id = request.form.get('experiment_id')
        if not experiment_id:
            return jsonify({
                'code': 400,
                'message': '缺少实验ID'
            }), 400
        
        # 检查实验是否存在
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
        
        # 确保当前教师是该实验的创建者
        if experiment.teacher_id != current_user.user_id:
            return jsonify({
                'code': 403,
                'message': '您没有权限为此实验上传测试数据'
            }), 403
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify({
                'code': 400,
                'message': '未上传文件'
            }), 400
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            return jsonify({
                'code': 400,
                'message': '未选择文件'
            }), 400
        
        # 检查文件类型
        if not file.filename.lower().endswith('.zip'):
            return jsonify({
                'code': 400,
                'message': '只支持ZIP格式的测试数据文件'
            }), 400
        
        # 获取实验对应的lab文件夹
        lab_name = f"lab{experiment_id}"  # 假设实验ID对应lab文件夹名称
        
        # 确保testdata文件夹存在（而不是testcode）
        # 使用后端目录下的实验文件夹，而不是当前工作目录
        backend_dir = os.path.dirname(os.path.abspath(__file__))  # 获取后端目录的绝对路径
        testdata_dir = os.path.join(backend_dir, lab_name, 'testdata')
        os.makedirs(testdata_dir, exist_ok=True)
        
        # 保存上传的文件到临时位置
        temp_zip_path = os.path.join(testdata_dir, 'temp_testdata.zip')
        file.save(temp_zip_path)
        
        # 解压文件到testdata文件夹
        try:
            import zipfile
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(testdata_dir)
            
            # 删除临时ZIP文件
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            
            return jsonify({
                'code': 200,
                'message': '测试数据上传并解压成功',
                'data': {
                    'experiment_id': experiment_id,
                    'testdata_dir': testdata_dir
                }
            })
        except Exception as e:
            # 如果解压失败，删除临时文件
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            
            print(f"解压测试数据失败: {str(e)}")
            return jsonify({
                'code': 500,
                'message': f'测试数据解压失败: {str(e)}'
            }), 500
        
    except Exception as e:
        print(f"上传测试数据错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

@app.route('/teacher/experiment/check-plagiarism', methods=['POST'])
def check_plagiarism():
    """
    查重模块接口
    根据实验ID，查找所有提交的pth模型文件，进行二进制查重并返回结果
    """
    try:
        # 获取当前登录用户
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                'code': 401,
                'message': '未登录或登录已过期'
            }), 401
        
        # 确保是教师用户
        user_type = current_user.user_type.value if isinstance(current_user.user_type, UserType) else current_user.user_type
        if user_type != 'teacher':
            return jsonify({
                'code': 403,
                'message': '只有教师可以进行查重'
            }), 403
        
        # 获取实验ID参数
        data = request.get_json()
        experiment_id = data.get('experiment_id')
        print(f"开始查重实验 ID: {experiment_id}")
        
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
        
        # 验证当前教师是否有权限查重该实验
        if experiment.teacher_id != current_user.user_id:
            return jsonify({
                'code': 403,
                'message': '您没有权限对此实验进行查重'
            }), 403
        
        # 获取该实验的所有提交记录
        submissions = Submission.query.filter_by(
            experiment_id=experiment_id
        ).all()
        
        if not submissions:
            return jsonify({
                'code': 400,
                'message': '该实验暂无提交记录'
            }), 400
        
        print(f"开始查重，共有{len(submissions)}个提交记录")
        
        # 创建一个字典，用于存储每个学生的pth文件路径
        student_pth_files = {}
        
        # 查找每个提交中的pth文件
        for submission in submissions:
            student_id = submission.student_id
            student_folder_path = submission.file_path
            
            if not os.path.exists(student_folder_path) or not os.path.isdir(student_folder_path):
                print(f"学生{student_id}提交文件夹不存在: {student_folder_path}")
                continue
            
            # 在提交文件夹中查找pth文件
            pth_files = []
            for root, dirs, files in os.walk(student_folder_path):
                for file in files:
                    if file.endswith('.pth'):
                        pth_files.append(os.path.join(root, file))
            
            if pth_files:
                # 如果找到多个pth文件，使用第一个
                student_pth_files[student_id] = pth_files[0]
                print(f"找到学生{student_id}的pth文件: {pth_files[0]}")
            else:
                print(f"学生{student_id}的提交中没有找到pth文件")
        
        # 如果没有找到任何pth文件，返回错误
        if not student_pth_files:
            return jsonify({
                'code': 400,
                'message': '未找到任何pth文件进行查重'
            }), 400
        
        # 计算文件相似度的函数
        def calculate_similarity(file1, file2):
            try:
                # 读取文件二进制内容
                with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
                    content1 = f1.read()
                    content2 = f2.read()
                
                # 如果文件大小相差太多，相似度应该较低
                size1 = len(content1)
                size2 = len(content2)
                
                # 如果文件大小相差超过20%，降低基础相似度
                if abs(size1 - size2) > 0.2 * max(size1, size2):
                    base_similarity = 30  # 基础相似度降低
                else:
                    base_similarity = 50  # 文件大小相近，基础相似度较高
                
                # 比较文件头部和尾部（通常包含元数据和模型架构信息）
                # 头部比较 - 取前2KB
                head_size = min(2048, min(size1, size2))
                head1 = content1[:head_size]
                head2 = content2[:head_size]
                
                # 计算头部相似度 - 使用分块比较方法
                head_similarity = 0
                block_size = 64  # 64字节一个块
                for i in range(0, head_size, block_size):
                    block1 = head1[i:i+block_size]
                    block2 = head2[i:i+block_size]
                    # 计算块内相同字节的比例
                    if block1 == block2:
                        head_similarity += 1
                
                head_similarity = (head_similarity * block_size / head_size) * 100 if head_size > 0 else 0
                
                # 尾部比较 - 取后1KB
                tail_size = min(1024, min(size1, size2))
                tail1 = content1[-tail_size:] if size1 >= tail_size else content1
                tail2 = content2[-tail_size:] if size2 >= tail_size else content2
                
                # 计算尾部相似度
                tail_similarity = 0
                for i in range(0, tail_size, block_size):
                    block1 = tail1[i:i+block_size]
                    block2 = tail2[i:i+block_size]
                    if block1 == block2:
                        tail_similarity += 1
                
                tail_similarity = (tail_similarity * block_size / tail_size) * 100 if tail_size > 0 else 0
                
                # 抽样比较文件中间部分
                # 选择多个位置进行抽样比较
                samples = 10
                middle_similarity = 0
                
                for _ in range(samples):
                    # 随机选择一个位置，但避开头尾
                    min_pos = head_size
                    max_pos = min(size1, size2) - tail_size - block_size
                    
                    if max_pos <= min_pos:
                        # 文件太小，无法进行中间部分抽样
                        continue
                    
                    pos = random.randint(min_pos, max_pos)
                    sample1 = content1[pos:pos+block_size]
                    sample2 = content2[pos:pos+block_size]
                    
                    if sample1 == sample2:
                        middle_similarity += 1
                
                middle_similarity = (middle_similarity / samples) * 100
                
                # 计算总相似度 - 头部权重高，因为包含模型架构信息
                # 尾部权重次之，中间部分权重最低
                weighted_similarity = (head_similarity * 0.5) + (tail_similarity * 0.3) + (middle_similarity * 0.2)
                
                # 应用基础相似度调整
                final_similarity = base_similarity + (weighted_similarity * 0.5)
                
                # 确保相似度在0-100范围内
                final_similarity = max(0, min(100, final_similarity))
                
                print(f"文件相似度计算 - 大小相似度: {base_similarity}, 头部: {head_similarity:.2f}%, 尾部: {tail_similarity:.2f}%, 中间: {middle_similarity:.2f}%, 最终: {final_similarity:.2f}%")
                
                return final_similarity
            except Exception as e:
                print(f"计算文件相似度时出错: {str(e)}")
                return 0
        
        # 获取风险级别
        def get_risk_level(similarity):
            if similarity >= 80:
                return "极高风险"
            elif similarity >= 70:
                return "高风险"
            elif similarity >= 60:
                return "中等风险"
            else:
                return "低风险"
        
        # 存储查重结果
        plagiarism_results = []
        
        # 对每个学生的pth文件进行两两比较
        student_ids = list(student_pth_files.keys())
        for i, student_id1 in enumerate(student_ids):
            # 获取学生信息
            student1 = User.query.get(student_id1)
            student_name1 = student1.real_name or student1.username if student1 else f"学生ID: {student_id1}"
            
            # 存储该学生与其他学生的最高相似度
            highest_similarity = 0
            highest_similarity_with = None
            highest_similarity_name = None
            
            # 存储所有相似度结果，用于调试
            all_similarities = []
            
            for j, student_id2 in enumerate(student_ids):
                if i == j:  # 跳过自己
                    continue
                
                # 获取学生2的信息
                student2 = User.query.get(student_id2)
                student_name2 = student2.real_name or student2.username if student2 else f"学生ID: {student_id2}"
                
                # 计算两个文件的相似度
                similarity = calculate_similarity(student_pth_files[student_id1], student_pth_files[student_id2])
                
                # 记录所有相似度结果
                all_similarities.append({
                    "with_student_id": student_id2,
                    "with_student_name": student_name2,
                    "similarity": similarity
                })
                
                # 如果相似度更高，更新记录
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    highest_similarity_with = student_id2
                    highest_similarity_name = student_name2
            
            # 输出调试信息
            print(f"学生 {student_name1} (ID: {student_id1}) 的相似度结果:")
            for sim in sorted(all_similarities, key=lambda x: x['similarity'], reverse=True)[:3]:
                print(f"  - 与 {sim['with_student_name']} (ID: {sim['with_student_id']}) 的相似度: {sim['similarity']:.2f}%")
            
            # 添加到结果列表
            plagiarism_results.append({
                'student_id': student_id1,
                'student_name': student_name1,
                'highest_similarity': round(highest_similarity, 2),
                'similar_with_id': highest_similarity_with,
                'similar_with_name': highest_similarity_name,
                'risk_level': get_risk_level(highest_similarity)
            })
        
        # 按相似度降序排序
        plagiarism_results.sort(key=lambda x: x['highest_similarity'], reverse=True)
        
        # 更新学生成绩，将查重结果作为评论添加到成绩中
        for result in plagiarism_results:
            student_id = result['student_id']
            similarity = result['highest_similarity']
            similar_with = result['similar_with_name']
            
            # 查找该学生的提交记录
            submission = Submission.query.filter_by(
                experiment_id=experiment_id,
                student_id=student_id
            ).first()
            
            if submission:
                # 查找是否已有成绩
                grade = Grade.query.filter_by(submission_id=submission.submission_id).first()
                
                if grade:
                    # 更新成绩评论，添加查重信息
                    grade.comment = f"查重结果: 与{similar_with}的相似度为{similarity}%"
                    db.session.commit()
                    print(f"已更新学生{student_id}的成绩评论，添加查重信息")
        
        return jsonify({
            'code': 200,
            'message': '查重完成',
            'data': {
                'checked_count': len(plagiarism_results),
                'total_submissions': len(submissions),
                'results': plagiarism_results
            }
        })
        
    except Exception as e:
        print(f"查重过程中出错: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

if __name__ == '__main__':
    run_app()

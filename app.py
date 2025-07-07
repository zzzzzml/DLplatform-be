from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import base64
import os
import uuid
from config import config
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# 加载配置
config_name = os.environ.get('FLASK_CONFIG') or 'default'
app.config.from_object(config[config_name])
config[config_name].init_app(app)

db = SQLAlchemy(app)

# 数据模型定义
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    user_type = db.Column(db.Enum('student', 'teacher'), nullable=True)
    real_name = db.Column(db.String(50), nullable=True)
    student_id = db.Column(db.String(20), nullable=True)
    profile_completed = db.Column(db.Boolean, nullable=True)
    class_id = db.Column(db.Integer, nullable=True)
    email = db.Column(db.String(100), nullable=True)

class Class(db.Model):
    __tablename__ = 'classes'
    class_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, nullable=False)

class Experiment(db.Model):
    __tablename__ = 'experiments'
    experiment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    publish_time = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    deadline = db.Column(db.TIMESTAMP, nullable=True)

class ExperimentAttachment(db.Model):
    __tablename__ = 'experiment_attachments'
    attachment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.experiment_id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    upload_time = db.Column(db.TIMESTAMP, default=datetime.utcnow)

# 创建上传文件夹
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 错误处理
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'code': 400, 'message': '请求参数错误'}), 400

@app.errorhandler(403)
def forbidden(error):
    return jsonify({'code': 403, 'message': '无权限访问'}), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({'code': 404, 'message': '资源不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'code': 500, 'message': '服务器内部错误'}), 500

# 学生端浏览实验要求接口
@app.route('/student/experiment/requirements', methods=['GET'])
def get_experiment_requirements():
    try:
        # 获取请求参数
        experiment_id = request.args.get('experiment_id')
        
        if not experiment_id:
            return jsonify({
                'code': 400,
                'message': '参数错误：实验ID不能为空'
            }), 400
        
        # 查询实验信息
        experiment = Experiment.query.get(experiment_id)
        if not experiment:
            return jsonify({
                'code': 404,
                'message': '实验不存在'
            }), 404
        
        # 查询附件信息
        attachments = ExperimentAttachment.query.filter_by(experiment_id=experiment_id).all()
        
        # 构建响应数据
        attachment_list = []
        for attachment in attachments:
            attachment_list.append({
                'attachment_id': attachment.attachment_id,
                'file_name': attachment.file_name,
                'file_size': attachment.file_size,
                'upload_time': attachment.upload_time.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        response_data = {
            'experiment_name': experiment.experiment_name,
            'description': experiment.description,
            'publish_time': experiment.publish_time.strftime('%Y-%m-%d %H:%M:%S'),
            'deadline': experiment.deadline.strftime('%Y-%m-%d %H:%M:%S') if experiment.deadline else None,
            'attachments': attachment_list
        }
        
        return jsonify({
            'code': 200,
            'message': '获取成功',
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误：{str(e)}'
        }), 500

#下载实验附件接口
@app.route('/download/attachment/<int:attachment_id>', methods=['GET'])
def download_attachment(attachment_id):
    attachment = ExperimentAttachment.query.get(attachment_id)
    if not attachment:
        return jsonify({'code': 404, 'message': '附件不存在'}), 404
    directory = os.path.dirname(attachment.file_path)
    filename = os.path.basename(attachment.file_path)
    return send_from_directory(directory, filename, as_attachment=True, download_name=attachment.file_name)

# 教师端发布实验附件接口
@app.route('/teacher/experiment/upload_attachment', methods=['POST'])
def upload_attachment():
    file = request.files.get('file')
    experiment_id = request.form.get('experiment_id', type=int)
    if not file:
        return jsonify({'code': 400, 'message': '未选择文件'}), 400
    if not file.filename:
        return jsonify({'code': 400, 'message': '文件名不能为空'}), 400
    if not experiment_id:
        return jsonify({'code': 400, 'message': 'experiment_id不能为空'}), 400

    # 检查实验是否存在
    experiment = Experiment.query.get(experiment_id)
    if not experiment:
        return jsonify({'code': 404, 'message': '实验不存在'}), 404

    filename = secure_filename(file.filename)
    file_extension = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(save_path)
    file_size = os.path.getsize(save_path) // 1024  # KB

    attachment = ExperimentAttachment(
        experiment_id=experiment_id,
        file_name=filename,
        file_path=save_path,
        file_size=file_size
    )
    db.session.add(attachment)
    db.session.commit()
    return jsonify({
        'code': 200,
        'message': '上传成功',
        'data': {
            'attachment_id': attachment.attachment_id,
            'file_name': attachment.file_name,
            'file_size': attachment.file_size,
            'upload_time': attachment.upload_time.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

#教师端发布实验接口
@app.route('/teacher/experiment/publish_with_attachment', methods=['POST'])
def publish_experiment_with_attachment():
    try:
        # 获取表单参数
        experiment_name = request.form.get('experiment_name')
        class_id = request.form.get('class_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        description = request.form.get('description')
        deadline = request.form.get('deadline')
        file = request.files.get('file')

        # 参数校验
        if not experiment_name:
            return jsonify({'code': 400, 'message': '实验名称不能为空'}), 400
        if not class_id:
            return jsonify({'code': 400, 'message': '班级ID不能为空'}), 400
        if not teacher_id:
            return jsonify({'code': 400, 'message': '教师ID不能为空'}), 400
        if not description:
            return jsonify({'code': 400, 'message': '实验描述不能为空'}), 400
        if not file or not file.filename:
            return jsonify({'code': 400, 'message': '未选择文件'}), 400

        # 检查班级是否存在
        class_obj = Class.query.get(class_id)
        if not class_obj:
            return jsonify({'code': 404, 'message': '班级不存在'}), 404

        # 处理截止时间
        deadline_time = None
        if deadline:
            try:
                deadline_time = datetime.strptime(deadline, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({'code': 400, 'message': '截止时间格式不正确'}), 400

        # 插入实验表
        experiment = Experiment(
            experiment_name=experiment_name,
            class_id=class_id,
            teacher_id=teacher_id,
            description=description,
            deadline=deadline_time
        )
        db.session.add(experiment)
        db.session.flush()  # 获取 experiment_id

        # 保存附件
        filename = secure_filename(file.filename)
        file_extension = os.path.splitext(filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        save_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(save_path)
        file_size = os.path.getsize(save_path) // 1024  # KB

        # 插入附件表
        attachment = ExperimentAttachment(
            experiment_id=experiment.experiment_id,
            file_name=filename,
            file_path=save_path,
            file_size=file_size
        )
        db.session.add(attachment)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '发布成功',
            'data': {
                'experiment_id': experiment.experiment_id,
                'attachment_id': attachment.attachment_id,
                'file_name': attachment.file_name,
                'file_size': attachment.file_size,
                'upload_time': attachment.upload_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'服务器错误：{str(e)}'}), 500

# 测试接口
@app.route('/')
def hello_world():
    return 'hello world'

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

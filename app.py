from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql

# 注册pymysql作为MySQL的驱动
pymysql.install_as_MySQLdb()

# 配置类
class Config:
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = 'mysql://root:root@localhost/dlplatform'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# 用户模型定义 - 修改为匹配数据库表结构
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # 改为user_id
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)  # 数据库中是VARCHAR(50)
    real_name = db.Column(db.String(50), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # student, teacher
    student_id = db.Column(db.String(20), nullable=True)  # 学号
    profile_completed = db.Column(db.Boolean, default=False)
    class_id = db.Column(db.Integer, nullable=True)  # 所在班级ID
    email = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)  # 改为created_at
    
    def __repr__(self):
        return f'<User {self.username}>'

@app.route('/')
def hello_world():
    return 'Hello, Flask!'

@app.route('/register', methods=['POST'])
def register():
    try:
        # 获取请求数据
        data = request.get_json()
        
        # 检查必要字段
        required_fields = ['username', 'password', 'user_type', 'realname', 'email']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': 400,
                    'message': f'缺少必要字段: {field}'
                }), 400
        
        # 检查用户名是否存在
        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({
                'code': 400,
                'message': '用户名已存在'
            }), 400
        
        # 检查邮箱是否存在
        existing_email = User.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({
                'code': 400,
                'message': '邮箱已被使用'
            }), 400
        
        # 创建新用户
        new_user = User(
            username=data['username'],
            password=data['password'],
            real_name=data['realname'],
            email=data['email'],
            user_type=data['user_type']
        )
        
        # 添加到数据库
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'code': 200,
            'message': '注册成功'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'code': 500,
            'message': f'注册失败: {str(e)}'
        }), 500

# 不需要创建表，因为表已经存在
# with app.app_context():
#    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

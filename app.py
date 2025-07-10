from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/dlplatform'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 班级表模型
class ClassInfo(db.Model):
    __tablename__ = 'classes'
    class_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, nullable=False)

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
        new_class = ClassInfo(class_name=class_name, teacher_id=teacher_id)
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

@app.route('/')
def hello_world():
    return 'Hello, Flask!'

if __name__ == '__main__':
    app.run(debug=True)

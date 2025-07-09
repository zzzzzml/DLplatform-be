from flask import Flask, request, jsonify
import pymysql

app = Flask(__name__)

# 简单的CORS支持
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        db='dlplatform',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 学生端获取成绩信息
@app.route('/student/experiment/scores', methods=['POST'])
def student_experiment_scores():
    data = request.get_json()
    experiment_id = data.get('experiment_id')
    if not experiment_id:
        return jsonify({"code": 400, "message": "experiment_id is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
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


if __name__ == '__main__':
    app.run(debug=True)
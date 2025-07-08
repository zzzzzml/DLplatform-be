from flask import Flask, request, jsonify
import pymysql

app = Flask(__name__)

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        db='dlplatform',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route('/api/experiment/scores', methods=['POST'])
def get_experiment_scores():
    data = request.get_json()
    experiment_id = data.get('experiment_id')
    if not experiment_id:
        return jsonify({'error': 'experiment_id is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """
        SELECT 
            u.user_id AS id,
            u.real_name AS name,
            c.class_name,
            g.score
        FROM grades g
        JOIN users u ON g.student_id = u.user_id
        JOIN classes c ON u.class_id = c.class_id
        WHERE g.experiment_id = %s
        ORDER BY g.score DESC
    """
    cursor.execute(sql, (experiment_id,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)
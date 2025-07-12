import sqlite3
import os

# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(current_dir, 'instance', 'dlplatform.db')

print(f"数据库路径: {db_path}")
print(f"数据库文件是否存在: {os.path.exists(db_path)}")

try:
    # 连接到SQLite数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("\n数据库中的表:")
    for table in tables:
        print(f"- {table[0]}")
    
    # 检查submissions表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='submissions'")
    if cursor.fetchone():
        # 获取submissions表中的所有数据
        cursor.execute("SELECT * FROM submissions")
        submissions = cursor.fetchall()
        
        print("\nSubmissions表中的数据:")
        if submissions:
            # 获取列名
            cursor.execute("PRAGMA table_info(submissions)")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"列名: {columns}")
            
            # 打印每一行数据
            for submission in submissions:
                print(submission)
            print(f"\n总计 {len(submissions)} 条记录")
        else:
            print("表中没有数据")
    else:
        print("\nSubmissions表不存在")
    
    # 关闭连接
    conn.close()
    
except Exception as e:
    print(f"发生错误: {e}") 
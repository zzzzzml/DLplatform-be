#!/usr/bin/env python3
"""
Flask应用启动脚本
"""

import os
import sys
from app import app, db

def create_app():
    """创建Flask应用实例"""
    return app

def init_database():
    """初始化数据库"""
    try:
        with app.app_context():
            db.create_all()
            print("数据库表创建成功！")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    # 检查环境变量
    if not os.environ.get('FLASK_CONFIG'):
        os.environ['FLASK_CONFIG'] = 'development'
    
    print(f"使用配置: {os.environ.get('FLASK_CONFIG')}")
    
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
    main() 
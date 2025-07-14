FROM m.daocloud.io/docker.io/library/python:3.8.20

WORKDIR /flask-app

# 先单独拷贝requirements.txt并安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 然后拷贝其他文件
COPY . .

EXPOSE 5000
CMD ["python","app.py"]


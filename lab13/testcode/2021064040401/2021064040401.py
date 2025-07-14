# 第一步加载库
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.data import DataLoader, TensorDataset

def evaluate_model():
    # 第二步设置设置模型架构，模型名统一为model
    class LeNet(nn.Module):
        def __init__(self):
            super().__init__()
            # 卷积层1：输入通道1，输出通道6，卷积核5x5
            self.conv1 = nn.Conv2d(1, 6, kernel_size=5)
            # 平均池化层：2x2窗口，步长2
            self.pool1 = nn.AvgPool2d(kernel_size=2, stride=2)
            # 卷积层2：输入通道6，输出通道16，卷积核5x5
            self.conv2 = nn.Conv2d(6, 16, kernel_size=5)
            # 平均池化层：2x2窗口，步长2
            self.pool2 = nn.AvgPool2d(kernel_size=2, stride=2)
            # 全连接层1：输入16*4*4=256，输出120
            self.fc1 = nn.Linear(16 * 4 * 4, 120)
            # 全连接层2：输入120，输出84
            self.fc2 = nn.Linear(120, 84)
            # 输出层：输入84，输出10（对应10个数字类别）
            self.fc3 = nn.Linear(84, 10)

        def forward(self, x):
            # 第一层卷积+池化+激活
            x = torch.relu(self.conv1(x))
            x = self.pool1(x)
            # 第二层卷积+池化+激活
            x = torch.relu(self.conv2(x))
            x = self.pool2(x)
            # 展平特征图
            x = x.view(x.size(0), -1)
            # 全连接层
            x = torch.relu(self.fc1(x))
            x = torch.relu(self.fc2(x))
            x = self.fc3(x)
            return x


    # 实例化模型
    model = LeNet()
    #第三步加载最优模型参数
    #加载最佳模型权重，修改为个人"学号.pth"
    model.load_state_dict(torch.load('2021064040401.pth'))


    # 第四步加载测试数据，测试数据文件固定为“../../data”，请根据实验要求中测试数据格式加载为test_loader，
    # create_testloader内代码可以根据自己的需求可以对测试数据进行相应增强
    def create_testloader(image_path, label_path, batch_size=64):
        # 加载数据
        with open(image_path, 'rb') as f_img, open(label_path, 'rb') as f_label:
            images = np.frombuffer(f_img.read(), dtype=np.uint8, offset=16).copy().reshape(-1, 28, 28)
            labels = np.frombuffer(f_label.read(), dtype=np.uint8, offset=8).copy()

        # 转换为张量
        images = torch.from_numpy(images).float().unsqueeze(1) / 255.0
        labels = torch.from_numpy(labels).long()

        # 构建DataLoader
        dataset = TensorDataset(images, labels)
        return DataLoader(dataset, batch_size=batch_size, shuffle=False)


    # 不可修改
    testloader = create_testloader(
        image_path='../../testdata/t10k-images-idx3-ubyte',
        label_path='../../testdata/t10k-labels-idx1-ubyte'
    )
    # 第五步模型评估，测试正确率不可修改
    model.eval()

    # 在测试集上进行最终评估
    test_correct = 0
    test_total = 0
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for images, labels in testloader:
            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            test_total += labels.size(0)
            test_correct += (predicted == labels).sum().item()
            all_preds.extend(predicted.numpy())
            all_labels.extend(labels.numpy())
        df = pd.DataFrame(all_preds)
        df.to_csv('all_preds.csv', index=False)
if __name__ == '__main__':
    evaluate_model()
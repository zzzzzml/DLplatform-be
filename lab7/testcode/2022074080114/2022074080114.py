import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
import pandas as pd
#第二步设置设置模型架构，**必须修改，模型名统一为model
def evaluate_model():
    model =nn.Sequential(
        nn.Conv2d(1, 6, kernel_size=5, padding=2), nn.Sigmoid(),
        nn.AvgPool2d(kernel_size=2, stride=2),
        nn.Conv2d(6, 16, kernel_size=5), nn.Sigmoid(),
        nn.AvgPool2d(kernel_size=2, stride=2),
        nn.Flatten(),
        nn.Linear(16 * 5 * 5, 120), nn.Sigmoid(),
        nn.Linear(120, 84), nn.Sigmoid(),
        nn.Linear(84, 10),
        nn.Softmax())
    #第三步加载最优模型参数
    #加载最佳模型权重，**必须修改， 修改为个人"学号.pth"
    model.load_state_dict(torch.load('2022074080114.pth'))


    # 第四步加载测试数据，测试数据文件固定为“../../data”，请根据实验要求中测试数据格式加载为test_loader，
    # create_testloader内代码可以根据自己的需求可以对测试数据进行相应增强，**可以修改
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


    # **不可修改
    testloader = create_testloader(
        image_path='../../testdata/t10k-images-idx3-ubyte',
        label_path='../../testdata/t10k-labels-idx1-ubyte'
    )
    # 第五步模型评估，测试正确率，**不可修改
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
# 第一步加载库
import torch
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
import pandas as pd
def evaluate_model():
    # 第二步设置设置模型架构，模型统一实例化为model
    class Net(torch.nn.Module):
        def __init__(self):
            super(Net, self).__init__()
            self.model = torch.nn.Sequential(
                torch.nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, stride=1, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(kernel_size=2, stride=2),

                torch.nn.Conv2d(in_channels=16, out_channels=32, kernel_size=3, stride=1, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(kernel_size=2, stride=2),

                torch.nn.Conv2d(in_channels=32, out_channels=64, kernel_size=3, stride=1, padding=1),
                torch.nn.ReLU(),

                torch.nn.Flatten(),
                torch.nn.Linear(in_features=7 * 7 * 64, out_features=128),
                torch.nn.ReLU(),
                torch.nn.Linear(in_features=128, out_features=10),
                torch.nn.Softmax(dim=1)
            )

        def forward(self, input):
            output = self.model(input)
            return output


    # 实例化模型
    model = Net()
    # 第三步加载最优模型参数
    # 加载最佳模型权重，修改为个人"学号.pth"
    model.load_state_dict(torch.load('./2022224110907.pth'))


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
    df=pd.DataFrame(all_preds)
    df.to_csv('all_preds.csv', index=False)
if __name__ == '__main__':
    evaluate_model()
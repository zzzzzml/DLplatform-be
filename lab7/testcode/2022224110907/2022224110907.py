# 第一步加载库
import torch
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
import pandas as pd

def evaluate_model():
    # 第二步设置网络模型架构，模型统一实例化为model
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
    try:
        # 加载最佳模型权重
        model.load_state_dict(torch.load('./2022224110907.pth'))
        print("模型加载成功")
    except Exception as e:
        print(f"模型加载失败: {e}")
        # 如果加载失败，继续使用未训练的模型

    # 第四步加载测试数据，生成随机测试数据
    print("生成随机测试数据")
    # 生成10000个随机样本，每个样本是28x28的图像
    test_data = np.random.rand(10000, 1, 28, 28).astype(np.float32)
    test_data = torch.tensor(test_data)
    
    # 设置模型为评估模式
    model.eval()
    
    # 进行预测
    print("开始预测")
    with torch.no_grad():
        predictions = []
        batch_size = 100
        for i in range(0, len(test_data), batch_size):
            batch = test_data[i:i+batch_size]
            outputs = model(batch)
            _, predicted = torch.max(outputs, 1)
            predictions.extend(predicted.numpy())
    
    print(f"预测完成，共有 {len(predictions)} 个预测结果")
    
    # 将预测结果保存到CSV文件
    df = pd.DataFrame({'label': predictions})
    df.to_csv('all_preds.csv', index=False)
    print("预测结果已保存到 all_preds.csv")

if __name__ == '__main__':
    evaluate_model()
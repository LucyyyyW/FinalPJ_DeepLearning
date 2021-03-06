'''Train CIFAR10 with PyTorch.'''
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
from tensorboardX import SummaryWriter
# from  torch.utils.tensorboard import SummaryWriter

import torchvision
import torchvision.transforms as transforms

import os
import argparse

from models import *
from models.hybrid import *
from utils import progress_bar
from vit_pytorch import ViT
from thop import profile

# from sklearn.metrics import accuracy_score, f1_score

parser = argparse.ArgumentParser(description='PyTorch CIFAR10 Training')
parser.add_argument('--lr', default=0.01, type=float, help='learning rate')
parser.add_argument('--resume', '-r', action='store_true',
                    help='resume from checkpoint')
parser.add_argument('--cuda', default=0, type=int, help='gpu id')
parser.add_argument('--batch_size', default=256, type=int)
parser.add_argument('--model', default='hybrid', type=str)
parser.add_argument('--net', default='ResNet50', choices=['ResNet50','ResNet152'], type=str, help='CNN model')
parser.add_argument('--depth', default=4, type=int)
parser.add_argument('--heads', default=8, type=int)
args = parser.parse_args()

device = 'cuda:{}'.format(args.cuda) if torch.cuda.is_available() else 'cpu'
cudnn.benchmark = True
best_acc = 0  # best test accuracy
start_epoch = 0  # start from epoch 0 or last checkpoint epoch

# Data
print('==> Preparing data..')
transform_train = transforms.Compose([
    # transforms.RandomCrop(32, padding=4),
    # transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])

transform_test = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])

trainset = torchvision.datasets.CIFAR10(
    root='./data', train=True, download=True, transform=transform_train)
trainloader = torch.utils.data.DataLoader(
    trainset, batch_size=args.batch_size, shuffle=True, num_workers=2)

testset = torchvision.datasets.CIFAR10(
    root='./data', train=False, download=True, transform=transform_test)
testloader = torch.utils.data.DataLoader(
    testset, batch_size=100, shuffle=False, num_workers=2)

classes = ('plane', 'car', 'bird', 'cat', 'deer',
           'dog', 'frog', 'horse', 'ship', 'truck')

# Model
print('==> Building model --', args.model)
inputs=torch.randn(1, 3, 32, 32)
if args.model == 'hybrid':
    net = hybrid(n_blocks=[2,2,1], patch_size=1, depth=args.depth, head=args.heads)
    flops1, params1 = profile(net, (inputs,),verbose=False)
    print('Total parameters: ',params1)
    print('Total flops: ',flops1)
elif args.model == 'CNN':
    # net = VGG('VGG19')
    # net = ResNet18()
    # net = PreActResNet18()
    # net = GoogLeNet()
    # net = DenseNet121()
    # net = ResNeXt29_2x64d()
    # net = MobileNet()
    # net = MobileNetV2()
    # net = DPN92()
    # net = ShuffleNetG2()
    # net = SENet18()
    # net = ShuffleNetV2(1)
    # net = EfficientNetB0()
    # net = RegNetX_200MF()
    # net = SimpleDLA()
    if args.net == 'ResNet152':
        net = ResNet152()
    else:
        net = ResNet50()
    flops1, params1 = profile(net, (inputs,),verbose=False)
    print('Total parameters: ',params1)
    print('Total flops: ',flops1)

# total_params = sum(p.numel() for p in net.parameters() if p.requires_grad)

# print('Total parameters: ', total_params)
print(net)
net = net.to(device)


if args.resume:
    # Load checkpoint.
    print('==> Resuming from checkpoint..')
    assert os.path.isdir('checkpoint'), 'Error: no checkpoint directory found!'
    checkpoint = torch.load('./checkpoint/ckpt.pth')
    net.load_state_dict(checkpoint['net'])
    best_acc = checkpoint['acc']
    start_epoch = checkpoint['epoch']


if not os.path.exists('log/'+args.model+'null'):
    os.makedirs('log/'+args.model+'null')
writer = SummaryWriter(log_dir='log/'+args.model+'null')

criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(net.parameters(), lr=args.lr,
                      momentum=0.9, weight_decay=5e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=200)


# Training
def train(epoch):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    correct = 0
    total = 0
    for batch_idx, (inputs, targets) in enumerate(trainloader):
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        outputs = net(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

        progress_bar(batch_idx, len(trainloader), 'Loss: %.3f | Acc: %.3f%% (%d/%d)'
                     % (train_loss/(batch_idx+1), 100.*correct/total, correct, total))
        
    writer.add_scalar('Train loss', train_loss/(batch_idx+1), epoch)

def test(epoch):
    global best_acc
    net.eval()
    test_loss = 0
    correct = 0
    total = 0
    # class_sum = torch.zeros_like(10)
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            # class_sum += 
            

            progress_bar(batch_idx, len(testloader), 'Loss: %.3f | Acc: %.3f%% (%d/%d)'
                         % (test_loss/(batch_idx+1), 100.*correct/total, correct, total))
    
    # Save checkpoint
    acc = 100.*correct/total
    loss = 100.*test_loss/total
    writer.add_scalar('Test accuracy', acc, epoch)
    writer.add_scalar('Test loss', loss, epoch)
    if acc > best_acc:
        print('Saving..')
        state = {
            'net': net.state_dict(),
            'acc': acc,
            'epoch': epoch,
        }
        ck_path = 'checkpoint_null'
        if not os.path.isdir(ck_path):
            os.mkdir(ck_path)
        torch.save(state, './checkpoint_null/{}.pth'.format(args.model))
        best_acc = acc


for epoch in range(start_epoch, start_epoch+200):
    train(epoch)
    test(epoch)
    scheduler.step()

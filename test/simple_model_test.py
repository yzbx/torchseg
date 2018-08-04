# -*- coding: utf-8 -*-

import torch
from torch.nn import Module,Conv2d
from torch.nn import functional as F
from torch.autograd import Variable
import torch.utils.data as TD
import random
from dataset.dataset_generalize import dataset_generalize,get_dataset_generalize_config
from easydict import EasyDict as edict

class simple_net(Module):
    def __init__(self):
        super(simple_net, self).__init__()
        self.conv1 = Conv2d(in_channels=3, out_channels=10,
                            kernel_size=3, stride=2, padding=1, bias=True)
        self.conv2 = Conv2d(in_channels=10, out_channels=20,
                            kernel_size=3, stride=1, padding=1, bias=True)

    def forward(self, x):
        inp_shape = x.shape[2:]

        # H, W -> H/2, W/2
        x = self.conv1(x)
        x = self.conv2(x)

        # H/2, W/2 -> H/4, W/4
        x = F.max_pool2d(x, kernel_size=3, stride=2, padding=1)

        x = F.upsample(x, size=inp_shape, mode='bilinear',align_corners=True)

        return x
    
    def train(self,args,trainloader):
        # set model to train mode
        super(simple_net,self).train()
        
        # use gpu memory
        device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.to(device)
        optimizer = torch.optim.Adam(self.parameters(), lr = 0.0001)
#        loss_fn=random.choice([torch.nn.NLLLoss(),torch.nn.CrossEntropyLoss()])
        loss_fn=torch.nn.CrossEntropyLoss()
        for epoch in range(args.n_epoch):
            for i, (images, labels) in enumerate(trainloader):
                images = Variable(images.to(device).float())
                labels = Variable(labels.to(device).long())
                
                optimizer.zero_grad()
                outputs = self.forward(images)
                
#                print(outputs.shape,labels.shape)
    
                loss = loss_fn(input=outputs, target=labels)
    
                loss.backward()
                optimizer.step()
                
                if (i+1) % 20 == 0:
                    print("Epoch [%d/%d] Loss: %.4f" % (epoch+1, args.n_epoch, loss.data))
                    
if __name__ == '__main__':
    config=edict()
    config.root_path='/media/sdb/CVDataset/ObjectSegmentation/archives/Cityscapes_archives'
    config.cityscapes_split=random.choice(['test','val','train'])
    config.resize_shape=(224,224)
    config=get_dataset_generalize_config(config,'Cityscapes')
    dataset=dataset_generalize(config)
    loader=TD.DataLoader(dataset=dataset,batch_size=2, shuffle=True,drop_last=False)
    args=edict()
    args.n_epoch=3
    net=simple_net()
    net.train(args,loader)
    
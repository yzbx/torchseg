# -*- coding: utf-8 -*-

import torch
import torch.nn as TN
from torch.nn import functional as F
from torch.autograd import Variable
import torch.utils.data as TD
import random
from dataset.cityscapes import cityscapes
from models.backbone import backbone
from utils.metrics import runningScore,get_scores
from utils.torch_tools import freeze_layer
from models.upsample import upsample_duc,upsample_bilinear,transform_psp
from easydict import EasyDict as edict
import numpy as np
from tqdm import tqdm
from tensorboardX import SummaryWriter
import time
import math
import os

class pspnet(TN.Module):
    def __init__(self,config):
        super(pspnet,self).__init__()
        self.config=config
        self.name=self.__class__.__name__
        self.backbone=backbone(config.model)
        
        if hasattr(self.config.model,'backbone_lr_ratio'):
            backbone_lr_raio=self.config.model.backbone_lr_ratio
            if backbone_lr_raio==0:
                freeze_layer(self.backbone)
        
        self.upsample_type = self.config.model.upsample_type
        self.upsample_layer = self.config.model.upsample_layer
        self.class_number = self.config.model.class_number
        self.input_shape = self.config.model.input_shape
        self.dataset_name=self.config.dataset.name
        if hasattr(self.config,'ignore_index'):
            self.ignore_index=self.config.ignore_index
        else:
            self.ignore_index = 0
        
#        self.midnet_type = self.config.model.midnet_type
        self.midnet_pool_sizes=self.config.model.midnet_pool_sizes
        self.midnet_scale=self.config.model.midnet_scale
        
        self.midnet_in_channels=self.backbone.get_feature_map_channel(self.upsample_layer)
        self.midnet_out_channels=self.config.model.midnet_out_channels
        self.midnet_out_size=self.backbone.get_feature_map_size(self.upsample_layer,self.input_shape[0:2])
        
        self.midnet=transform_psp(self.midnet_pool_sizes,
                                  self.midnet_scale,
                                  self.midnet_in_channels,
                                  self.midnet_out_channels,
                                  self.midnet_out_size)
        
        # psp net will output channels with 2*self.midnet_out_channels
        if self.upsample_type=='duc':
            r=2**self.upsample_layer
            self.decoder=upsample_duc(2*self.midnet_out_channels,self.class_number,r)
        elif self.upsample_type=='bilinear':
            self.decoder=upsample_bilinear(2*self.midnet_out_channels,self.class_number,self.input_shape[0:2])
        else:
            assert False,'unknown upsample type %s'%self.upsample_type


    def forward(self, x):
        feature_map=self.backbone.forward(x,self.upsample_layer)
        feature_mid=self.midnet(feature_map)
        x=self.decoder(feature_mid)        

        return x
    
    def get_optim(self,args):
        if hasattr(args,'lr'):
            lr=args.lr
        else:
            lr=0.0001
        
        if hasattr(args,'optim'):
            if args.optim=='adam':
                optimizer = torch.optim.Adam([p for p in self.parameters() if p.requires_grad], lr = lr)
            elif args.optim in ['sgd','sgd_simple']:
                #lr=1e-2 / math.sqrt(16 / args.batch_size)
                lr=lr / math.sqrt(16 / args.batch_size)
                optimizer = torch.optim.SGD([p for p in self.parameters() if p.requires_grad],
                                             lr=lr, momentum=0.9, nesterov=True)
            elif args.optim=='sgd_complex':
                
                #lr=1e-2 / math.sqrt(16 / args.batch_size)
                lr=lr / math.sqrt(16 / args.batch_size)
                optimizer = torch.optim.SGD([
                        {'params': [param for name, param in self.named_parameters() if param.requires_grad and name[-4:] == 'bias'],
                         'lr': 2 *lr},
                        {'params': [param for name, param in self.named_parameters() if param.requires_grad and name[-4:] != 'bias'],
                         'lr': lr, 'weight_decay': 1e-4}
                    ], momentum=0.9, nesterov=True)
            else:
                assert False,'unknonw optimizer type %s'%args.optim
        else:
            optimizer = torch.optim.Adam([p for p in self.parameters() if p.requires_grad], lr = 0.0001)
        
        return optimizer
    
    def do_train_or_val(self,args,trainloader=None,valloader=None):
        # use gpu memory
        self.cuda()
        self.backbone.model.cuda()
        optimizer = self.get_optim(args)
#        loss_fn=random.choice([torch.nn.NLLLoss(),torch.nn.CrossEntropyLoss()])
        if hasattr(args,'ignore_index'):
            if args.ignore_index:
                loss_fn=torch.nn.CrossEntropyLoss(ignore_index=self.ignore_index)
            else:
                loss_fn=torch.nn.CrossEntropyLoss()
        else:
            loss_fn=torch.nn.CrossEntropyLoss()
        
        # metrics
        running_metrics = runningScore(self.class_number)
        
        time_str = time.strftime("%Y-%m-%d___%H-%M-%S", time.localtime())
        log_dir=os.path.join(args.log_dir,self.name,self.dataset_name,args.note,time_str)
        checkpoint_path=os.path.join(log_dir,"{}_{}_best_model.pkl".format(self.name, self.dataset_name))
        os.makedirs(log_dir,exist_ok=True)
        writer = SummaryWriter(log_dir=log_dir)
        best_iou=0.0
        
        for epoch in range(args.n_epoch):
            if trainloader is not None:
                print('train: '+'.'*50)
                # set model to train mode
                self.train()
                n_step=len(trainloader)
                curr_iter=epoch*len(trainloader)
                max_iter=args.n_epoch*len(trainloader)
                for i, (images, labels) in enumerate(trainloader):
                    if hasattr(args,'optim') and args.optim=='sgd_complex':
                        lr=1e-2 / math.sqrt(16 / args.batch_size)
                        lr_decay=0.9
                        optimizer.param_groups[0]['lr'] = 2 * lr * (1 - curr_iter / max_iter) ** lr_decay
                        optimizer.param_groups[1]['lr'] = lr * (1 - curr_iter / max_iter) ** lr_decay
                    images = Variable(images.cuda().float())
                    labels = Variable(labels.cuda().long())
                    
                    optimizer.zero_grad()
                    outputs = self.forward(images)
                    loss = loss_fn(input=outputs, target=labels)
        
                    loss.backward()
                    optimizer.step()
                    
                    if (i+1) % 5 == 0:
                        print("Epoch [%d/%d] Step [%d/%d] Loss: %.4f" % (epoch+1, args.n_epoch, i, n_step, loss.data))
                        predicts = outputs.data.cpu().numpy().argmax(1)
                        trues = labels.data.cpu().numpy()
                        running_metrics.reset()
                        running_metrics.update(trues,predicts)
                        score, class_iou = running_metrics.get_scores()
                        for k, v in score.items():
                            print(k, v)
                        running_metrics.reset()
                        
                writer.add_scalar('train/loss', loss.data, epoch)
                writer.add_scalar('train/acc', score['Overall Acc: \t'], epoch)
                writer.add_scalar('train/iou', score['Mean IoU : \t'], epoch)
            
            if valloader is not None:
                print('validation: '+'.'*50)
                self.eval()
                running_metrics.reset()
                for i_val, (images_val, labels_val) in enumerate(valloader):
#                    with torch.no_grad:
                    images_val = Variable(images_val.cuda().float())
                    labels_val = Variable(labels_val.cuda().long())
        
                    outputs_val = self.forward(images_val)
                    predicts_val = outputs_val.data.cpu().numpy().argmax(1)
                    trues_val = labels_val.data.cpu().numpy()
                    running_metrics.update(trues_val, predicts_val)
                    
                    loss_val = loss_fn(input=outputs_val, target=labels_val)
        
                score, class_iou = running_metrics.get_scores()
                for k, v in score.items():
                    print(k, v)
                running_metrics.reset()
        
                if score['Mean IoU : \t'] >= best_iou:
                    best_iou = score['Mean IoU : \t']
                    state = {'epoch': epoch+1,
                             'miou': best_iou,
                             'model_state': self.state_dict(),
                             'optimizer_state' : optimizer.state_dict(),}
                    
                    torch.save(state, checkpoint_path)

                writer.add_scalar('val/loss', loss_val.data, epoch)
                writer.add_scalar('val/acc', score['Overall Acc: \t'], epoch)
                writer.add_scalar('val/iou', score['Mean IoU : \t'], epoch)
                
                if epoch % (1+args.n_epoch//10) == 0:
                    print('write image to tensorboard'+'.'*50)
                    idx=np.random.choice(predicts_val.shape[0])
                    writer.add_image('val/images',images_val[idx,:,:,:],epoch)
                    writer.add_image('val/predicts', torch.from_numpy(predicts_val[idx,:,:]), epoch)
                    writer.add_image('val/trues', torch.from_numpy(trues_val[idx,:,:]), epoch)
                    diff_img=(predicts_val[idx,:,:]==trues_val[idx,:,:]).astype(np.uint8)
                    writer.add_image('val/difference', torch.from_numpy(diff_img), epoch)
        
        writer.close()
        
if __name__ == '__main__':
    config=edict()
    config.model=edict()
    config.model.upsample_type='duc'
    config.model.upsample_layer=3
    config.model.class_number=20
    config.model.backbone_name='vgg16'
    config.model.layer_preference='last'
    config.model.input_shape=(224,224)
    
    config.model.midnet_pool_sizes=[6,3,2,1]
    config.model.midnet_scale=5
    config.model.midnet_out_channels=512
    
    config.dataset=edict()
    config.dataset.root_path='/media/sdb/CVDataset/ObjectSegmentation/archives/Cityscapes_archives'
    config.dataset.cityscapes_split=random.choice(['test','val','train'])
    config.dataset.resize_shape=(224,224)
    config.dataset.name='cityscapes'
    
    train_dataset=cityscapes(config.dataset,split='train')
    train_loader=TD.DataLoader(dataset=train_dataset,batch_size=32, shuffle=True,drop_last=True)
    
    val_dataset=cityscapes(config.dataset,split='val')
    val_loader=TD.DataLoader(dataset=val_dataset,batch_size=32, shuffle=True,drop_last=False)
    config.args=edict()
    config.args.n_epoch=300
    config.args.log_dir='/home/yzbx/tmp/logs/pytorch'
    config.args.note='image'
    config.args.batch_size=32
    net=pspnet(config)
    net.do_train_or_val(config.args,train_loader,val_loader)
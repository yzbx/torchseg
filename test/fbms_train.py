# -*- coding: utf-8 -*-

import torch.utils.data as td
from models.motion_stn import motion_stn, motion_net, stn_loss
from models.motionseg.motion_utils import (Metric_Acc,Metric_Mean,get_parser,
                                           get_default_config,get_dataset,
                                           get_other_config,get_model,
                                           poly_lr_scheduler)
from utils.torch_tools import init_writer
import torch.nn.functional as F
import os
import torch
import time
import torchsummary
import sys
from tqdm import trange,tqdm

if __name__ == '__main__':
    parser=get_parser()
    args = parser.parse_args()
    
    config=get_default_config()
    
    if args.net_name=='motion_psp':
        if args.use_none_layer is False or args.upsample_layer<=3:
            min_size=30*config.psp_scale*2**config.upsample_layer
        else:
            min_size=30*config.psp_scale*2**3
            
        config.input_shape=[min_size,min_size]
    
    sort_keys=sorted(list(config.keys()))
    for key in sort_keys:
        if hasattr(args,key):
            print('{} = {} (default: {})'.format(key,args.__dict__[key],config[key]))
            config[key]=args.__dict__[key]
        else:
            print('{} : (default:{})'.format(key,config[key]))
    
    for key in args.__dict__.keys():
        if key not in config.keys():
            print('{} : unused keys {}'.format(key,args.__dict__[key]))
    
    # update config according to basic config
    config=get_other_config(config)
    
    if args.app=='dataset':
        for split in ['train','val']:
            xxx_dataset=get_dataset(config,split)                
            dataset_size=len(xxx_dataset)
            for idx in range(dataset_size):
                xxx_dataset.__getitem__(idx)
        sys.exit(0)
    
    
    if config['net_name'] in ['motion_stn','motion_net']:
        model=globals()[config['net_name']]() 
    else:
        model=get_model(config)
    
    # support for cpu/gpu
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    
    if args.app=='summary':
        torchsummary.summary(model, ((3, config.input_shape[0], config.input_shape[1]),
                                     (3, config.input_shape[0], config.input_shape[1])))
        sys.exit(0)
        
    dataset_loaders={}
    for split in ['train','val']:
        xxx_dataset=get_dataset(config,split)
        batch_size=args.batch_size if split=='train' else 1
        xxx_loader=td.DataLoader(dataset=xxx_dataset,batch_size=batch_size,shuffle=True,drop_last=False,num_workers=2)
        dataset_loaders[split]=xxx_loader
    
    time_str = time.strftime("%Y-%m-%d___%H-%M-%S", time.localtime())
    log_dir = os.path.join(config['log_dir'], config['net_name'],
                           config['dataset'], config['note'], time_str)
    checkpoint_path = os.path.join(log_dir, 'model-last-%d.pkl' % config['epoch'])
    
    writer=init_writer(config,log_dir)
    
    seg_loss_fn=torch.nn.CrossEntropyLoss(ignore_index=255)
    
    optimizer_params = [{'params': [p for p in model.parameters() if p.requires_grad]}]
    
    if config.optimizer=='adam':
        optimizer = torch.optim.Adam(
                    optimizer_params, lr=config['init_lr'], amsgrad=False)
    else:
        assert config.init_lr>1e-3
        optimizer = torch.optim.SGD(
                    optimizer_params, lr=config['init_lr'], momentum=0.9, weight_decay=1e-4)
    
    metric_acc=Metric_Acc()
    metric_stn_loss=Metric_Mean()
    metric_mask_loss=Metric_Mean()
    metric_total_loss=Metric_Mean()
    
    tqdm_epoch = trange(config['epoch'], desc='{} epochs'.format(config.note), leave=True)
    for epoch in tqdm_epoch:
        for split in ['train','val']:
            if split=='train':
                model.train()
            else:
                model.eval()
                
            metric_acc.reset()
            metric_stn_loss.reset()
            metric_mask_loss.reset()
            metric_total_loss.reset()
            
            tqdm_step = tqdm(dataset_loaders[split], desc='steps', leave=False)
            N=len(dataset_loaders[split])
            for step,(frames,gt) in enumerate(tqdm_step):
                images = [torch.autograd.Variable(img.to(device).float()) for img in frames]
                origin_labels=torch.autograd.Variable(gt.to(device).long())
                labels=F.interpolate(origin_labels.float(),size=config.input_shape,mode='nearest').long()
                
                if split=='train':
                    poly_lr_scheduler(config,optimizer,
                              iter=epoch*N+step,
                              max_iter=config.epoch*N)
                    optimizer.zero_grad()
                    
                outputs=model.forward(images)
                if config.net_name=='motion_anet':
                    mask_gt=torch.squeeze(labels,dim=1)
                    mask_loss_value=0
                    for mask in outputs['masks']:
                        mask_loss_value+=seg_loss_fn(mask,mask_gt)
                else:
                    mask_loss_value=seg_loss_fn(outputs['masks'][0],torch.squeeze(labels,dim=1))
                
                if config['net_name'].find('_stn')>=0:
                    if config['stn_object']=='features':
                        stn_loss_value=stn_loss(outputs['features'],labels.float(),outputs['pose'],config['pose_mask_reg'])
                    elif config['stn_object']=='images':
                        stn_loss_value=stn_loss(outputs['stn_images'],labels.float(),outputs['pose'],config['pose_mask_reg'])
                    else:
                        assert False,'unknown stn object %s'%config['stn_object']
                    
                    total_loss_value=mask_loss_value*config['motion_loss_weight']+stn_loss_value*config['stn_loss_weight']
                else:
                    stn_loss_value=torch.tensor(0.0)
                    total_loss_value=mask_loss_value
                    
                origin_mask=F.interpolate(outputs['masks'][0], size=origin_labels.shape[2:4],mode='nearest')
                
                metric_acc.update(origin_mask,origin_labels)
                metric_stn_loss.update(stn_loss_value.item())
                metric_mask_loss.update(mask_loss_value.item())
                metric_total_loss.update(total_loss_value.item())
                if split=='train':
                    total_loss_value.backward()
                    optimizer.step()
            acc=metric_acc.get_acc()
            precision=metric_acc.get_precision()
            recall=metric_acc.get_recall()
            fmeasure=metric_acc.get_fmeasure()
            avg_p,avg_r,avg_f=metric_acc.get_avg_metric()
            mean_stn_loss=metric_stn_loss.get_mean()
            mean_mask_loss=metric_mask_loss.get_mean()
            mean_total_loss=metric_total_loss.get_mean()
            writer.add_scalar(split+'/acc',acc,epoch)
            writer.add_scalar(split+'/precision',precision,epoch)
            writer.add_scalar(split+'/recall',recall,epoch)
            writer.add_scalar(split+'/fmeasure',fmeasure,epoch)
            writer.add_scalar(split+'/avg_p',avg_p,epoch)
            writer.add_scalar(split+'/avg_r',avg_r,epoch)
            writer.add_scalar(split+'/avg_f',avg_f,epoch)
            writer.add_scalar(split+'/stn_loss',mean_stn_loss,epoch)
            writer.add_scalar(split+'/mask_loss',mean_mask_loss,epoch)
            writer.add_scalar(split+'/total_loss',mean_total_loss,epoch)
            
            if split=='train':
                tqdm_epoch.set_postfix(train_fmeasure=fmeasure.item())
            else:
                tqdm_epoch.set_postfix(val_fmeasure=fmeasure.item())
                
            if epoch % 10 == 0:
                print(split,'fmeasure=%0.4f'%fmeasure,
                      'total_loss=',mean_total_loss)
    
    if config['save_model']:
        torch.save(model.state_dict(),checkpoint_path)
    
    writer.close()
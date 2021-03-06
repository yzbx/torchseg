# -*- coding: utf-8 -*-

import os
import torch
import torch.nn as nn
from ..backbone import backbone
from ..upsample import get_suffix_net
from .motion_backbone import motion_backbone,motionnet_upsample_bilinear
from easydict import EasyDict as edict
from torch.nn.init import xavier_uniform_, zeros_
import torch.nn.functional as F

def conv(in_planes, out_planes, kernel_size=3):
    return nn.Sequential(
        nn.Conv2d(in_planes, out_planes, kernel_size=kernel_size, padding=(kernel_size-1)//2, stride=2),
        nn.ReLU(inplace=True)
    )

def dict2edict(config):
    """
    use semantic segmentation layer function
    """
    decoder_config=edict()
    decoder_config=config
    os.environ['torchseg_use_bias']=str(config.use_bias)
    return decoder_config

class motion_fcn(nn.Module):
    def __init__(self,config):
        super().__init__()
        decoder_config=dict2edict(config)
        self.input_shape=config.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=backbone(config,use_none_layer=config.use_none_layer)

        self.midnet_input_shape=self.backbone.get_output_shape(self.upsample_layer,self.input_shape)
        self.midnet_out_channels=2*self.midnet_input_shape[1]
        self.concat_size=self.midnet_input_shape[2:]
        self.class_number=config.class_number
        self.decoder=get_suffix_net(decoder_config,
                                    self.midnet_out_channels,
                                    self.class_number)

    def forward(self,imgs):
        features=[self.backbone(img,self.upsample_layer) for img in imgs]
        x=torch.cat(features,dim=1)
        x=self.decoder(x)
        #x=torch.sigmoid(x)
        return {'masks':[x]}

class motion_fcn_flow(nn.Module):
    def __init__(self,config):
        super().__init__()
        decoder_config=dict2edict(config)
        self.input_shape=config.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=backbone(config,use_none_layer=config.use_none_layer)

        self.midnet_input_shape=self.backbone.get_output_shape(self.upsample_layer,self.input_shape)
        self.midnet_out_channels=2+self.midnet_input_shape[1]
        self.concat_size=self.midnet_input_shape[2:]
        self.class_number=config.class_number
        self.decoder=get_suffix_net(decoder_config,
                                    self.midnet_out_channels,
                                    self.class_number)

    def forward(self,imgs):
        features=[self.backbone(imgs[0],self.upsample_layer),
                  F.interpolate(imgs[1], size=self.midnet_input_shape[2:4],
                                mode='bilinear', align_corners=True)]
        x=torch.cat(features,dim=1)
        x=self.decoder(x)
        #x=torch.sigmoid(x)
        return {'masks':[x]}

class motion_fcn2(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.input_shape=config.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=motion_backbone(config,use_none_layer=config['use_none_layer'])

        self.midnet_out_channels=2*self.backbone.get_feature_map_channel(self.upsample_layer)
        self.class_number=config.class_number

        self.decoder=motionnet_upsample_bilinear(in_channels=self.midnet_out_channels,
                                                     out_channels=self.class_number,
                                                     output_shape=self.input_shape[0:2])

    def forward(self,imgs):
        features=[self.backbone(img,self.upsample_layer) for img in imgs]
        x=torch.cat(features,dim=1)
        x=self.decoder(x)
        #x=torch.sigmoid(x)
        return {'masks':[x]}

class motion_fcn2_flow(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.input_shape=config.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=motion_backbone(config,use_none_layer=config['use_none_layer'])

        self.midnet_input_shape=self.backbone.get_output_shape(self.upsample_layer,self.input_shape)
        self.midnet_out_channels=2+self.midnet_input_shape[1]
        self.class_number=config.class_number

        self.decoder=motionnet_upsample_bilinear(in_channels=self.midnet_out_channels,
                                                     out_channels=self.class_number,
                                                     output_shape=self.input_shape[0:2])

    def forward(self,imgs):
        features=[self.backbone(imgs[0],self.upsample_layer),
                  F.interpolate(imgs[1], size=self.midnet_input_shape[2:4],
                                mode='bilinear', align_corners=True)]
        x=torch.cat(features,dim=1)
        x=self.decoder(x)
        #x=torch.sigmoid(x)
        return {'masks':[x]}


class stn(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.nb_ref_imgs = 1
        self.norm_stn_pose=config.norm_stn_pose
        conv_planes = [16, 32, 64, 128, 256, 256, 256]
        self.conv1 = conv(3, conv_planes[0], kernel_size=7)
        self.conv2 = conv(conv_planes[0], conv_planes[1], kernel_size=5)
        self.conv3 = conv(conv_planes[1], conv_planes[2])
        self.conv4 = conv(conv_planes[2], conv_planes[3])
        self.conv5 = conv(conv_planes[3], conv_planes[4])
        self.conv6 = conv(conv_planes[4]*(1+self.nb_ref_imgs), conv_planes[5])
        self.conv7 = conv(conv_planes[5], conv_planes[6])

        self.backbone=nn.Sequential(self.conv1,
                                    self.conv2,
                                    self.conv3,
                                    self.conv4,
                                    self.conv5)

        self.pose_pred = nn.Sequential(self.conv6,
                                       self.conv7,
                                       nn.Conv2d(conv_planes[6], 6*self.nb_ref_imgs, kernel_size=1, padding=0))

        for m in self.modules():
            if isinstance(m, nn.Conv2d) or isinstance(m, nn.ConvTranspose2d):
                xavier_uniform_(m.weight.data)
                if m.bias is not None:
                    zeros_(m.bias)

    def forward(self, imgs):
        features=[self.backbone(img) for img in imgs]
        merge_features=torch.cat(features,dim=1)
        pose = self.pose_pred(merge_features)
        pose = pose.mean(3).mean(2)
        pose = pose.view(pose.size(0), self.nb_ref_imgs, 6)

        if self.norm_stn_pose:
            pose[:,:,0]+=1
            pose[:,:,4]+=1

        stn_images=[imgs[0]]
        n=len(features)
        for i in range(n-1):
            theta=pose[:,i,:].view(-1,2,3)

            grid_images=F.affine_grid(theta,imgs[i+1].size())
            aux_images=F.grid_sample(imgs[i+1],grid_images)
            stn_images.append(aux_images)

        return {'stn_images':stn_images,
                'pose':pose}

class motion_fcn_stn(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.stn=stn(config)
        self.motion_fcn=motion_fcn(config)

    def forward(self,imgs):
        results=self.stn(imgs)
        masks=self.motion_fcn(results['stn_images'])
        results['masks']=masks['masks']

        return results
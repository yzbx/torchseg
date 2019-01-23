# -*- coding: utf-8 -*-

import torch.nn as nn
from models.backbone import backbone
from models.upsample import get_suffix_net, transform_segnet
from models.motionseg.motion_fcn import stn,dict2edict

class motion_unet(nn.Module):
    def __init__(self,config):
        super().__init__()
        decoder_config=dict2edict(config)
        self.input_shape=decoder_config.model.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=backbone(decoder_config.model,use_none_layer=True)
        
        self.midnet=transform_segnet(self.backbone,decoder_config)
        self.midnet_out_channels=self.backbone.get_feature_map_channel(self.upsample_layer)
        self.decoder=get_suffix_net(config,
                                    self.midnet_out_channels,
                                    self.class_number)
        
    def forward(self,imgs):
        features=[self.backbone.forward_layers(img) for img in imgs]
        main,aux=tuple(features)
        feature_transform=self.midnet.forward(main,aux)
        y=self.decoder(feature_transform)
        
        return {'masks',[y]}
    
class motion_unet_stn(nn.Module):
    def __init__(self,config):
        super().__init__()
        self.stn=stn(config)
        self.motion_unet=motion_unet(config)
        
    def forward(self,imgs):
        results=self.stn(imgs)
        masks=self.motion_fcn(results['stn_images'])
        results['masks']=masks['masks']
        
        return results
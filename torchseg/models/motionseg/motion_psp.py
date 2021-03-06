# -*- coding: utf-8 -*-
import torch.nn as nn
from .motion_backbone import motion_backbone,transform_motion_psp,motionnet_upsample_bilinear
from .motion_panet import get_input_channel
from easydict import EasyDict as edict

class motion_psp(nn.Module):
    """
    for use_none_layer=False
    input shape = (240,240)
        240 = min_common_multiplier(midnet_pool_sizes)*midnet_scale*upsample_ratio
            = min_common_multiplier([1,2,3,6])*5*(2**upsample_layer)

    """
    def __init__(self,config):
        super().__init__()
        self.config=config

        self.input_shape=config.input_shape
        self.upsample_layer=config['upsample_layer']
        self.backbone=motion_backbone(config,use_none_layer=config['use_none_layer'])
        aux_input_channel=get_input_channel(config.input_format)
        assert aux_input_channel>0
        if config.aux_backbone is None:
            config.aux_backbone=config.backbone_name
        aux_config=edict(config.copy())
        aux_config.backbone_name=aux_config.aux_backbone
        aux_config.freeze_layer=0
        aux_config.backbone_pretrained=False
        self.aux_backbone=motion_backbone(aux_config,use_none_layer=config.use_none_layer,in_channels=aux_input_channel)

        self.midnet_input_shape = self.backbone.get_output_shape(
            self.upsample_layer, self.input_shape)

        self.midnet_out_channels=4*self.midnet_input_shape[1]

#        midnet_pool_sizes=[1,2,3,6]
        midnet_pool_sizes=[7,4,2,1]
        midnet_scale=1
        self.midnet=transform_motion_psp(midnet_pool_sizes,
                                         midnet_scale,
                                         self.midnet_input_shape,
                                         self.midnet_out_channels)
        self.class_number=config.class_number
        self.decoder=motionnet_upsample_bilinear(in_channels=self.midnet_out_channels,
                                                     out_channels=self.class_number,
                                                     output_shape=self.input_shape[0:2])

    def forward(self,imgs):
        features=[model.forward(img,self.upsample_layer) for img,model in zip(imgs,[self.backbone,self.aux_backbone])]
        main,aux=tuple(features)
        feature_transform=self.midnet.forward(main,aux)
        y=self.decoder(feature_transform)

        return {'masks':[y]}
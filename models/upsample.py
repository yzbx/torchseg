# -*- coding: utf-8 -*-
import torchvision as TV
import torch.nn as TN
import numpy as np
import torch.nn.functional as F
import torch


class upsample_duc(TN.Module):
    def __init__(self, in_channels, out_channels, upsample_ratio):
        """
        out_channels: class number
        """
        super(upsample_duc, self).__init__()
        self.duc = TN.PixelShuffle(upsample_ratio)
        self.duc_conv = TN.Conv2d(in_channels=in_channels,
                                  out_channels=out_channels*upsample_ratio*upsample_ratio,
                                  kernel_size=3,
                                  padding=1,
                                  stride=1)
        self.duc_norm = TN.BatchNorm2d(
            num_features=out_channels*upsample_ratio*upsample_ratio)

    def forward(self, x):
        x = self.duc_conv(x)
        x = self.duc_norm(x)
        x = F.relu(x)
        x = self.duc(x)

        return x


class upsample_bilinear(TN.Module):
    def __init__(self, in_channels, out_channels, output_shape):
        """
        out_channels: class number
        """
        super().__init__()
        self.output_shape = output_shape
        self.duc_conv = TN.Conv2d(in_channels=in_channels,
                                  out_channels=out_channels,
                                  kernel_size=3,
                                  padding=1,
                                  stride=1)
        self.duc_norm = TN.BatchNorm2d(num_features=out_channels)

    def forward(self, x):
        x = self.duc_conv(x)
        x = self.duc_norm(x)
        x = F.relu(x)
        x = F.upsample(x, size=self.output_shape, mode='bilinear')
        return x
# TODO


class transform_psp(TN.Module):
    def __init__(self, pool_sizes, scale, in_channels, out_channels, out_size):
        super(transform_psp, self).__init__()

        path_out_c_list = []
        N = len(pool_sizes)
        mean_c = out_channels//N
        for i in range(N-1):
            path_out_c_list.append(mean_c)

        path_out_c_list.append(out_channels+mean_c-mean_c*N)

        self.pool_sizes = pool_sizes
        self.scale = scale
        self.out_size = out_size
        pool_paths = []
        for pool_size, out_c in zip(pool_sizes, path_out_c_list):
            pool_path = TN.Sequential(TN.AvgPool2d(kernel_size=pool_size*scale,
                                                   stride=pool_size*scale,
                                                   padding=0),
                                      TN.Conv2d(in_channels=in_channels,
                                                out_channels=out_c,
                                                kernel_size=1,
                                                stride=1,
                                                padding=0,
                                                bias=False),
                                      TN.BatchNorm2d(num_features=out_c),
                                      TN.ReLU(),
                                      TN.Upsample(size=out_size, mode='bilinear', align_corners=False))
            pool_paths.append(pool_path)

        self.pool_paths = TN.ModuleList(pool_paths)
        
        self.conv_bn_relu=TN.Sequential(TN.Conv2d(in_channels=out_channels,
                                                  out_channels=out_channels,
                                                  kernel_size=3,
                                                  stride=1,
                                                  padding=1,
                                                  bias=False),
                                      TN.BatchNorm2d(num_features=out_channels),
                                      TN.ReLU(),
                                      TN.Dropout2d(p=0.1))

    def forward(self, x):
        output_slices = [x]
        min_input_size = max(self.pool_sizes)*self.scale
        if self.out_size[0] != min_input_size:
            psp_x = F.upsample(input=x, size=min_input_size,
                               mode='bilinear', align_corners=False)
        else:
            psp_x = x

        for module in self.pool_paths:
            x = module(psp_x)
            output_slices.append(x)

        x = torch.cat(output_slices, dim=1)
        x = self.conv_bn_relu(x)
        return x


class transform_global(TN.Module):
    def __init__(self, dilation_sizes, class_number):
        """
        in_channels=class_number
        out_channels=class_number
        """
        super(transform_global, self).__init__()
        dil_paths = []
        for dilation_size in dilation_sizes:
            # for stride=1, to keep size: 2*padding=dilation*(kernel_size-1)
            dil_paths.append(TN.Conv2d(in_channels=class_number,
                                       out_channels=class_number,
                                       kernel_size=3,
                                       padding=dilation_size,
                                       dilation=dilation_size))
        self.dil_paths = TN.ModuleList(dil_paths)
        self.conv = TN.Conv2d(in_channels=class_number*(1+len(dilation_sizes)),
                              out_channels=class_number,
                              kernel_size=1,
                              padding=0)

    def forward(self, x):
        global_features = [x]
        for model in self.dil_paths:
            global_features.append(model(x))

        x = torch.cat(global_features, dim=1)
        x = self.conv(x)
        return x


class transform_dict(TN.Module):
    """
    input [b,c,h,w]
    output [b,dict_vertor_size,h,w]
    assert c in range(dict_vertor_number)
    """

    def __init__(self, dict_vector_number, dict_verctor_length):
        super().__init__()
        self.dict = TN.Embedding(num_embeddings=dict_vector_number,
                                 embedding_dim=dict_verctor_length)

    def forward(self, x):
        # [b,c,h,w] -> [b,h,w,c]
        x = x.permute([0, 2, 3, 1])
        x = x.argmax(-1)
        x = self.dict(x)
        # [b,h,w,c] -> [b,c,h,w]
        x = x.permute([0, 3, 1, 2])

        return x


class transform_fractal(TN.Module):
    def __init__(self, in_channels, depth, class_number, fusion_type='max',do_fusion=False):
        """
        input [b,in_channels,h,w]
        output [b,class_number,h,w]
        """
        super().__init__()
        self.depth = depth
        self.class_number = class_number
        self.fusion_type = fusion_type
        self.do_fusion=do_fusion
        if do_fusion:
            assert depth>1,'fusion can only do once on the top level'
        
        support_types = ['max', 'mean', 'route']
        assert fusion_type in support_types, 'fusion_type %s not in %s' % (
            fusion_type, support_types)
        assert depth >= 1, 'depth %d cannot less than 1' % depth

        fractal_paths = []
        if fusion_type == 'route':
            raise NotImplementedError
        
        if depth == 1:
            path = TN.Sequential(TN.Conv2d(in_channels=in_channels,
                                           out_channels=class_number,
                                           kernel_size=1,
                                           stride=1,
                                           padding=0),
                                 TN.BatchNorm2d(
                num_features=class_number),
                TN.ReLU(inplace=True))
            fractal_paths.append(path)
        else:
            for i in range(depth):
                if i == 0:
                    path = transform_fractal(
                        in_channels, i+1, class_number, fusion_type)
                else:
                    path = TN.Sequential(TN.Conv2d(in_channels=in_channels,
                                                   out_channels=(
                                                       2**i)*class_number,
                                                   kernel_size=1,
                                                   stride=1,
                                                   padding=0),
                                         TN.BatchNorm2d(num_features=(2**i)*class_number),
                                         TN.ReLU(inplace=True),
                                         transform_fractal((2**i)*class_number, i, class_number, fusion_type))
                
                fractal_paths.append(path)
        self.fractal_paths=TN.ModuleList(fractal_paths)

    def forward(self, x):
        outputs=[]
        for model in self.fractal_paths:
            y=model(x)
            if type(y) is list:
                outputs.extend(y)
            else:
                outputs.append(y)
        
        if self.do_fusion:
            if self.fusion_type=='max':
                result=None
                for o in outputs:
                    if result is None:
                        result=o
                    else:
                        result=torch.max(result,o)
                return result
            elif self.fusion_type=='mean':
                result=None
                for o in outputs:
                    if result is None:
                        result=o
                    else:
                        result=result+o
                return result/len(outputs)
            elif self.fusion_type=='route':
                raise NotImplementedError
            else:
                raise Exception('This is unexcepted Error')
            
        return outputs

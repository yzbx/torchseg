# -*- coding: utf-8 -*-

from imgaug import augmenters as iaa
import numpy as np
import cv2
import math
import random
from easydict import EasyDict as edict
import matplotlib.pyplot as plt
from utils.disc_tools import show_images

class ImageAugmenter:
    def __init__(self, propability=0.25):
        sometimes = lambda aug: iaa.Sometimes(propability, aug)
        blur = iaa.OneOf([
            iaa.GaussianBlur((0, 3.0)),
            # blur images with a sigma between 0 and 3.0
            iaa.AverageBlur(k=(2, 7)),
            # blur image using local means with kernel sizes between 2 and 7
            iaa.MedianBlur(k=(3, 11))
            # blur image using local medians with kernel sizes between 2 and 7
        ])
        noise = iaa.AdditiveGaussianNoise(loc=0, scale=(0.0, 0.05 * 255), per_channel=0.5)
        # add gaussian noise to images
        dropout = iaa.Dropout((0.01, 0.1), per_channel=0.5)
        bright = iaa.Add((-10, 10), per_channel=0.5)
        # change brightness of images (by -10 to 10 of original value)
        # randomly remove up to 10% of the pixels
        self.seq = iaa.Sequential(
            [sometimes(blur),
             sometimes(noise),
             sometimes(dropout),
             sometimes(bright)
             ],
            random_order=True)

    def augument_image(self, image):
        return self.seq.augment_image(image)

class ImageTransformer(object):
    def __init__(self,config,propability=0.25):
        self.config=config
        self.p=propability
        
    def transform_image_and_mask(self,image,mask,propability=None,config=None):
        if config is None:
            config=self.config
            
        if not hasattr(config,'debug'):
            config.debug=False
        
        if propability is None:
            propability=self.p
        
        if propability == 0:
            return image,mask
        
        assert propability >= 0 and propability <= 1,'propability %0.2f not in [0,1]'%propability
        
        a=np.random.rand()
        if hasattr(config,'rotate') and a<propability:
            if hasattr(config.rotate,'angle'):
                angle=config.rotate.angle
            elif hasattr(config.rotate,'max_angle'):
                a=np.random.rand()
                angle=a*config.rotate.max_angle
            else:
                assert False,'angle and max_angle shoule have one and only one defined!'
            
            if config.debug:
                print('rotate image and mask with angle %0.2f'%angle)
            image,mask=self.rotate_transform(image,mask,angle)
        
        a=np.random.rand()
        if hasattr(config,'crop') and a<propability:
            if hasattr(config.crop,'crop_size'):
                crop_size=config.crop.crop_size
            elif hasattr(config.crop,'crop_ratio'):
                crop_ratio=config.crop.crop_ratio
                h,w=mask.shape
                if type(crop_ratio) == list or type(crop_ratio)==tuple:
                    ratio_max=max(crop_ratio)
                    ratio_min=min(crop_ratio)
                    a=np.random.rand()
                    th=(ratio_min+(ratio_max-ratio_min)*a)*h
                    tw=(ratio_min+(ratio_max-ratio_min)*a)*w
                    crop_size=(int(th),int(tw))
                else:
                    crop_size=(int(crop_ratio*h),int(crop_ratio*w))
            else:
                assert False,'crop size and crop ratio should have one and only one defined!'
            
            if config.debug:
                print('crop image and mask with size (%d,%d)'%(crop_size[0],crop_size[1]))
            image,mask=self.crop_transform(image,mask,crop_size)
            
        a=np.random.rand()
        if hasattr(config,'horizontal_flip') and a<propability:
            if config.horizontal_flip:
                if config.debug:
                    print('horizontal flip')
                image,mask=self.horizontal_flip_transform(image,mask)
            
        a=np.random.rand()
        if hasattr(config,'vertical_flip') and a<propability:
            if config.vertical_flip:
                if config.debug:
                    print('vertical flip')
                image,mask=self.vertical_flip_transform(image,mask)
            
        return image,mask
        
    
    @staticmethod
    def rotate_while_keep_size(image,rotation,interpolation):
        def rotateImage(image, angle):
              image_center = tuple(np.array(image.shape[1::-1]) / 2)
              rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
              result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=interpolation)
              return result
        # Get size before we rotate
        y,x=image.shape[0:2]
#        rotation=rotation*2
#        image_2a=rotateImage(image,rotation)
        image_a=rotateImage(image,rotation/2)
#        Y_2a,X_2a=image_2a.shape[0:2]
        Y_a,X_a=image_a.shape[0:2]
        assert y==Y_a and x==X_a,'rotate image has different size'
    
#        tan_angle=math.tan(math.radians(rotation))
        tan_angle_half=math.tan(math.radians(rotation/2))
        cos_angle=math.cos(math.radians(rotation))
        cos_angle_half=math.cos(math.radians(rotation/2))
        
        width_new_float=2*(cos_angle_half*(x/2-tan_angle_half*y/2)/cos_angle)
        height_new_float=2*(cos_angle_half*(y/2-tan_angle_half*x/2)/cos_angle)
        
        assert width_new_float>0,'half of the angle cannot bigger than arctan(width/height)'
        assert height_new_float>0,'half of the angle cannot bigger than arctan(height/width)'
#        height_new=2*int(cos_angle_half*(x/2-tan_angle_half*y/2)/cos_angle)
#        width_new=2*int(cos_angle_half*(y/2-tan_angle_half*x/2)/cos_angle)
#        print('old height is',y)
#        print('old width is',x)
#        print('new_height is',height_new_float)
#        print('new_width is',width_new_float)
    
        x_new=int(math.ceil((x-width_new_float)/2))
        y_new=int(math.ceil((y-height_new_float)/2))
        x_new_end=int(math.floor(width_new_float+(x-width_new_float)/2))
        y_new_end=int(math.floor(height_new_float+(y-height_new_float)/2))
        
        new_image=image_a[y_new:y_new_end,x_new:x_new_end]
#        print(y,x)
        # Return the image, re-sized to the size of the image passed originally
        return cv2.resize(src=new_image,dsize=(x,y), interpolation=interpolation)
    
    @staticmethod
    def rotate_transform(image,mask,rotate_angle):
        new_image=ImageTransformer.rotate_while_keep_size(image,rotate_angle,cv2.INTER_CUBIC)
        new_mask=ImageTransformer.rotate_while_keep_size(mask,rotate_angle,cv2.INTER_NEAREST)
        return new_image,new_mask
    
    @staticmethod
    def crop_transform(image,mask,crop_size):
        th,tw=crop_size
        h,w=mask.shape
        assert h>th,'crop size (%d,%d) should small than image size (%d,%d)'%(th,tw,h,w)
        assert w>tw,'crop size (%d,%d) should small than image size (%d,%d)'%(th,tw,h,w)
        
        x1 = random.randint(0, w - tw)
        y1 = random.randint(0, h - th)
        
        # image[y1:y1+th,x1:x1+tw] == image[y1:y1+th,x1:x1+tw,:]
        new_image=image[y1:y1+th,x1:x1+tw]
        new_mask=mask[y1:y1+th,x1:x1+tw]
        return new_image,new_mask
    
    @staticmethod
    def horizontal_flip_transform(image,mask):
        new_image=cv2.flip(image,1)
        new_mask=cv2.flip(mask,1)
        return new_image,new_mask
    
    @staticmethod
    def vertical_flip_transform(image,mask):
        new_image=cv2.flip(image,0)
        new_mask=cv2.flip(mask,0)
        return new_image,new_mask

def get_default_augmentor_config():
    config=edict()
    config.rotate=edict()
    config.rotate.max_angle=15
    config.crop=edict()
    config.crop.crop_ratio=[0.85,1.0]
    config.horizontal_flip=True
    config.vertical_filp=False
    config.debug=False
    
    return config

class Augmentations(object):
    def __init__(self,p=0.25,config=None):
        if config is None:
            config=get_default_augmentor_config()
        
        self.aug=ImageAugmenter(propability=p)
        self.tran=ImageTransformer(config=config,propability=p)
        self.p=p
        
    def transform(self,image,mask=None):
        if mask is None:
            return self.aug.augument_image(image)
        else:
            return self.tran.transform_image_and_mask(image,mask)
    
if __name__ == '__main__':
    
    config=edict()
    config.rotate=edict()
    config.rotate.angle=30
    config.crop=edict()
    config.crop.crop_size=(100,100)
    config.horizontal_flip=True
    config.vertical_filp=False
    config.debug=True
    
    aug = ImageAugmenter()
    tran = ImageTransformer(config)
    img = cv2.imread('test/image.png',cv2.IMREAD_COLOR)
    mask = cv2.imread('test/mask.png',cv2.IMREAD_GRAYSCALE)
#    img=np.random.rand(60,80)
#    mask=np.random.rand(60,80)
    
    assert img is not None
    assert mask is not None
    show_images([img,mask])
    
    aug_img=aug.augument_image(img)
    tran_img,tran_mask=tran.transform_image_and_mask(img,mask,propability=1)
    
    imgs = [cv2.resize(img,(224,224),interpolation=cv2.INTER_NEAREST) for img in [aug_img,tran_img,tran_mask] ]
    show_images(imgs,['aug','tran_img','tran_mask'])
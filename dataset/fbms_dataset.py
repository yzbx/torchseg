# -*- coding: utf-8 -*-

import os
import glob
import torch.utils.data as td
import random
import numpy as np
import cv2

class fbms_dataset(td.Dataset):
    def __init__(self,config,split='train',normalizations=None):
        self.config=config
        self.split=split
        self.normalizations=normalizations
        if split=='train':
            self.gt_files=glob.glob(os.path.join(self.config['train_path'],'*','GroundTruth','*.png'),recursive=True)
        else:
            self.gt_files=glob.glob(os.path.join(self.config['val_path'],'*','GroundTruth','*.png'),recursive=True)
            
        print('%s dataset size %d'%(split,len(self.gt_files)))
        
    def __len__(self):
        return len(self.gt_files)
    
    def get_frames(self,gt_file):
        def get_frame_path(base_path,video_name,frame_index):
            path=os.path.join(base_path,video_name+'_'+'%02d'%frame_index)+'.jpg'
            if not os.path.exists(path):
                path=os.path.join(base_path,video_name+'_'+'%03d'%frame_index)+'.jpg'
            if not os.path.exists(path):
                path=os.path.join(base_path,video_name+'_'+'%04d'%frame_index)+'.jpg'
            
            if not os.path.exists(path):
                path=os.path.join(base_path,video_name+'%02d'%frame_index)+'.jpg'
            if not os.path.exists(path):
                path=os.path.join(base_path,video_name+'%03d'%frame_index)+'.jpg'
            if not os.path.exists(path):
                path=os.path.join(base_path,video_name+'%04d'%frame_index)+'.jpg'
            return path
    
        path_strings=gt_file.split(os.path.sep)
        
        index_string=path_strings[-1].split('_')[0]
        frame_index=int(index_string)
        video_name=path_strings[-3]
        
        base_path=os.path.sep.join(path_strings[0:-2])
        main_frame=get_frame_path(base_path,video_name,frame_index)
        assert os.path.exists(main_frame),main_frame
        
        x=random.random()
        if x>0.5:
            aux_frame=get_frame_path(base_path,video_name,frame_index+self.config['frame_gap'])
            if not os.path.exists(aux_frame):
                aux_frame=get_frame_path(base_path,video_name,frame_index-self.config['frame_gap'])
        else:
            aux_frame=get_frame_path(base_path,video_name,frame_index-self.config['frame_gap'])
            if not os.path.exists(aux_frame):
                aux_frame=get_frame_path(base_path,video_name,frame_index+self.config['frame_gap'])
    
        assert os.path.exists(aux_frame),aux_frame
        return [main_frame,aux_frame]
    
    def __getitem__(self,index):
        frames=self.get_frames(self.gt_files[index])
        frame_images=[cv2.imread(f,cv2.IMREAD_COLOR) for f in frames]
        gt_image=cv2.imread(self.gt_files[index],cv2.IMREAD_GRAYSCALE)
        
        # resize image
        resize_frame_images=[cv2.resize(img,(224,224),interpolation=cv2.INTER_LINEAR) for img in frame_images]
        resize_gt_image=cv2.resize(gt_image,(224,224),interpolation=cv2.INTER_NEAREST)
        
        # normalize image
        if self.normalizations is not None:
            resize_frame_images = [self.normalizations.forward(img) for img in resize_frame_images]
        
        # bchw
        resize_frame_images=[img.transpose((2,0,1)) for img in resize_frame_images]
        resize_gt_image=np.expand_dims(resize_gt_image,0)
        
        resize_gt_image=(resize_gt_image!=0).astype(np.uint8)
        return resize_frame_images,resize_gt_image
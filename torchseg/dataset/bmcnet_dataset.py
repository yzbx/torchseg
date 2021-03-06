# -*- coding: utf-8 -*-

import os
import glob
import numpy as np
import random
import cv2
from .segtrackv2_dataset import motionseg_dataset

class bmcnet_dataset(motionseg_dataset):
    """
    BMCnet
    ├── real
    │   ├── Video_001
    │   ├── Video_002
    │   ├── Video_003
    │   ├── Video_004
    │   ├── Video_005
    │   ├── Video_006
    │   ├── Video_007
    │   ├── Video_008
    │   └── Video_009
    ├── test
    │   ├── 112_png
    │   ├── 122_png
    │   ├── 212_png
    │   ├── 222_png
    │   ├── 312_png
    │   ├── 322_png
    │   ├── 412_png
    │   ├── 422_png
    │   ├── 512_png
    │   └── 522_png
    └── train
        ├── 111_png
        ├── 121_png
        ├── 211_png
        ├── 221_png
        ├── 311_png
        ├── 321_png
        ├── 411_png
        ├── 421_png
        ├── 511_png
        └── 521_png
    """
    def __init__(self,config,split='train',normalizations=None,augmentations=None):
        super().__init__(config,split,normalizations,augmentations)

        self.main_files=self.get_main_files()
        print('dataset size = {}',len(self.main_files))
        n=len(self.main_files)
        if n > self.config.use_part_number > 0:
            gap=n//self.config.use_part_number
            self.main_files=self.main_files[::gap]
            print('total dataset image %d, use %d'%(n,len(self.main_files)))

    def __len__(self):
        return len(self.main_files)

    def get_main_files(self):
        if self.split=='train':
            rootpath=os.path.join(self.root_path,'train')
        else:
            rootpath=os.path.join(self.root_path,'test')

        pattern=os.path.join(rootpath,'**','input','*.png')
        main_files=glob.glob(pattern,recursive=True)
        main_files.sort()

        valid_main_files=[f for f in main_files if os.path.exists(self.get_gt_file(f))]
        assert len(valid_main_files)>0,'rootpath={}'.format(rootpath)
        return valid_main_files

    def get_aux_file(self,main_file):
        dirname=os.path.dirname(main_file)
        pattern=os.path.join(dirname,'*.png')
        aux_files=glob.glob(pattern)
        aux_files.sort()
        assert len(aux_files)>0,'main_file={},pattern={}'.format(main_file,pattern)

        main_index=aux_files.index(main_file)
        aux_files.remove(main_file)
        n=len(aux_files)
        if self.frame_gap==0:
            frame_gap=random.randint(1,10)
        else:
            frame_gap=self.frame_gap

        x=random.random()
        if x>0.5:
            aux_index=main_index+frame_gap
            aux_index=aux_index if aux_index<n else n-1
        else:
            aux_index=main_index-frame_gap
            aux_index=aux_index if aux_index>=0 else 0
        return aux_files[aux_index]

    def get_gt_file(self,main_file):
        if self.split=='train':
            gt_file=main_file.replace('input','truth')
        else:
            gt_file=main_file.replace('input','private_truth')
        return gt_file

    def __get_path__(self,index):
        main_file=self.main_files[index]
        aux_file=self.get_aux_file(main_file)
        gt_files=[self.get_gt_file(main_file),self.get_gt_file(aux_file)]
        
        return main_file,aux_file,gt_files

    def __get_image__(self,index):
        main_file,aux_file,gt_files=self.__get_path__(index)
        main_file=self.main_files[index]
        aux_file=self.get_aux_file(main_file)
        
        frame_images=[cv2.imread(f,cv2.IMREAD_COLOR) for f in [main_file,aux_file]]
        gt_image=cv2.imread(gt_files[0],cv2.IMREAD_GRAYSCALE)
        
        labels=[]
        label=np.zeros_like(gt_image)
        label[gt_image>0]=1
        
        labels.append(label)
        if os.path.exists(gt_files[1]):
            aux_gt_image=cv2.imread(gt_files[1],cv2.IMREAD_GRAYSCALE)
            aux_label=np.zeros_like(aux_gt_image)
            aux_label[aux_gt_image>0]=1
            labels.append(aux_label)
        else:
            aux_gt_image=np.zeros_like(gt_image)
            labels.append(aux_gt_image)
        return frame_images,labels,main_file,aux_file,gt_files
"""
notebook utils for motionseg
"""


import torch.utils.data as td
import torch
import os
from ...dataset.dataset_generalize import image_normalizations
from .torch_tools import get_ckpt_path,load_ckpt
from ...models.motionseg.motion_utils import fine_tune_config,get_model
from ...models.motionseg.motion_utils import get_parser,get_dataset
from .configs.motionseg_config import get_default_config
from .configs.semanticseg_config import load_config

def get_model_and_dataset(cfg,filter_relu=None):
    if isinstance(cfg,(tuple,list)):
        parser=get_parser()
        args = parser.parse_args(cfg)

        config=get_default_config()
        if args.net_name=='motion_psp':
            if args.use_none_layer is False or args.upsample_layer<=3:
                min_size=30*config.psp_scale*2**config.upsample_layer
            else:
                min_size=30*config.psp_scale*2**3

            config.input_shape=[min_size,min_size]

        for key in config.keys():
            if hasattr(args,key):
                print('{} = {} (default: {})'.format(key,args.__dict__[key],config[key]))
                config[key]=args.__dict__[key]
            else:
                print('{} : (default:{})'.format(key,config[key]))

        for key in args.__dict__.keys():
            if key not in config.keys():
                print('{} : unused keys {}'.format(key,args.__dict__[key]))

    elif isinstance(cfg,str):
        config=load_config(cfg)
        default_config=get_default_config()
        for key in default_config.keys():
            if not hasattr(config,key):
                config[key]=default_config[key]
    else:
        config=cfg

    config=fine_tune_config(config)

    if filter_relu is not None:
        config.filter_relu=filter_relu

    model=get_model(config)

    # support for cpu/gpu
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    normer=image_normalizations(ways='-1,1')
    dataset_loaders={}
    for split in ['train','val']:
        xxx_dataset=get_dataset(config,split)
        batch_size=config.batch_size if split=='train' else 1
        xxx_loader=td.DataLoader(dataset=xxx_dataset,batch_size=batch_size,shuffle=True,drop_last=False,num_workers=2)
        dataset_loaders[split]=xxx_loader

    if isinstance(cfg,str):
        log_dir=os.path.dirname(cfg)
        checkpoint_path = get_ckpt_path(log_dir)
    else:
        log_dir = os.path.join(config['log_dir'], config['net_name'],
                               config['dataset'], config['note'])
        checkpoint_path = get_ckpt_path(log_dir)
    model=load_ckpt(model,checkpoint_path)

    return model,dataset_loaders,normer
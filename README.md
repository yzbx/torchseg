# torchseg
use pytorch to do image semantic segmentation

# requriments
```
conda install pytorch torchvision -c pytorch
pip install opencv-python
pip install tensorboardX
pip install easydict
```

# code reference
- https://github.com/meetshah1995/pytorch-semseg
```
test pspnet model on cityscapes dataset
Overall Acc: 	 0.865857910768811
Mean Acc : 	 0.4482797176755918
FreqW Acc : 	 0.7728509434255326
Mean IoU : 	 0.36876733235206416
note for official website https://hszhao.github.io/projects/pspnet/
the miou is 0.8+
```
- https://github.com/CSAILVision/semantic-segmentation-pytorch
- [cityscapes dataset evaluation](https://github.com/mcordts/cityscapesScripts)

# blog reference
- [paper and dataset for semantic segmentation introduction](https://meetshah1995.github.io/semantic-segmentation/deep-learning/pytorch/visdom/2017/06/01/semantic-segmentation-over-the-years.html#sec_datasets)

# todo
- [x] pspnet
- [ ] color for label image and predict image
- [x] keras empty net: use pytorch loader and tensorboard-pytorch in keras
- [x] notebook for keras and empty net
- [x] simplenet
- [x] motionnet
- [x] tensorboard-pytorch
- [x] miou
- [x] input image preprocess and augmentation: 
    - [ ] ~~imagenet~~
    - [x] [-1,1]
    - [ ] ~~[0,1]~~
- [x] pspnet + edge
    - [ ] multi input, output, loss, log
    - [ ] edge before pspnet or after pspnet ?
    - [ ] Series connection or Parallel connection
    - [ ] change edge width with epoch
- [x] pspnet + global
    - very different from keras version, from single dilation to multi dilation
- [x] pspnet + dict learning
    - dict net after upsample net (conv feature can be upsampled with duc, but dict feature may not fit for upsample)
- [ ] pspnet + fractal filters (random number of filters)
- [ ] ~~the ignore_index for CrossEntropyLoss~~
    - [ ] foreground ids[1-19], background ids[0], ignore_index[100,255 in labels?]
- [ ] multi outputs metrics support like keras
- [x] benchmark
    - [x] dataset loader with path
    - [x] upsample predict results
    - [ ] ~~crop + merge predict results~~
    - [x] train id --> label id
    
# benchmark
- use code from https://github.com/mcordts/cityscapesScripts (only support for python2)
- change to python2 environment `source activate env2`
- clone them and install them by `pip install .`
- `export CITYSCAPES_RESULTS=/media/sdc/yzbx/benchmark_output/cityscapes`
- `export CITYSCAPES_DATASET=/media/sdb/CVDataset/ObjectSegmentation/archives/Cityscapes_archives/gtFine_trainvaltest`
- open terminal and input: `csEvalPixelLevelSemanticLabeling`
- the image size and id transform can be view in [test/benchmark_test.py](test/benchmark_test.py)
- note: the benchmark is very slow, even for only 500 val images, about 5-10s/per image
- a failed result can be see in [#3](https://github.com/ISCAS007/torchseg/issues/3)
import random
import torch
import numpy as np
import argparse
from glob import glob 
from os import path 
import torch.nn as nn

def setup_seed(seed=42):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True

class binary_erosion(object):
    def __init__ (self):
        self.conv = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=3, bias=False, padding=1)
        self.conv.weight = torch.nn.Parameter(torch.tensor([[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]).unsqueeze(0).unsqueeze(0))
    def __call__(self, mask, iterations):
        mask = mask.unsqueeze(0)
        for _ in range(iterations):
            mask = self.conv(mask.float()) >= 2.0
        return mask
    def __repr__(self):
        return "binary erosion..."
    
class Add_Legs(object):
    def __init__(self, leg_directory, p=0.9):
        self.p = p
        self.leg_files = glob(path.join(leg_directory, '*.pt'))
        self.erosion = binary_erosion()

        if len(self.leg_files) == 0:
            raise ValueError("No legs found.")
        print(f"{len(self.leg_files)} leg masks found at {leg_directory}.")
    def __call__(self, img):
        if torch.rand(1) > self.p: return img
        legs = torch.load(random.choice(self.leg_files))
        mask = legs[3,...].unsqueeze(0)
        mask = mask == 0.0
        legs = legs[:3,...] / 255.0
        mask = self.erosion(mask, 2).squeeze(0)
        return img * mask + legs * ~mask
    def __repr__(self):
        return "adding random legs augmentation"

def add_background_image(images, alpha, background_image):
#   print(f'background: {background_image.shape}')
#   print(f'images: {images.shape}')
#   print(f'alpha: {alpha.shape}')
  alpha = torch.ceil(alpha)
  reg_mask = alpha == 0.0
  inv_mask = alpha != 0.0
  images_with_background = images * inv_mask.unsqueeze(0) + (background_image / 255.0) * reg_mask.unsqueeze(0)
#   print(f'final: {images_with_background.shape}')
  return images_with_background
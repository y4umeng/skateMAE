import os
import argparse
import math
import torch
import torchvision
# from torch.utils.tensorboard import SummaryWriter
from torchvision.transforms import ToTensor, Compose, Normalize
from tqdm import tqdm

from model import *
from utils import setup_seed
from data import skate_data

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--batch_size', type=int, default=256)
    parser.add_argument('--max_device_batch_size', type=int, default=256)
    parser.add_argument('--base_learning_rate', type=float, default=1e-3)
    parser.add_argument('--weight_decay', type=float, default=0.05)
    parser.add_argument('--total_epoch', type=int, default=100)
    parser.add_argument('--warmup_epoch', type=int, default=5)
    parser.add_argument('--pretrained_model_path', type=str, default=None)
    parser.add_argument('--output_model_path', type=str, default='vit-t-classifier-from_scratch.pt')

    args = parser.parse_args()

    setup_seed(args.seed)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    batch_size = args.batch_size
    load_batch_size = min(args.max_device_batch_size, batch_size)

    assert batch_size % load_batch_size == 0
    steps_per_update = batch_size // load_batch_size

    transform = Compose([ToTensor(), Normalize(0.5, 0.5)])
    train_dataset = skate_data('data/batb1k/synthetic_frames', 'data/batb1k/synthetic_frame_poses.csv', device, transform)
    val_dataset = skate_data('data/batb1k/val', 'data/batb1k/synthetic_frame_poses.csv', device, transform)
    train_dataloader = torch.utils.data.DataLoader(train_dataset, load_batch_size, shuffle=True, num_workers=2)
    val_dataloader = torch.utils.data.DataLoader(val_dataset, load_batch_size, shuffle=False, num_workers=2)

    if args.pretrained_model_path is not None:
        model = torch.load(args.pretrained_model_path, map_location='cpu')
        # writer = SummaryWriter(os.path.join('logs', 'cifar10', 'pretrain-cls'))
    else:
        model = MAE_ViT()
        # writer = SummaryWriter(os.path.join('logs', 'cifar10', 'scratch-cls'))

    dist_classes = 100
    elev_classes = 360
    azim_classes = 360
    model = skateMAE(model.encoder, dist_classes, elev_classes, azim_classes).to(device)

    loss_fn = torch.nn.CrossEntropyLoss()
    acc_fn = lambda logit, label: torch.mean((logit.argmax(dim=-1) == label).float())

    optim = torch.optim.AdamW(model.parameters(), lr=args.base_learning_rate * args.batch_size / 256, betas=(0.9, 0.999), weight_decay=args.weight_decay)
    lr_func = lambda epoch: min((epoch + 1) / (args.warmup_epoch + 1e-8), 0.5 * (math.cos(epoch / args.total_epoch * math.pi) + 1))
    lr_scheduler = torch.optim.lr_scheduler.LambdaLR(optim, lr_lambda=lr_func)

    best_val_acc = 0
    step_count = 0
    optim.zero_grad()
    for e in range(args.total_epoch):
        model.train()
        losses = []
        acces = []
        for img, dist_label, elev_label, azim_label in tqdm(iter(train_dataloader)):
            step_count += 1
            dist_logits, elev_logits, azim_logits = model(img)
            loss = loss_fn(dist_logits, dist_label) + loss_fn(elev_logits, elev_label) + loss_fn(dist_logits, azim_label)
            acc = torch.mean(torch.stack((acc_fn(dist_logits, dist_label), acc_fn(elev_logits, elev_label), acc_fn(azim_logits, azim_label))))
            loss.backward()
            if step_count % steps_per_update == 0:
                optim.step()
                optim.zero_grad()
            losses.append(loss.item())
            acces.append(acc.item())
        lr_scheduler.step()
        avg_train_loss = sum(losses) / len(losses)
        avg_train_acc = sum(acces) / len(acces)
        print(f'In epoch {e}, average training loss is {avg_train_loss}, average training acc is {avg_train_acc}.')

        model.eval()
        with torch.no_grad():
            losses = []
            acces = []
            for img, dist_label, elev_label, azim_label in tqdm(iter(val_dataloader)):
                dist_logits, elev_logits, azim_logits = model(img)
                loss = loss_fn(dist_logits, dist_label) + loss_fn(elev_logits, elev_label) + loss_fn(dist_logits, azim_label)
                acc = torch.mean(torch.stack((acc_fn(dist_logits, dist_label), acc_fn(elev_logits, elev_label), acc_fn(azim_logits, azim_label))))
                losses.append(loss.item())
                acces.append(acc.item())
            avg_val_loss = sum(losses) / len(losses)
            avg_val_acc = sum(acces) / len(acces)
            print(f'In epoch {e}, average validation loss is {avg_val_loss}, average validation acc is {avg_val_acc}.')  

        if avg_val_acc > best_val_acc:
            best_val_acc = avg_val_acc
            print(f'saving best model with acc {best_val_acc} at {e} epoch!')       
            torch.save(model, args.output_model_path)

        # writer.add_scalars('cls/loss', {'train' : avg_train_loss, 'val' : avg_val_loss}, global_step=e)
        # writer.add_scalars('cls/acc', {'train' : avg_train_acc, 'val' : avg_val_acc}, global_step=e)
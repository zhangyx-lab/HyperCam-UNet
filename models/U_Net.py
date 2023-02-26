from module import Module
from typing import List, Tuple
import torch
import torch.nn as nn
from torchvision import transforms
from dataset import Sample_t
from env import DEVICE

class CustomLoss(nn.Module):
    def __init__(self):
        super(CustomLoss, self).__init__()

    def forward(self, pred, truth):
        return torch.sum(torch.abs(truth - pred))

# lossFunction = nn.BCEWithLogitsLoss().to(DEVICE)
# lossFunction = nn.CrossEntropyLoss().to(DEVICE)
lossFunction = CustomLoss().to(DEVICE)

Features_T = List[torch.Tensor]

class U_Node(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        # self.norm1 = nn.BatchNorm2d(in_ch)
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1)
        self.relu1 = nn.ReLU()
        # self.norm2 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1)
        self.relu2 = nn.ReLU()
        # Random init
        for layer in [self.conv1, self.conv2]:
            nn.init.normal_(layer.weight, mean=0, std=1e-4)

    def forward(self, x):
        # out = self.norm1(x)
        out = self.conv1(x)
        out = self.relu1(out)
        # out = self.norm2(out)
        out = self.conv2(out)
        out = self.relu2(out)
        return out


class Encoder(nn.Module):
    def __init__(self, channels: List[int], sample: torch.Tensor):
        super().__init__()
        # Downscaler
        self.pool = nn.MaxPool2d((2, 2))
        # Initialize input sample
        nodes = []
        # Generate node list according to input sample and channels
        for c in channels:
            sample = self.pool(sample)
            # Get dimensions out of the current sample
            _, d, _, _ = sample.shape
            # Create new node layer using the sample
            layer = U_Node(d, c)
            # Iterate the sample
            sample = layer(sample)
            print("Encoder node shape", sample.shape)
            # Append layer to node list
            nodes.append(layer)
        # Instantiate node list
        self.nodes = nn.ModuleList(nodes)
        del nodes

    def forward(self, x) -> Features_T:
        features = []
        for node in self.nodes:
            x = self.pool(x)
            x = node(x)
            features.append(x)
        return features


class Decoder(nn.Module):
    def __init__(self, channels: List[int], sample: Features_T):
        super().__init__()
        # Initialize parameters
        self.layer_count = len(channels)
        # Decompose packed tensors
        sample = sample[::-1]
        offset = len(sample) - self.layer_count
        s, features = sample[0], sample[offset:]
        upconvs = []
        scalers = []
        dec_nodes = []
        # Generate layers
        for i in range(len(channels)):
            _, d, _, _ = s.shape
            c = channels[i]
            # Upscale convolution
            upconv = nn.ConvTranspose2d(d, c, 2, 2)
            upconvs.append(upconv)
            # Iterate input sample
            s: torch.Tensor = upconv(s)
            # Generate scaler
            _, _, w, h = s.shape
            scaler = transforms.Resize((w, h))
            scalers.append(scaler)
            f = scaler(features[i])
            s = torch.cat([s, f], dim=1)
            _, d, _, _ = s.shape
            # Concat sample with features
            decoder = U_Node(d, c)
            dec_nodes.append(decoder)
            s: torch.Tensor = decoder(s)
            print("Decoder node shape", s.shape)

        # self.upconvs = nn.ModuleList(upconvs)
        # self.scalers = nn.ModuleList(scalers)
        # self.dec_nodes = nn.ModuleList(dec_nodes)
        self.layers = nn.ModuleList([
            nn.ModuleList(upconvs[i], scalers[i], dec_nodes[i])
            for i in range(self.layer_count)
        ])

    def forward(self, features: Features_T):
        features = features[::-1]
        offset = len(features) - self.layer_count
        x, features = features[0], features[offset:]
        for i in range(self.layer_count):
            upconv, scaler, dec_node = self.layers[i]
            x = upconv(x)
            f = scaler(features[i])
            x = torch.cat([x, f], dim=1)
            x = dec_node(x)
        return x

class Model(Module):
    def __init__(self, device, sample: Sample_t):
        super(Model, self).__init__(device)
        sample_in, sample_out = sample
        print("model input shape", sample_in.shape)
        # Resize the decoder output to match sample output
        _, _, w, h = sample_out.shape
        self.scaler = transforms.Resize((w, h))
        s = self.scaler(sample_in)
        # Encoder
        self.encoder = Encoder([16, 32, 64, 128, 256], s)
        s = self.encoder(s)
        # Decoder
        self.decoder = Decoder([256, 128, 64, 32, 16], s)
        s = self.decoder(s)
        # Report output shape
        print("Decoder result shape", s.shape)
        # FC Layers to Complete Spectrum Information
        self.fc = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=(1,1)),
            nn.Conv2d(32, 64, kernel_size=(1,1)),
            nn.Conv2d(64, 128, kernel_size=(1,1)),
            nn.Conv2d(128, 256, kernel_size=(1,1)),
            nn.Conv2d(256, sample_out.shape[2], kernel_size=(1,1)),
        )
        s = self.fc(s)
        # self.sigmoid = nn.Sigmoid()
        print("Final result shape", s.shape)
        # Clear memory
        s.detach()
        sample_out.detach()

    def forward(self, x):
        # x.shape = (Batches, Bands, Hight, Width)
        bri_map = torch.stack((torch.mean(x, dim=1),), dim=1)
        out = x / bri_map
        # Learnable layers
        out = self.scaler(out)
        out = self.encoder(out)
        out = self.decoder(out)
        # out = self.sigmoid(out)
        bri_map = self.scaler(bri_map)
        bri_map.detach()
        return out, bri_map

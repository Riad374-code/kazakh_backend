import torch
import torch.nn as nn
import segmentation_models_pytorch as smp
from typing import Optional, Dict, Any

class CaspianPollutionCNN(nn.Module):
    """
    Fully Convolutional Neural Network (FCN) architecture for marine pollution segmentation.
    Uses a U-Net architecture paired with a convolutional encoder backbone (ResNet / EfficientNet).
    
    Why U-Net + ResNet for Satellite Imagery?
    - Captures both deep conceptual features (what type of pollutant it is via convolutional downsampling) 
      and exact spatial boundary coordinates (where it is on the sea via skip connections).
    """

    def __init__(
        self,
        encoder_name: str = "resnet34",  # Highly effective & low-latency for hackathons
        encoder_weights: str = "imagenet", # Pre-trained convolutional weights
        in_channels: int = 3,            # 3 for RGB, 1 for SAR radar, 4+ for multi-spectral
        num_classes: int = 6,            # 0=Water, 1=Oil, 2=Algae, 3=Runoff, 4=Sediment, 5=Lakebed
        activation: Optional[str] = None # None during training (for raw logits), 'softmax' for inference
    ):
        super(CaspianPollutionCNN, self).__init__()
        self.encoder_name = encoder_name
        self.num_classes = num_classes
        
        # Initialize U-Net architecture with chosen CNN encoder
        self.model = smp.Unet(
            encoder_name=encoder_name,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=num_classes,
            activation=activation
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Input shape : (Batch, Channels, Height, Width) -> e.g., (4, 3, 512, 512)
        Output shape: (Batch, Num_Classes, Height, Width) -> e.g., (4, 6, 512, 512)
        """
        return self.model(x)

    def get_model_summary(self) -> Dict[str, Any]:
        return {
            "model_architecture": "U-Net (Convolutional Semantic Segmentation)",
            "encoder_backbone": self.encoder_name,
            "input_channels": self.model.encoder.in_channels,
            "output_classes": self.num_classes,
            "parameters_count_million": round(sum(p.numel() for p in self.model.parameters()) / 1e6, 2),
            "suitable_for": "Real-time satellite tile pixel-level anomaly categorization"
        }

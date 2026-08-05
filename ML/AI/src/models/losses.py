import torch
import torch.nn as nn
import torch.nn.functional as F

class DiceLoss(nn.Module):
    """
    Dice Loss for segmentation overlap optimization.
    Helps focus training on minority pollution pixel contours rather than overwhelming background water.
    """
    def __init__(self, smooth: float = 1e-6):
        super(DiceLoss, self).__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Probabilities via softmax across classes or sigmoid for multi-label
        probs = F.softmax(logits, dim=1)
        
        # Convert targets to one-hot encoding if needed
        if targets.dim() == 3:
            targets_one_hot = F.one_hot(targets, num_classes=logits.shape[1]).permute(0, 3, 1, 2).float()
        else:
            targets_one_hot = targets

        intersection = torch.sum(probs * targets_one_hot, dim=(2, 3))
        union = torch.sum(probs, dim=(2, 3)) + torch.sum(targets_one_hot, dim=(2, 3))
        
        dice = (2.0 * intersection + self.smooth) / (union + self.smooth)
        # Average loss over batch and classes (skipping class 0 background if desired)
        return 1.0 - torch.mean(dice[:, 1:])  # Optimize specifically on pollution classes (index 1 to N)


class FocalLoss(nn.Module):
    """
    Focal Loss specifically mitigates severe class imbalance by down-weighting well-classified 
    open sea pixels and forcing the optimizer to focus on hard-to-detect pollution borders.
    """
    def __init__(self, alpha: float = 0.25, gamma: float = 2.0):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = F.cross_entropy(logits, targets, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * ce_loss
        return torch.mean(focal_loss)


class CombinedDiceFocalLoss(nn.Module):
    """
    Hybrid loss combining Dice Overlap Optimization with Focal Class Imbalance Handling.
    Recommended default for Phase 5 & 6 marine segmentation during the hackathon.
    """
    def __init__(self, dice_weight: float = 0.5, focal_weight: float = 0.5):
        super(CombinedDiceFocalLoss, self).__init__()
        self.dice_loss = DiceLoss()
        self.focal_loss = FocalLoss()
        self.dice_weight = dice_weight
        self.focal_weight = focal_weight

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        dice = self.dice_loss(logits, targets)
        focal = self.focal_loss(logits, targets)
        return (self.dice_weight * dice) + (self.focal_weight * focal)

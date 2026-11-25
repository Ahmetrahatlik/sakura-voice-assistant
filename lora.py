# XTTS GPT'si için LoRA: ana ağırlık donuk, yanına küçük A·B eklenir (eğitim ses\egitim_xtts\lora_egit.py).
# Asistan eğitilmiş LoRA'yı birlestir() ile ağırlıklara gömer: hız ve bellek aynı kalır (hizlandir()'dan ÖNCE çağrılmalı).
import torch, torch.nn as nn

HEDEF = ("attn.c_attn", "attn.c_proj", "mlp.c_fc", "mlp.c_proj")


class LoRA(nn.Module):
    def __init__(self, taban, r, alfa):
        super().__init__()
        self.taban = taban
        g, c = taban.weight.shape                     # transformers Conv1D: ağırlık (giriş, çıkış), y = x @ W + b
        self.A = nn.Parameter(torch.randn(g, r, device=taban.weight.device) / r)
        self.B = nn.Parameter(torch.zeros(r, c, device=taban.weight.device))
        self.olcek = alfa / r

    def forward(self, x):
        return self.taban(x) + (x @ self.A.to(x.dtype)) @ self.B.to(x.dtype) * self.olcek


def _katmanlar(gpt2):
    for i, blok in enumerate(gpt2.h):
        for ad in HEDEF:
            ust, alt = ad.split(".")
            yield f"{i}.{ad}", getattr(blok, ust), alt


def ekle(gpt2, r=16, alfa=32):
    katman = []
    for ad, ust, alt in _katmanlar(gpt2):
        k = LoRA(getattr(ust, alt), r, alfa)
        k.ad = ad
        setattr(ust, alt, k)
        katman.append(k)
    return katman


def durum(katman, r, alfa):
    return {"r": r, "alfa": alfa, "A": {k.ad: k.A.detach().cpu() for k in katman}, "B": {k.ad: k.B.detach().cpu() for k in katman}}


@torch.no_grad()
def birlestir(gpt2, yol, guc=1.0):
    """Kaydedilmiş LoRA'yı GPT2 ağırlıklarına kalıcı ekler (guc: 0 = etkisiz, 1 = eğitildiği gibi)."""
    d = torch.load(yol, map_location="cpu")
    olcek = d["alfa"] / d["r"] * guc
    for ad, ust, alt in _katmanlar(gpt2):
        w = getattr(ust, alt).weight
        w += (d["A"][ad] @ d["B"][ad]).to(w.device, w.dtype) * olcek

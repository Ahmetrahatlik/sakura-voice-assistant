# XTTS'in GPT kod üretimini CUDA Graph ile hızlandırır.
# Windows'ta dizüstü ekran kartına her küçük işlemi tek tek göndermek ~35 µs sürüyor; bir adımda ~600 işlem var.
# Burada tek adım bir kez "kaydedilir" ve her adımda tek komutla yeniden oynatılır. Ağırlıklar aynı, sonuç aynı yöntem.
import math
import torch
import torch.nn.functional as F


class HizliGPT:
    def __init__(self, xtts, tmax=1024, dt=torch.float16):
        g = xtts.gpt
        self.g = g
        tr = g.gpt  # GPT2Model
        self.h = tr.config.n_head
        self.d = tr.config.n_embd // self.h
        self.eps = tr.config.layer_norm_epsilon
        # ağırlıkların yarım duyarlıklı kopyası: ekran kartı belleğinden okunacak veri yarıya iner (asıl model fp32 kalır)
        c = lambda t: t.detach().to(dt).contiguous()
        self.dt = dt
        self.blocks = [dict(l1w=c(b.ln_1.weight), l1b=c(b.ln_1.bias), aw=c(b.attn.c_attn.weight), ab=c(b.attn.c_attn.bias),
                            pw=c(b.attn.c_proj.weight), pb=c(b.attn.c_proj.bias), l2w=c(b.ln_2.weight), l2b=c(b.ln_2.bias),
                            fw=c(b.mlp.c_fc.weight), fb=c(b.mlp.c_fc.bias), mw=c(b.mlp.c_proj.weight), mb=c(b.mlp.c_proj.bias)) for b in tr.h]
        self.lnf = (c(tr.ln_f.weight), c(tr.ln_f.bias), tr.ln_f.eps)
        norm, lin = g.gpt_inference.lm_head[0], g.gpt_inference.lm_head[1]
        self.hn = (c(norm.weight), c(norm.bias), norm.eps)
        self.hw, self.hb = c(lin.weight), c(lin.bias)
        self.mel_emb = c(g.mel_embedding.weight)
        self.mel_pos = c(g.mel_pos_embedding.emb.weight)
        dev = self.mel_emb.device
        L = len(self.blocks)
        self.tmax = tmax
        self.K = torch.zeros(L, 1, self.h, tmax, self.d, device=dev, dtype=dt)
        self.V = torch.zeros_like(self.K)
        self.ar = torch.arange(tmax, device=dev)
        # grafiğin sabit girişleri
        self.tok = torch.zeros(1, dtype=torch.long, device=dev)
        self.gi = torch.zeros(1, dtype=torch.long, device=dev)   # üretilen kodun sırası (konum embedding'i)
        self.pos = torch.zeros(1, dtype=torch.long, device=dev)  # önbellekteki yeri
        self.graph = None

    def _blok(self, b, l, x, pos_idx, mask):
        y = F.layer_norm(x, (x.shape[-1],), b["l1w"], b["l1b"], self.eps)
        qkv = torch.addmm(b["ab"], y.view(-1, y.shape[-1]), b["aw"]).view(1, -1, 3, self.h, self.d)
        q, k, v = qkv.unbind(2)
        q, k, v = q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2)
        self.K[l].index_copy_(2, pos_idx, k)
        self.V[l].index_copy_(2, pos_idx, v)
        o = F.scaled_dot_product_attention(q, self.K[l], self.V[l], attn_mask=mask)
        o = o.transpose(1, 2).reshape(-1, self.h * self.d)
        x = x + torch.addmm(b["pb"], o, b["pw"]).view_as(x)
        y = F.layer_norm(x, (x.shape[-1],), b["l2w"], b["l2b"], self.eps)
        y = torch.addmm(b["fb"], y.view(-1, y.shape[-1]), b["fw"])
        y = F.gelu(y, approximate="tanh")
        x = x + torch.addmm(b["mb"], y, b["mw"]).view_as(x)
        return x

    def _ileri(self, x, pos_idx, mask):
        for l, b in enumerate(self.blocks):
            x = self._blok(b, l, x, pos_idx, mask)
        x = F.layer_norm(x, (x.shape[-1],), self.lnf[0], self.lnf[1], self.lnf[2])
        x = F.layer_norm(x[:, -1], (x.shape[-1],), self.hn[0], self.hn[1], self.hn[2])
        return F.linear(x, self.hw, self.hb).float()

    def _adim(self):
        x = (self.mel_emb[self.tok] + self.mel_pos[self.gi]).unsqueeze(0)
        mask = (self.ar <= self.pos).view(1, 1, 1, -1)
        return self._ileri(x, self.pos, mask)

    def _kaydet(self):
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                self._adim()
        torch.cuda.current_stream().wait_stream(s)
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):
            self.logits = self._adim()

    @torch.inference_mode()
    def generate(self, cond_latents, text_inputs, temperature=0.75, top_k=50, top_p=0.85, repetition_penalty=10.0, **_):
        g = self.g
        if self.graph is None:
            self._kaydet()
        t = F.pad(text_inputs, (0, 1), value=g.stop_text_token)
        t = F.pad(t, (1, 0), value=g.start_text_token)
        pre = torch.cat([cond_latents, g.text_embedding(t) + g.text_pos_embedding(t)], dim=1).to(self.dt)
        start = g.start_audio_token
        x = torch.cat([pre, (self.mel_emb[start] + self.mel_pos[0]).view(1, 1, -1)], dim=1)
        n = x.shape[1]
        idx = self.ar[:n]
        mask = torch.zeros(1, 1, n, self.tmax, dtype=torch.bool, device=x.device)
        mask[0, 0, :, :n] = torch.tril(torch.ones(n, n, dtype=torch.bool, device=x.device))
        logits = self._ileri(x, idx, mask)
        # HF ile aynı: tekrar cezası girişteki sahte "1"lere, başlangıç koduna ve üretilenlere uygulanır
        seen = torch.zeros(logits.shape[-1], dtype=torch.bool, device=x.device)
        seen[1] = True
        seen[start] = True
        out = [start]
        stop = g.stop_audio_token
        for i in range(g.max_gen_mel_tokens):
            lg = logits[0].clone()
            if repetition_penalty != 1.0:
                pen = torch.where(lg < 0, lg * repetition_penalty, lg / repetition_penalty)
                lg = torch.where(seen, pen, lg)
            lg = lg / temperature
            if top_k:
                kth = torch.topk(lg, top_k).values[-1]
                lg = lg.masked_fill(lg < kth, -math.inf)
            if top_p < 1.0:
                srt, ix = torch.sort(lg, descending=False)
                cum = srt.softmax(-1).cumsum(-1)
                rm = cum <= (1 - top_p)
                rm[-1] = False
                lg = lg.masked_fill(rm.scatter(0, ix, rm), -math.inf)
            nxt = torch.multinomial(lg.softmax(-1), 1)
            tk = int(nxt)
            out.append(tk)
            if tk == stop:
                break
            seen[tk] = True
            self.tok.copy_(nxt)
            self.gi.fill_(i + 1)
            self.pos.fill_(n + i)
            self.graph.replay()
            logits = self.logits
        return torch.tensor([out[1:]], device=x.device)


def hizlandir(xtts, yerinde=True):
    """Konuşmacı latentleri bundan ÖNCE hesaplanmalı (koşullandırma kodlayıcısı da GPT'nin içinde)."""
    if yerinde:
        # fp32 GPT'nin yanında fp16 kopya tutmak ekran kartında ~0,75 GB fazla yer: GPT'yi fp16'ya çevir,
        # üretimden sonraki tek "latent" geçişini autocast ile çalıştır (kopya yerine aynı ağırlıklar kullanılır)
        xtts.gpt.half()
        ileri = xtts.gpt.forward
        def latent(*a, **k):
            with torch.autocast("cuda", dtype=torch.float16):
                r = ileri(*a, **k)
            return r.float() if torch.is_tensor(r) else r
        xtts.gpt.forward = latent
    h = HizliGPT(xtts)
    xtts.gpt.generate = h.generate
    return h

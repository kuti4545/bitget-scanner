"""Gösterge puanlama — 10 üzerinden, yön LONG/SHORT."""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

import config
from indicators import (
    rsi,
    macd,
    bollinger,
    vumanchu_cipher_b,
    pvg,
    last_cross,
    slope,
    sma,
    ema,
    atr,
)


@dataclass
class Signal:
    symbol: str
    price: float
    change24h: float
    volume24h: float
    direction: str
    score: float
    rsi: float
    macd_hist: float
    bb_percent: float
    wt1: float
    wt2: float
    mfi: float
    pvg: float
    vol_ratio: float
    reasons: list
    entry_low: float = 0.0
    entry_high: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    rr1: float = 0.0
    rr2: float = 0.0
    atr: float = 0.0
    style: str = "retest"
    h1_trend: str = "YOK"
    h4_trend: str = "YOK"
    regime: str = "YOK"
    yorum: str = ""
    setup: str = ""
    btc_bias: str = "YOK"
    btc_note: str = ""
    confidence: str = "ORTA"
    risk_usd: float = 0.0
    margin_usd: float = 0.0
    leverage: float = 0.0
    notional_usd: float = 0.0
    sl_loss_usd: float = 0.0
    tp1_usd: float = 0.0
    tp2_usd: float = 0.0
    skip_reason: str = ""
    high24h: float = 0.0
    low24h: float = 0.0

    def to_dict(self):
        d = asdict(self)
        d["reasons"] = self.reasons
        return d


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def analyze(symbol: str, df: pd.DataFrame, ticker: dict) -> Signal | None:
    if df is None or len(df) < 40:
        return None

    close = df["close"]
    vol = df["volume"]

    rsi_s = rsi(close, 14)
    macd_line, macd_sig, macd_hist = macd(close)
    mid, upper, lower, width, pb = bollinger(close)
    wt1, wt2, money, mf_osc = vumanchu_cipher_b(df)
    pvg_s = pvg(df, 8)
    vol_sma = sma(vol, 20)

    i = -1
    vals = {
        "rsi": float(rsi_s.iloc[i]),
        "macd_h": float(macd_hist.iloc[i]),
        "macd_h_prev": float(macd_hist.iloc[-2]),
        "pb": float(pb.iloc[i]),
        "width": float(width.iloc[i]),
        "width_sma": float(sma(width, 20).iloc[i]) if len(width) > 25 else float(width.iloc[i]),
        "wt1": float(wt1.iloc[i]),
        "wt2": float(wt2.iloc[i]),
        "mfi": float(money.iloc[i]),
        "mf_osc": float(mf_osc.iloc[i]),
        "pvg": float(pvg_s.iloc[i]),
        "vol_ratio": float(vol.iloc[i] / vol_sma.iloc[i]) if vol_sma.iloc[i] else 1.0,
        "close": float(close.iloc[i]),
        "rsi_slope": slope(rsi_s, 3),
        "hist_slope": slope(macd_hist, 3),
        "wt_cross": last_cross(wt1, wt2),
        "macd_cross": last_cross(macd_line, macd_sig),
    }
    if any(np.isnan(v) for v in vals.values() if isinstance(v, float)):
        return None

    long_pts = []
    short_pts = []
    reasons_l = []
    reasons_s = []

    # --- RSI (max 1.7) ---
    r, rs = vals["rsi"], vals["rsi_slope"]
    if r <= 30 and rs > 0:
        long_pts.append(1.7)
        reasons_l.append(f"RSI aşırı satım dönüş {r:.1f}")
    elif r <= 32:
        long_pts.append(1.2)
        reasons_l.append(f"RSI dip {r:.1f}")
    elif r < 38 and rs > 0:
        long_pts.append(0.4)
    if r >= 70 and rs < 0:
        short_pts.append(1.7)
        reasons_s.append(f"RSI aşırı alım dönüş {r:.1f}")
    elif r >= 68:
        short_pts.append(1.2)
        reasons_s.append(f"RSI tepe {r:.1f}")
    elif r > 62 and rs < 0:
        short_pts.append(0.4)

    # --- MACD (max 1.7) ---
    if vals["macd_cross"] == 1:
        long_pts.append(1.7)
        reasons_l.append("MACD yukarı kesti")
    elif vals["macd_h"] > 0 and vals["hist_slope"] > 0:
        long_pts.append(1.3)
        reasons_l.append("MACD histogram yeşil ve güçleniyor")
    elif vals["hist_slope"] > 0 and vals["macd_h"] < 0:
        long_pts.append(0.7)
        reasons_l.append("MACD histogram toparlanıyor")
    if vals["macd_cross"] == -1:
        short_pts.append(1.7)
        reasons_s.append("MACD aşağı kesti")
    elif vals["macd_h"] < 0 and vals["hist_slope"] < 0:
        short_pts.append(1.3)
        reasons_s.append("MACD histogram kırmızı ve zayıflıyor")
    elif vals["hist_slope"] < 0 and vals["macd_h"] > 0:
        short_pts.append(0.7)
        reasons_s.append("MACD histogram zayıflıyor")

    # --- Hacim (max 1.4) ---
    vr = vals["vol_ratio"]
    last_ret = float(close.iloc[-1] / close.iloc[-2] - 1)
    if vr >= 1.8 and last_ret > 0:
        long_pts.append(1.4)
        reasons_l.append(f"Hacim patlaması x{vr:.1f} + yeşil mum")
    elif vr >= 1.3 and last_ret > 0:
        long_pts.append(0.9)
        reasons_l.append(f"Hacim ortalamanın üstünde x{vr:.1f}")
    if vr >= 1.8 and last_ret < 0:
        short_pts.append(1.4)
        reasons_s.append(f"Hacim patlaması x{vr:.1f} + kırmızı mum")
    elif vr >= 1.3 and last_ret < 0:
        short_pts.append(0.9)
        reasons_s.append(f"Hacim ortalamanın üstünde x{vr:.1f}")

    # --- Bollinger (max 1.6) ---
    pbv, w, ws = vals["pb"], vals["width"], vals["width_sma"]
    squeeze = w < ws * 0.75
    if pbv <= 0.12:
        long_pts.append(1.6)
        reasons_l.append("Fiyat alt Bollinger bandında")
    elif pbv <= 0.30 and last_ret > 0:
        long_pts.append(1.0)
        reasons_l.append("Alt banda yakın tepki")
    elif squeeze and pbv > 0.55 and last_ret > 0:
        long_pts.append(1.1)
        reasons_l.append("Bollinger sıkışma sonrası yukarı")
    if pbv >= 0.88:
        short_pts.append(1.6)
        reasons_s.append("Fiyat üst Bollinger bandında")
    elif pbv >= 0.70 and last_ret < 0:
        short_pts.append(1.0)
        reasons_s.append("Üst banda yakın red")
    elif squeeze and pbv < 0.45 and last_ret < 0:
        short_pts.append(1.1)
        reasons_s.append("Bollinger sıkışma sonrası aşağı")

    # --- VuManChu Cipher B (max 2.0) ---
    w1, w2, mfi_v = vals["wt1"], vals["wt2"], vals["mfi"]
    xc = vals["wt_cross"]
    if xc == 1 and w1 <= -53:
        long_pts.append(2.0)
        reasons_l.append(f"VuManChu yeşil nokta (WT {w1:.0f})")
    elif xc == 1 and w1 < 0:
        long_pts.append(1.3)
        reasons_l.append("VuManChu WT yukarı kesti")
    elif w1 > w2 and w1 < -40:
        long_pts.append(0.8)
        reasons_l.append("VuManChu oversold toparlanma")
    if mfi_v >= 55 and (xc == 1 or w1 > w2):
        long_pts.append(0.4)
        reasons_l.append(f"VuManChu para girişi MFI {mfi_v:.0f}")
    if xc == -1 and w1 >= 53:
        short_pts.append(2.0)
        reasons_s.append(f"VuManChu kırmızı nokta (WT {w1:.0f})")
    elif xc == -1 and w1 > 0:
        short_pts.append(1.3)
        reasons_s.append("VuManChu WT aşağı kesti")
    elif w1 < w2 and w1 > 40:
        short_pts.append(0.8)
        reasons_s.append("VuManChu overbought zayıflama")
    if mfi_v <= 45 and (xc == -1 or w1 < w2):
        short_pts.append(0.4)
        reasons_s.append(f"VuManChu para çıkışı MFI {mfi_v:.0f}")

    # --- PVG (max 1.6) ---
    pv = vals["pvg"]
    if pv > 0.012:
        long_pts.append(_clamp(1.0 + pv * 20, 1.0, 1.6))
        reasons_l.append(f"PVG pozitif {pv:.3f}")
    elif pv > 0.004:
        long_pts.append(0.6)
    if pv < -0.012:
        short_pts.append(_clamp(1.0 + abs(pv) * 20, 1.0, 1.6))
        reasons_s.append(f"PVG negatif {pv:.3f}")
    elif pv < -0.004:
        short_pts.append(0.6)

    long_score = _clamp(sum(long_pts), 0, 10)
    short_score = _clamp(sum(short_pts), 0, 10)

    if long_score == 0 and short_score == 0:
        return None
    if long_score >= short_score:
        direction, score, reasons = "LONG", long_score, reasons_l
    else:
        direction, score, reasons = "SHORT", short_score, reasons_s

    try:
        chg = float(ticker.get("change24h") or 0) * 100
    except (TypeError, ValueError):
        chg = 0.0
    try:
        vol24 = float(ticker.get("usdtVolume") or 0)
    except (TypeError, ValueError):
        vol24 = 0.0
    try:
        high24 = float(ticker.get("high24h") or 0)
    except (TypeError, ValueError):
        high24 = 0.0
    try:
        low24 = float(ticker.get("low24h") or 0)
    except (TypeError, ValueError):
        low24 = 0.0

    return Signal(
        symbol=symbol,
        price=vals["close"],
        change24h=round(chg, 2),
        volume24h=vol24,
        high24h=high24,
        low24h=low24,
        direction=direction,
        score=round(score, 2),
        rsi=round(vals["rsi"], 1),
        macd_hist=round(vals["macd_h"], 6),
        bb_percent=round(vals["pb"], 2),
        wt1=round(vals["wt1"], 1),
        wt2=round(vals["wt2"], 1),
        mfi=round(vals["mfi"], 1),
        pvg=round(vals["pvg"], 4),
        vol_ratio=round(vals["vol_ratio"], 2),
        reasons=reasons[:5],
    )


def _px(price: float) -> float:
    p = abs(price)
    if p >= 1000:
        return round(price, 2)
    if p >= 100:
        return round(price, 3)
    if p >= 1:
        return round(price, 4)
    if p >= 0.01:
        return round(price, 6)
    return round(price, 8)


def hour_trend(df_1h: pd.DataFrame | None) -> str:
    if df_1h is None or len(df_1h) < 55:
        return "YOK"
    e20 = ema(df_1h["close"], 20)
    e50 = ema(df_1h["close"], 50)
    c = float(df_1h["close"].iloc[-1])
    a, b = float(e20.iloc[-1]), float(e50.iloc[-1])
    if c > a > b:
        return "YUKARI"
    if c < a < b:
        return "AŞAĞI"
    if c > a:
        return "ZAYIF YUKARI"
    if c < a:
        return "ZAYIF AŞAĞI"
    return "YATAY"


def _local_extrema(series: pd.Series, order: int = 3):
    lows, highs = [], []
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    for i in range(order, n - order):
        w = vals[i - order : i + order + 1]
        if np.isnan(w).any():
            continue
        if vals[i] <= w.min():
            lows.append(i)
        if vals[i] >= w.max():
            highs.append(i)
    return lows, highs


def reversal_flags(df: pd.DataFrame) -> dict:
    """Dip/tepe teyidi: fitil, RSI diverjans, WT ekstrem, hacim klimaks."""
    out = {"dip": 0.0, "tepe": 0.0, "tags": []}
    if len(df) < 30:
        return out
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]
    rsi_s = rsi(c, 14)
    wt1, wt2, money, _ = vumanchu_cipher_b(df)
    *_, pb = bollinger(c)
    rng = (h.iloc[-1] - l.iloc[-1]) or 1e-12
    lower_wick = min(o.iloc[-1], c.iloc[-1]) - l.iloc[-1]
    upper_wick = h.iloc[-1] - max(o.iloc[-1], c.iloc[-1])
    vol_ratio = float(v.iloc[-1] / sma(v, 20).iloc[-1]) if sma(v, 20).iloc[-1] else 1.0
    bull = c.iloc[-1] > o.iloc[-1]
    bear = c.iloc[-1] < o.iloc[-1]

    if float(rsi_s.iloc[-1]) <= 32:
        out["dip"] += 0.6
        out["tags"].append(f"RSI dip bölgesi {rsi_s.iloc[-1]:.0f}")
    if float(rsi_s.iloc[-1]) >= 68:
        out["tepe"] += 0.6
        out["tags"].append(f"RSI tepe bölgesi {rsi_s.iloc[-1]:.0f}")
    if float(wt1.iloc[-1]) <= -53:
        out["dip"] += 0.8
        out["tags"].append("VuManChu oversold")
    if float(wt1.iloc[-1]) >= 53:
        out["tepe"] += 0.8
        out["tags"].append("VuManChu overbought")
    if float(pb.iloc[-1]) <= 0.08:
        out["dip"] += 0.5
        out["tags"].append("Alt banda yapışık")
    if float(pb.iloc[-1]) >= 0.92:
        out["tepe"] += 0.5
        out["tags"].append("Üst banda yapışık")
    if lower_wick / rng >= 0.45 and bull:
        out["dip"] += 0.7
        out["tags"].append("Alt fitil reddi")
    if upper_wick / rng >= 0.45 and bear:
        out["tepe"] += 0.7
        out["tags"].append("Üst fitil reddi")
    if vol_ratio >= 1.8 and bull and float(rsi_s.iloc[-1]) < 45:
        out["dip"] += 0.4
        out["tags"].append("Dipte hacim klimaks")
    if vol_ratio >= 1.8 and bear and float(rsi_s.iloc[-1]) > 55:
        out["tepe"] += 0.4
        out["tags"].append("Tepede hacim klimaks")

    lows, highs = _local_extrema(c, 3)
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if c.iloc[i2] < c.iloc[i1] and rsi_s.iloc[i2] > rsi_s.iloc[i1] + 1:
            out["dip"] += 1.0
            out["tags"].append("RSI pozitif diverjans")
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if c.iloc[i2] > c.iloc[i1] and rsi_s.iloc[i2] < rsi_s.iloc[i1] - 1:
            out["tepe"] += 1.0
            out["tags"].append("RSI negatif diverjans")
    return out


def btc_bias(df15: pd.DataFrame | None, df1h: pd.DataFrame | None) -> tuple[str, str]:
    if df15 is None or len(df15) < 20:
        return "YOK", "BTC verisi yok."
    r4 = float(df15["close"].iloc[-1] / df15["close"].iloc[-5] - 1)
    r1 = float(df15["close"].iloc[-1] / df15["close"].iloc[-2] - 1)
    rsi_b = float(rsi(df15["close"], 14).iloc[-1])
    h1 = hour_trend(df1h)
    if r4 <= -0.012 or r1 <= -0.006:
        bias = "DUMP"
    elif r4 >= 0.012 or r1 >= 0.006:
        bias = "PUMP"
    elif "YUKARI" in h1:
        bias = "YUKARI"
    elif "AŞAĞI" in h1:
        bias = "AŞAĞI"
    else:
        bias = "YATAY"
    note = (
        f"BTC 15m son 4 mum {r4*100:+.2f}%, son mum {r1*100:+.2f}%, "
        f"RSI {rsi_b:.0f}, 1H {h1}."
    )
    return bias, note


def size_position(sig: Signal) -> Signal:
    entry = (sig.entry_low + sig.entry_high) / 2 or sig.price
    sl_pct = abs(entry - sig.sl) / entry if entry else 0.01
    sl_pct = max(sl_pct, 0.004)

    high_setup = sig.setup in ("DIP", "TEPE") and sig.score >= 7.4
    mid_setup = sig.score >= 7.0
    against_btc = (
        (sig.direction == "LONG" and sig.btc_bias == "DUMP")
        or (sig.direction == "SHORT" and sig.btc_bias == "PUMP")
    )
    with_btc = (
        (sig.direction == "LONG" and sig.btc_bias in ("PUMP", "YUKARI"))
        or (sig.direction == "SHORT" and sig.btc_bias in ("DUMP", "AŞAĞI"))
    )

    against_1h = (
        (sig.direction == "LONG" and sig.h1_trend.startswith("AŞAĞI"))
        or (sig.direction == "SHORT" and sig.h1_trend.startswith("YUKARI"))
    )
    weak_vol = sig.vol_ratio < 1.0

    if against_btc or sig.style == "kaçtı-retest-bekle" or against_1h:
        sig.confidence = "DÜŞÜK"
        risk_pct = config.RISK_PCT_LOW
        max_lev = config.MAX_LEVERAGE_LOW
        if against_btc and sig.score < 7.2:
            sig.skip_reason = "BTC ters, fırsat zayıf. Bekle."
    elif high_setup and with_btc and not weak_vol and sig.symbol == "BTCUSDT":
        sig.confidence = "YÜKSEK"
        risk_pct = config.RISK_PCT_HIGH
        max_lev = config.MAX_LEVERAGE_BTC
    elif high_setup and with_btc and not weak_vol:
        sig.confidence = "YÜKSEK"
        risk_pct = config.RISK_PCT_MID
        max_lev = config.MAX_LEVERAGE_MID
    elif mid_setup or with_btc:
        sig.confidence = "ORTA+"
        risk_pct = config.RISK_PCT_MID
        max_lev = config.MAX_LEVERAGE_MID
    else:
        sig.confidence = "ORTA"
        risk_pct = config.RISK_PCT_LOW
        max_lev = config.MAX_LEVERAGE_LOW
    if weak_vol and sig.confidence == "YÜKSEK":
        sig.confidence = "ORTA+"
        max_lev = min(max_lev, config.MAX_LEVERAGE_MID)

    equity = config.ACCOUNT_EQUITY
    risk_usd = equity * risk_pct
    notional = min(risk_usd / sl_pct, equity * max_lev * 0.5)
    margin_cap = equity * 0.22
    margin = min(margin_cap, max(config.MIN_MARGIN_USD, notional / float(max_lev)))
    lev = min(float(max_lev), notional / margin) if margin else 2.0
    notional = margin * lev
    sl_loss = notional * sl_pct
    tp1 = sl_loss * 1.5
    tp2 = sl_loss * 2.5

    sig.risk_usd = round(sl_loss, 2)
    sig.margin_usd = round(margin, 2)
    sig.leverage = round(lev, 1)
    sig.notional_usd = round(notional, 2)
    sig.sl_loss_usd = round(sl_loss, 2)
    sig.tp1_usd = round(tp1, 2)
    sig.tp2_usd = round(tp2, 2)
    return sig


def attach_plan(
    sig: Signal,
    df: pd.DataFrame,
    df_1h: pd.DataFrame | None = None,
    btc_15: pd.DataFrame | None = None,
    btc_1h: pd.DataFrame | None = None,
    df_4h: pd.DataFrame | None = None,
) -> Signal:
    """Tahtacı usulü: dip/tepe, BTC filtresi, 300$ risk."""
    price = float(df["close"].iloc[-1])
    atr_s = atr(df, 14)
    a = float(atr_s.iloc[-1]) if len(atr_s) else price * 0.008
    if not a or a <= 0:
        a = price * 0.008

    look = min(16, len(df))
    swing_lo = float(df["low"].iloc[-look:].min())
    swing_hi = float(df["high"].iloc[-look:].max())
    mid = float(sma(df["close"], 20).iloc[-1])
    sig.h1_trend = hour_trend(df_1h)
    sig.h4_trend = hour_trend(df_4h)
    if sig.h4_trend in ("YUKARI", "AŞAĞI"):
        sig.regime = "TREND"
    elif sig.h4_trend in ("ZAYIF YUKARI", "ZAYIF AŞAĞI", "YATAY"):
        sig.regime = "RANGE"
    else:
        sig.regime = "YOK"
    sig.atr = _px(a)

    if sig.direction == "LONG":
        ideal = min(price, max(swing_lo + 0.15 * a, mid - 0.35 * a, price - 0.45 * a))
        entry_lo, entry_hi = ideal, min(price, ideal + 0.35 * a)
        if entry_hi < entry_lo:
            entry_lo, entry_hi = entry_hi, entry_lo
        sl = min(swing_lo, entry_lo) - 0.25 * a
        risk = entry_hi - sl
        if risk <= 0:
            risk = 1.2 * a
            sl = entry_lo - risk
        tp1 = entry_hi + 1.5 * risk
        tp2 = entry_hi + 2.5 * risk
        stretched = price > entry_hi + 0.35 * a
    else:
        ideal = max(price, min(swing_hi - 0.15 * a, mid + 0.35 * a, price + 0.45 * a))
        entry_lo, entry_hi = max(price, ideal - 0.35 * a), ideal
        if entry_hi < entry_lo:
            entry_lo, entry_hi = entry_hi, entry_lo
        sl = max(swing_hi, entry_hi) + 0.25 * a
        risk = sl - entry_lo
        if risk <= 0:
            risk = 1.2 * a
            sl = entry_hi + risk
        tp1 = entry_lo - 1.5 * risk
        tp2 = entry_lo - 2.5 * risk
        stretched = price < entry_lo - 0.35 * a

    if stretched:
        sig.style = "kaçtı-retest-bekle"
    elif abs(price - ((entry_lo + entry_hi) / 2)) <= 0.2 * a:
        sig.style = "bölgede-limit"
    else:
        sig.style = "retest-bekle"

    against = (
        (sig.direction == "LONG" and sig.h1_trend.startswith("AŞAĞI"))
        or (sig.direction == "SHORT" and sig.h1_trend.startswith("YUKARI"))
    )
    with_trend = (
        (sig.direction == "LONG" and "YUKARI" in sig.h1_trend)
        or (sig.direction == "SHORT" and "AŞAĞI" in sig.h1_trend)
    )
    if against:
        sig.score = round(max(sig.score - 1.5, 0), 2)
    against_4h = (
        (sig.direction == "LONG" and sig.h4_trend == "AŞAĞI")
        or (sig.direction == "SHORT" and sig.h4_trend == "YUKARI")
    )
    with_4h = (
        (sig.direction == "LONG" and "YUKARI" in sig.h4_trend)
        or (sig.direction == "SHORT" and "AŞAĞI" in sig.h4_trend)
    )
    if against_4h:
        sig.score = round(max(sig.score - 2.0, 0), 2)
        sig.skip_reason = sig.skip_reason or "4H ters yon, islem yok."

    rev = reversal_flags(df)
    rsi_now = float(sig.rsi)
    wt_now = float(sig.wt1)
    # DIP: RSI gerçek dip + VuManChu oversold. Sadece WT yetmez (BTW 41 RSI).
    if (
        sig.direction == "LONG"
        and rev["dip"] >= 1.2
        and rsi_now <= 32
        and wt_now <= -53
    ):
        sig.setup = "DIP"
        sig.score = round(min(10.0, sig.score + min(rev["dip"], 1.6)), 2)
        sig.reasons = (rev["tags"][:2] + sig.reasons)[:5]
    elif (
        sig.direction == "SHORT"
        and rev["tepe"] >= 1.2
        and rsi_now >= 68
        and wt_now >= 53
    ):
        sig.setup = "TEPE"
        sig.score = round(min(10.0, sig.score + min(rev["tepe"], 1.6)), 2)
        sig.reasons = (rev["tags"][:2] + sig.reasons)[:5]
    else:
        sig.setup = "MOMENTUM"
    if with_4h and sig.setup in ("DIP", "TEPE"):
        sig.score = round(min(10.0, sig.score + 0.3), 2)
    # Hacim tavanı dip/tepe bonusundan SONRA. Yoksa RSI 23 + x0.3 hacim 7.9 oluyor.
    if sig.vol_ratio < 1.0:
        sig.score = round(min(sig.score, 6.6), 2)
        if sig.confidence == "YÜKSEK":
            sig.confidence = "ORTA"

    sig.btc_bias, sig.btc_note = btc_bias(btc_15, btc_1h)
    if sig.symbol.startswith("BTC"):
        sig.btc_note = "Bu BTC'nin kendisi."
    elif sig.direction == "LONG" and sig.btc_bias == "DUMP":
        sig.score = round(max(sig.score - 1.0, 0), 2)
    elif sig.direction == "SHORT" and sig.btc_bias == "PUMP":
        sig.score = round(max(sig.score - 1.0, 0), 2)
    elif sig.direction == "LONG" and sig.btc_bias in ("PUMP", "YUKARI") and sig.setup == "DIP":
        sig.score = round(min(10.0, sig.score + 0.4), 2)
    elif sig.direction == "SHORT" and sig.btc_bias in ("DUMP", "AŞAĞI") and sig.setup == "TEPE":
        sig.score = round(min(10.0, sig.score + 0.4), 2)

    sig.entry_low = _px(entry_lo)
    sig.entry_high = _px(entry_hi)
    sig.sl = _px(sl)
    sig.tp1 = _px(tp1)
    sig.tp2 = _px(tp2)
    risk_px = abs((entry_hi if sig.direction == "LONG" else entry_lo) - sl)
    sig.rr1 = 1.5 if risk_px else 0
    sig.rr2 = 2.5 if risk_px else 0

    size_position(sig)

    bits = []
    if sig.setup == "DIP":
        bits.append("Dip teyidi var: kovalama, bölgede long.")
    elif sig.setup == "TEPE":
        bits.append("Tepe teyidi var: kovalama, bölgede short.")
    else:
        bits.append("Dip/tepe teyidi zayıf; momentum işi, daha küçük boyut.")
    bits.append(sig.btc_note)
    if not sig.symbol.startswith("BTC"):
        if sig.direction == "LONG" and sig.btc_bias == "DUMP":
            bits.append("BTC dökülüyor; alt long erken kalır.")
        elif sig.direction == "SHORT" and sig.btc_bias == "PUMP":
            bits.append("BTC pompalıyor; alt short ezilir.")
        elif sig.setup == "DIP" and sig.btc_bias in ("PUMP", "YUKARI"):
            bits.append("BTC toparlıyor, alt dip senaryosu güçlenir.")
        elif sig.setup == "TEPE" and sig.btc_bias in ("DUMP", "AŞAĞI"):
            bits.append("BTC zayıf, alt tepe short uyumlu.")
    bits.append(f"4H {sig.h4_trend} rejim {sig.regime}.")
    if with_trend:
        bits.append(f"Coin 1H {sig.h1_trend}, sinyal ile aynı yön.")
    elif against:
        bits.append(f"Coin 1H {sig.h1_trend}, sinyale ters.")
    if against_4h:
        bits.append("4H ters; bu setup MAGMA tipi, ele.")
    elif with_4h:
        bits.append("4H ile aynı yön.")
    if sig.style == "kaçtı-retest-bekle":
        bits.append("Fiyat entryi geçmiş. Market kovalama.")
    elif sig.style == "bölgede-limit":
        bits.append("Fiyat entry bandında. Limit koy.")
    else:
        bits.append("Retest bekle.")
    if sig.skip_reason:
        bits.append(sig.skip_reason)
    sig.yorum = " ".join(bits)
    return sig

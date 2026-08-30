"""MACD, RSI, hacim, Bollinger, VuManChu Cipher B, PVG."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    au = up.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    ad = down.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = au / ad.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = sma(close, n)
    std = close.rolling(n).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower) / mid.replace(0, np.nan)
    percent_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return mid, upper, lower, width, percent_b


def mfi(high, low, close, volume, n=14) -> pd.Series:
    tp = (high + low + close) / 3
    mf = tp * volume
    delta = tp.diff()
    pos = mf.where(delta > 0, 0.0)
    neg = mf.where(delta < 0, 0.0)
    pos_sum = pos.rolling(n).sum()
    neg_sum = neg.rolling(n).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def vumanchu_cipher_b(df: pd.DataFrame):
    """WaveTrend + MFI (VuManChu Cipher B çekirdeği)."""
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
    esa = ema(hlc3, 9)
    de = ema((hlc3 - esa).abs(), 9)
    ci = (hlc3 - esa) / (0.015 * de.replace(0, np.nan))
    wt1 = ema(ci, 12)
    wt2 = sma(wt1, 3)
    money = mfi(df["high"], df["low"], df["close"], df["volume"], 14)
    # Cipher B'deki yeşil/kırmızı alan için 0 etrafı MFI-50
    mf_osc = money - 50
    return wt1, wt2, money, mf_osc


def pvg(df: pd.DataFrame, lookback: int = 8) -> pd.Series:
    """
    PVG = Price-Volume Growth.
    Fiyat değişimi ile hacim büyümesini aynı yöne zorlar.
    Pozitif: fiyat artarken hacim de artıyor (alım baskısı).
    Negatif: fiyat düşerken hacim artıyor (satım baskısı).
    """
    ret = df["close"].pct_change(lookback)
    vol_sma = sma(df["volume"], lookback)
    vol_growth = df["volume"] / vol_sma.replace(0, np.nan) - 1
    return ret * (1 + vol_growth.clip(-1, 3))


def last_cross(fast: pd.Series, slow: pd.Series) -> int:
    """Son barda yukarı kesişim +1, aşağı -1, yok 0."""
    if len(fast) < 3:
        return 0
    f1, f0 = float(fast.iloc[-2]), float(fast.iloc[-1])
    s1, s0 = float(slow.iloc[-2]), float(slow.iloc[-1])
    if np.isnan([f1, f0, s1, s0]).any():
        return 0
    if f1 <= s1 and f0 > s0:
        return 1
    if f1 >= s1 and f0 < s0:
        return -1
    return 0


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev).abs(),
            (df["low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def slope(s: pd.Series, n: int = 3) -> float:
    if len(s) < n + 1:
        return 0.0
    a = s.iloc[-n:]
    if a.isna().any():
        return 0.0
    return float(a.iloc[-1] - a.iloc[0])

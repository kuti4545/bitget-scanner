#!/usr/bin/env python3
"""Bitget USDT-M tarayıcı. GitHub Actions veya local çalışır."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

import config
from score import analyze, attach_plan

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bitget-leverage-scanner/1.0"})
TR_TZ = timezone(timedelta(hours=3))
BTC_15 = None
BTC_1H = None


def get_tickers() -> list[dict]:
    url = f"{config.BITGET_BASE}/api/v2/mix/market/tickers"
    r = SESSION.get(url, params={"productType": config.PRODUCT_TYPE}, timeout=20)
    r.raise_for_status()
    body = r.json()
    if body.get("code") != "00000":
        raise RuntimeError(body)
    rows = body.get("data") or []
    out = []
    for row in rows:
        try:
            vol = float(row.get("usdtVolume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        if vol < config.MIN_USDT_VOLUME_24H:
            continue
        out.append(row)
    out.sort(key=lambda x: float(x.get("usdtVolume") or 0), reverse=True)
    return out[: config.MAX_SYMBOLS]


def get_candles(symbol: str, granularity: str | None = None, limit: int | None = None) -> pd.DataFrame | None:
    url = f"{config.BITGET_BASE}/api/v2/mix/market/candles"
    params = {
        "symbol": symbol,
        "granularity": granularity or config.TIMEFRAME,
        "limit": str(limit or config.CANDLE_LIMIT),
        "productType": config.PRODUCT_TYPE,
    }
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != "00000":
            return None
        raw = body.get("data") or []
        if len(raw) < 40:
            return None
        df = pd.DataFrame(
            raw,
            columns=["ts", "open", "high", "low", "close", "base_vol", "quote_vol"],
        )
        for col in ["open", "high", "low", "close", "base_vol", "quote_vol"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
        df = df.dropna().sort_values("ts").reset_index(drop=True)
        df["volume"] = df["base_vol"]
        # Sadece kisa TF kapanmamis mumu at. 1H/4H atilirsa trend 3 saat gecikir (SPY hatasi).
        if params["granularity"] in ("5m", "15m", "30m"):
            df = drop_unclosed(df, params["granularity"])
        if df is None or len(df) < 40:
            return None
        return df
    except requests.RequestException:
        return None


GRAN_MS = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1H": 60 * 60 * 1000,
    "4H": 4 * 60 * 60 * 1000,
}


def drop_unclosed(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    """Oluşan mumu at: MAGMA tipi yarıda 8.0 olmasın."""
    width = GRAN_MS.get(granularity)
    if not width or df.empty:
        return df
    last_open = int(df["ts"].iloc[-1])
    now_ms = int(time.time() * 1000)
    if now_ms < last_open + width - 8000:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def load_state() -> dict:
    path = Path(config.STATE_PATH)
    if not path.exists():
        return {"alerts": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"alerts": {}}


def save_json(path: str, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cooldown_ok(state: dict, symbol: str, direction: str) -> bool:
    """Ayni coin herhangi bir yon 3s icinde tekrar etmesin (KORU long+short)."""
    alerts = state.get("alerts") or {}
    now = datetime.now(timezone.utc)
    wait = timedelta(minutes=max(config.ALERT_COOLDOWN_MIN, 5))
    for key, last in alerts.items():
        if not key.startswith(f"{symbol}:"):
            continue
        try:
            last_ts = datetime.fromisoformat(last)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - last_ts < wait:
            return False
    return True


def mark_alert(state: dict, sig) -> None:
    state.setdefault("alerts", {})
    state["alerts"][f"{sig.symbol}:{sig.direction}"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("journal", [])
    state["journal"].append(
        {
            "symbol": sig.symbol,
            "direction": sig.direction,
            "score": sig.score,
            "setup": sig.setup,
            "regime": getattr(sig, "regime", ""),
            "h4": getattr(sig, "h4_trend", ""),
            "price": sig.price,
            "sl": sig.sl,
            "tp1": sig.tp1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "p2h": None,
            "p8h": None,
            "r2h": None,
            "r8h": None,
        }
    )
    state["journal"] = state["journal"][-40:]
    if sig.style in ("retest-bekle", "kaçtı-retest-bekle"):
        state.setdefault("pending", [])
        state["pending"] = [
            p for p in state["pending"]
            if not (p.get("symbol") == sig.symbol and p.get("direction") == sig.direction)
        ]
        state["pending"].append(
            {
                "symbol": sig.symbol,
                "direction": sig.direction,
                "entry_low": sig.entry_low,
                "entry_high": sig.entry_high,
                "sl": sig.sl,
                "tp1": sig.tp1,
                "tp2": sig.tp2,
                "score": sig.score,
                "setup": sig.setup,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        state["pending"] = state["pending"][-20:]


def format_now_enter(p: dict, price: float) -> str:
    arrow = "🟢 LONG" if p["direction"] == "LONG" else "🔴 SHORT"
    return (
        f"⏰ <b>ŞİMDİ GİR</b>  {arrow}  <b>{p['symbol']}</b>  [{p.get('setup','')}]\n"
        f"Fiyat bandına geldi: <b>{price}</b>\n"
        f"Entry: {p['entry_low']} – {p['entry_high']}\n"
        f"SL: <b>{p['sl']}</b>   TP1: {p['tp1']}   TP2: {p.get('tp2','')}\n"
        f"Kovalama bititi, limit/market küçük boy. SL aynı saniye."
    )


def check_pending(state: dict, tickers: list[dict]) -> list[str]:
    """Beklenen entry gelince ikinci uyari."""
    by_sym = {t.get("symbol"): t for t in tickers}
    now = datetime.now(timezone.utc)
    keep = []
    fired = []
    for p in state.get("pending") or []:
        try:
            ts = datetime.fromisoformat(p["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if now - ts > timedelta(hours=8):
            print("pending sure doldu", p.get("symbol"))
            continue
        row = by_sym.get(p["symbol"])
        if not row:
            keep.append(p)
            continue
        try:
            px = float(row.get("lastPr") or 0)
        except (TypeError, ValueError):
            keep.append(p)
            continue
        lo, hi, sl = float(p["entry_low"]), float(p["entry_high"]), float(p["sl"])
        if lo > hi:
            lo, hi = hi, lo
        if p["direction"] == "LONG":
            stopped = sl and px <= sl
            hit = lo <= px <= hi * 1.001
        else:
            stopped = sl and px >= sl
            hit = lo * 0.999 <= px <= hi
        if stopped:
            print("pending SL", p["symbol"], px)
            continue
        if hit:
            send_telegram(format_now_enter(p, px))
            fired.append(f"{p['symbol']} {p['direction']} {px}")
            continue
        keep.append(p)
    state["pending"] = keep
    return fired


def _ret(entry: float, last: float, direction: str) -> float:
    if not entry:
        return 0.0
    raw = (last / entry - 1) * 100
    return raw if direction == "LONG" else -raw


def update_journal(state: dict) -> list[str]:
    """2s ve 8s sonra fiyatı yaz, Telegram ozeti icin satir uret."""
    notes = []
    now = datetime.now(timezone.utc)
    for row in state.get("journal") or []:
        try:
            ts = datetime.fromisoformat(row["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        age_h = (now - ts).total_seconds() / 3600
        need_2 = age_h >= 2 and row.get("p2h") is None
        need_8 = age_h >= 8 and row.get("p8h") is None
        if not need_2 and not need_8:
            continue
        df = get_candles(row["symbol"], granularity="15m", limit=80)
        if df is None or df.empty:
            continue
        last = float(df["close"].iloc[-1])
        d = row["direction"]
        if need_2:
            row["p2h"] = last
            row["r2h"] = round(_ret(row["price"], last, d), 2)
            notes.append(f"{row['symbol']} {d} 2s {row['r2h']:+.2f}%")
        if need_8:
            row["p8h"] = last
            row["r8h"] = round(_ret(row["price"], last, d), 2)
            notes.append(f"{row['symbol']} {d} 8s {row['r8h']:+.2f}%")
    return notes


def send_telegram(text: str) -> bool:
    token = config.TELEGRAM_BOT_TOKEN
    chat = config.TELEGRAM_CHAT_ID
    if not token or not chat:
        print("Telegram ayarlı değil, mesaj basılıyor:\n", text)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = SESSION.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            print("Telegram hata:", r.text[:300])
            return False
        return True
    except requests.RequestException as exc:
        print("Telegram exception:", exc)
        return False


def format_alert(sig) -> str:
    arrow = "🟢 LONG" if sig.direction == "LONG" else "🔴 SHORT"
    setup = sig.setup or "MOMENTUM"
    vol_m = sig.volume24h / 1_000_000
    reasons = "\n".join(f"• {x}" for x in sig.reasons) or "• Confluence"
    style_tr = {
        "kaçtı-retest-bekle": "KAÇTI — retest bekle, kovalama",
        "bölgede-limit": "BÖLGEDE — limit emir",
        "retest-bekle": "RETEST BEKLE — market kovalama",
    }.get(sig.style, sig.style)
    skip = f"\n⚠ {sig.skip_reason}\n" if sig.skip_reason else ""
    return (
        f"{arrow}  <b>{sig.symbol}</b>  [{setup}]  güven: <b>{sig.confidence}</b>\n"
        f"Puan: <b>{sig.score}</b>/10   TF: {config.TIMEFRAME}+1H+4H   BTC: {sig.btc_bias}\n"
        f"4H: {getattr(sig,'h4_trend','YOK')}   Rejim: {getattr(sig,'regime','YOK')}\n"
        f"Fiyat: <b>{sig.price}</b>   24s: {sig.change24h:+.2f}%   {vol_m:.1f}M\n"
        f"{skip}"
        f"\n"
        f"<b>Plan</b>\n"
        f"Stil: {style_tr}\n"
        f"Entry: <b>{sig.entry_low} – {sig.entry_high}</b>\n"
        f"SL: <b>{sig.sl}</b>\n"
        f"TP1: <b>{sig.tp1}</b>  |  TP2: <b>{sig.tp2}</b>\n"
        f"\n"
        f"<b>300$ hesap</b>\n"
        f"Marj: <b>${sig.margin_usd}</b>\n"
        f"Kaldıraç: <b>{sig.leverage}x</b>\n"
        f"Nominal: ${sig.notional_usd}\n"
        f"SL olursa kayıp ≈ <b>${sig.sl_loss_usd}</b>\n"
        f"TP1 ≈ +${sig.tp1_usd}   TP2 ≈ +${sig.tp2_usd}\n"
        f"\n"
        f"<b>Yorum</b>\n"
        f"{sig.yorum}\n"
        f"\n"
        f"<b>Göstergeler</b>\n"
        f"RSI {sig.rsi} | WT {sig.wt1}/{sig.wt2} | MFI {sig.mfi}\n"
        f"%B {sig.bb_percent} | PVG {sig.pvg} | Vol x{sig.vol_ratio}\n"
        f"{reasons}\n"
        f"\n"
        f"<i>Sinyal tavsiye değildir. 300$ hesapta 10x üstü yok. SL’siz girme.</i>"
    )


SKIP_SYMBOLS = {
    "SPYUSDT", "QQQUSDT", "TSLAUSDT", "NVDAUSDT", "AAPLUSDT",
    "MSFTUSDT", "AMZNUSDT", "METAUSDT", "GOOGUSDT", "MSTRUSDT",
    "COINUSDT", "SOXLUSDT", "SOXSUSDT", "TQQQUSDT", "SPXUSDT", "SPCXUSDT",
    "JP225USDT", "NAS100USDT", "US30USDT", "MUUSDT", "SKHYUSDT",
    "SKHYNIXUSDT", "AMDUSDT", "INTCUSDT", "CRCLUSDT",
}


def quality_gate(sig) -> str | None:
    """Sıkı kapı: spam ve MAGMA tipi 8.0 falling-knife kesilir."""
    if sig.symbol in SKIP_SYMBOLS:
        return "hisse/endeks tarayicida yok"
    if sig.score < config.ALERT_SCORE:
        return f"puan {sig.score}<{config.ALERT_SCORE}"
    if sig.confidence == "DÜŞÜK":
        return "guven dusuk"
    # kacti/retest ilk mesaj gitsin; band gelince "SIMDI GIR" ayrica gelir.
    if sig.setup == "MOMENTUM":
        return "sadece momentum"
    if sig.direction == "LONG" and sig.setup == "DIP":
        if sig.rsi > 32:
            return "DIP ama RSI dip degil"
        if sig.wt1 > -53:
            return "DIP ama VuManChu desteklemiyor"
    if sig.direction == "SHORT" and sig.setup == "TEPE":
        if sig.rsi < 68:
            return "TEPE ama RSI tepe degil"
        if sig.wt1 < 53:
            return "TEPE ama VuManChu desteklemiyor"
    if sig.direction == "SHORT" and sig.h1_trend == "YUKARI":
        return "short ama 1H net yukari"
    if sig.direction == "LONG" and sig.h1_trend == "AŞAĞI":
        return "long ama 1H net asagi"
    if sig.symbol != "BTCUSDT":
        if sig.direction == "SHORT" and sig.btc_bias == "PUMP":
            return "alt short BTC pompa"
        if sig.direction == "LONG" and sig.btc_bias == "DUMP":
            return "alt long BTC dump"
    if sig.direction == "SHORT" and sig.change24h >= 10:
        return "pompada short yok"
    if sig.direction == "LONG" and sig.change24h <= -10:
        return "cokusste long yok"
    high24 = getattr(sig, "high24h", 0) or 0
    low24 = getattr(sig, "low24h", 0) or 0
    px = sig.price or 0
    if high24 > 0 and low24 > 0:
        rng = (high24 - low24) / low24
        if rng >= 0.25 and sig.symbol != "BTCUSDT":
            return "24s range pompa/dump"
        if sig.direction == "LONG" and (high24 - px) / high24 >= 0.12:
            return "24s tepeden dustu"
        if sig.direction == "SHORT" and (px - low24) / low24 >= 0.12:
            return "24s dipten zippladi"
    if sig.vol_ratio < 0.8:
        return "hacim zayif"
    if getattr(sig, "volume24h", 0) < 15_000_000:
        return "24s hacim dusuk"
    entry = ((sig.entry_low + sig.entry_high) / 2) or sig.price
    if entry and sig.sl and abs(entry - sig.sl) / entry < 0.003:
        return "sl cok dar"
    h4 = getattr(sig, "h4_trend", "YOK")
    if sig.direction == "SHORT" and h4 == "YUKARI":
        return "short 4H yukari"
    if sig.direction == "LONG" and h4 == "AŞAĞI":
        return "long 4H asagi"
    if sig.skip_reason:
        return sig.skip_reason
    return None


def scan_one(ticker: dict):
    symbol = ticker.get("symbol")
    df = get_candles(symbol)
    if df is None:
        return None
    sig = analyze(symbol, df, ticker)
    if not sig:
        return None
    df_1h = None
    df_4h = None
    if sig.score >= 5.0:
        df_1h = get_candles(symbol, granularity="1H", limit=80)
        df_4h = get_candles(symbol, granularity="4H", limit=80)
    return attach_plan(sig, df, df_1h, BTC_15, BTC_1H, df_4h)


def run() -> dict:
    global BTC_15, BTC_1H
    started = datetime.now(TR_TZ)
    BTC_15 = get_candles("BTCUSDT")
    BTC_1H = get_candles("BTCUSDT", granularity="1H", limit=80)
    tickers = get_tickers()
    print(f"{len(tickers)} parite taranacak (min hacim {config.MIN_USDT_VOLUME_24H:.0f})")

    signals = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(scan_one, t): t.get("symbol") for t in tickers}
        for fut in as_completed(futs):
            try:
                sig = fut.result()
            except Exception as exc:
                print("hata", futs[fut], exc)
                continue
            if sig:
                signals.append(sig)
            time.sleep(0.02)

    signals.sort(key=lambda s: s.score, reverse=True)
    state = load_state()
    entered = check_pending(state, tickers)
    if entered:
        print("simdi gir", " | ".join(entered))
    journal_notes = update_journal(state)
    if journal_notes:
        print("journal", " | ".join(journal_notes))
        send_telegram("<b>Journal</b>\n" + "\n".join(journal_notes))
    alerts = []
    for sig in signals:
        blocked = quality_gate(sig)
        if blocked:
            print("elendi", sig.symbol, sig.direction, sig.score, blocked)
            continue
        if len(alerts) >= getattr(config, "MAX_ALERTS_PER_RUN", 3):
            print("tur limiti", sig.symbol, sig.score)
            continue
        if not cooldown_ok(state, sig.symbol, sig.direction):
            print("cooldown", sig.symbol, sig.direction, sig.score)
            continue
        ok = send_telegram(format_alert(sig))
        if ok or not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
            mark_alert(state, sig)
            alerts.append(sig.to_dict())

    snapshot = {
        "updated_at": started.strftime("%Y-%m-%d %H:%M:%S TR"),
        "timeframe": config.TIMEFRAME,
        "scanned": len(tickers),
        "alert_score": config.ALERT_SCORE,
        "alerts_sent": len(alerts),
        "top": [s.to_dict() for s in signals[:40]],
    }
    save_json(config.LATEST_PATH, snapshot)
    save_json(config.STATE_PATH, state)
    print(f"Bitti. Sinyal {len(signals)}, Telegram {len(alerts)}")
    return snapshot


if __name__ == "__main__":
    run()

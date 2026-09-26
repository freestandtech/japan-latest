#!/usr/bin/env python3
"""EN -> JA translation via Sakana Fugu (OpenAI-compatible Chat Completions).

Reads the API key from SAKANA_API_KEY. Translations are cached in
translate_cache.json keyed by (register, source text), so unchanged strings are
never re-sent. The cache holds only demo copy (source + translation), no
credentials.

Usage as a library:
    from translate import Translator
    t = Translator()
    t.translate("Start sampling", register="consumer")
    t.translate_many(["...", "..."], register="b2b")

Usage from the shell:
    python translate.py --register b2b "Campaign performance overview"
"""
import argparse
import hashlib
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

BASE_URL = "https://api.sakana.ai/v1"
MODEL = "fugu"
TIMEOUT = 120
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translate_cache.json")

GLOSSARY = {
    "sampling": "サンプリング",
    "campaign": "キャンペーン",
    "conversion": "コンバージョン",
    "first-party data": "ファーストパーティデータ",
    "privacy notice (consent screens, notice headings, consent text)": "個人情報の取扱いについて",
    "privacy policy (only a link to the full policy document)": "プライバシーポリシー",
    "\"Nothing else.\" at the end of a what-we-collect list": "これ以外の情報はお預かりしません。",
}

# Japanese demo personas: always written this way (surname first).
PERSONA_NAMES = {
    "Mayumi Satō": "佐藤 真由美", "Mayumi S.": "佐藤 真由美", "Mayumi": "真由美",
    "Yuki T.": "田中 優希", "Yuki Tanaka": "田中 優希",
    "Kenta M.": "森 健太", "Kenta Mori": "森 健太",
    "Aoi N.": "中村 葵", "Haruto S.": "鈴木 陽翔", "Mei K.": "小林 芽衣",
    "Sakura S.": "佐藤 さくら", "Sakura Sato": "佐藤 さくら", "Sakura": "さくら",
    "Sota I.": "伊藤 颯太", "Rin F.": "藤田 凛", "Ren O.": "小川 蓮",
    "Hina W.": "渡辺 陽菜", "Rina O.": "岡田 莉奈",
    "Sakura Terrace": "サクラテラス", "Sakura Heights": "さくらハイツ",
}

# Reviewed fixes applied to the model output: (wrong, right) substring edits.
# Kept outside the prompt so fixing one string doesn't invalidate the cache.
POST_EDITS = [
    ("FreeStandアナリティクス", "FreeStand Analytics"),
    ("40 secondsで", "40秒で"),
    ("さくらには配信しません", "さくらさんには配信しません"),
    ("さくらはドライフード", "さくらさんはドライフード"),
    # purposes list: "Nothing else" means no other purpose, not no other data
    ("Nestléの広告。これ以外の情報はお預かりしません。", "Nestléの広告。これ以外の目的には使用しません。"),
    # profile tag has a fixed width; the full phrase gets truncated
    ("同意：個人情報の取扱いについて v1.0 · インドからのアクセスを含む", "同意：個人情報の取扱い v1.0 · インドアクセス含む"),
]

# Exact source strings with a fixed translation. Mostly sentence fragments the
# page glues around a variable ("You added " + brand + " as a friend."), which
# can't be translated in isolation. "" drops the fragment.
OVERRIDES = {
    "You added": "",
    "as a friend.": "を友だち追加しました。",
    "Earn": "獲得",
    "points": "ポイント",
}

# Fugu keeps English time units next to numbers ("2 days", "1–7 years");
# convert them in the Japanese output. Ages here are always children/pets → 歳.
N = r"(\d[\d.,]*(?:\s?[–-]\s?\d[\d.,]*)?)"
UNIT_FIXES = [
    (re.compile(r"(\d+) y (\d+) m(?![A-Za-z])"), r"\1歳\2か月"),
    (re.compile(r"(\d+):(\d+) min(?![A-Za-z])"), r"\1分\2秒"),
    (re.compile(r"(\d+)\s?\+\s?(?:years?|y)(?![A-Za-z])"), r"\1歳以上"),
    (re.compile(N + r"\s?(?:years?|y)(?![A-Za-z])"), r"\1歳"),
    (re.compile(N + r"\s?months?(?![A-Za-z])"), r"\1か月"),
    (re.compile(N + r"\s?weeks?(?![A-Za-z])"), r"\1週間"),
    (re.compile(N + r"\s?days?(?![A-Za-z])"), r"\1日"),
    (re.compile(N + r"\s?(?:hours?|hrs?)(?![A-Za-z])"), r"\1時間"),
    (re.compile(N + r"\s?(?:minutes?|mins?)(?![A-Za-z])"), r"\1分"),
    (re.compile(N + r"\s?seconds?(?![A-Za-z])"), r"\1秒"),
]

KEEP_ENGLISH = [
    "FreeStand", "WhatsApp", "LINE", "Nestlé", "LACTOGROW", "Pedigree",
    "Shinsu SP", "APPI", "RoPA", "OTP", "SKU", "QR",
]

COMMON_RULES = f"""You are a professional Japanese localizer. Translate the user's English text into natural Standard Japanese (標準語).

Rules:
- Output ONLY the Japanese translation. No quotes, notes, romaji, or explanations.
- Keep brand, product, store and company names in English exactly as written (e.g. {", ".join(KEEP_ENGLISH)}, and any other brand/product/store/courier name). Japanese place names and addresses are written in Japanese (e.g. Shibuya, Tokyo → 東京都渋谷区).
- Japanese persona names are written in kanji, surname first, exactly as listed: """ + "; ".join(f"{k} → {v}" for k, v in PERSONA_NAMES.items()) + """. Any other person's name stays in Latin letters.
- Dates use Japanese format (e.g. Sep 12, 2026 → 2026年9月12日; Sep 14 (Mon) → 9月14日（月）; 8 Jan, 2026 → 2026年1月8日).
- Do not translate code, variable names, URLs, email addresses, file paths, or numbers. Keep numbers, currency, %, and units exactly as written.
- Placeholders look like ⟦0⟧, ⟦1⟧ ... They stand for markup, line breaks or code. Keep every placeholder exactly once, unchanged, placing it where it belongs grammatically in the Japanese sentence.
- Use Japanese punctuation (、。) for Japanese sentences. Short UI labels (buttons, tabs, headings) stay short and get no trailing 。.
- Glossary (always use): """ + "; ".join(f"{k} → {v}" for k, v in GLOSSARY.items()) + "."

REGISTERS = {
    "b2b": COMMON_RULES + """
- Audience: Japanese FMCG brand managers and a media agency (B2B sales demo, analytics dashboard, pitch copy, case studies).
- Register: business polite です/ます. When FreeStand refers to itself, use humble 謙譲語 (e.g. いたします, ご提供します). Do not use overly formal 最敬語. No hype or exaggerated marketing language; keep it factual and concise.
- Dashboard labels and table headers: concise noun phrases, no です/ます.""",
    "consumer": COMMON_RULES + """
- Audience: Japanese consumers using a LINE mini app / sample request form / feedback survey.
- Register: friendly, simple, clear です/ます. Short sentences. Button labels are short (e.g. 送信する, 次へ).""",
}


class Translator:
    def __init__(self, cache_path=CACHE_PATH, workers=6):
        key = os.environ.get("SAKANA_API_KEY")
        if not key:
            raise SystemExit("SAKANA_API_KEY is not set")
        self.client = OpenAI(api_key=key, base_url=BASE_URL, timeout=TIMEOUT, max_retries=3)
        self.cache_path = cache_path
        self.workers = workers
        self.lock = threading.Lock()
        try:
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)
        except FileNotFoundError:
            self.cache = {}

    @staticmethod
    def key(text, register):
        # the prompt is part of the key, so changing the rules re-translates
        h = hashlib.sha256((REGISTERS[register] + "\x00" + text).encode("utf-8")).hexdigest()[:24]
        return register + ":" + h

    @staticmethod
    def postprocess(text, ja):
        # headings/labels: no trailing 。 unless the English is a full sentence
        if ja.endswith("。") and not re.search(r"[.!?][\"”’)]*\s*$", re.sub(r"⟦\d+⟧", "", text)):
            ja = ja[:-1]
        for pattern, repl in UNIT_FIXES:
            ja = pattern.sub(repl, ja)
        for wrong, right in POST_EDITS:
            ja = ja.replace(wrong, right)
        return ja

    def save(self):
        with self.lock:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.cache_path)

    def _call(self, text, register):
        resp = self.client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": REGISTERS[register]},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    def cached(self, text, register="b2b"):
        """Translation from overrides/cache only; None if it would need an API call."""
        if text in OVERRIDES:
            return OVERRIDES[text]
        if text in PERSONA_NAMES:
            return PERSONA_NAMES[text]
        hit = self.cache.get(self.key(text, register))
        return self.postprocess(text, hit["ja"]) if hit else None

    def translate(self, text, register="b2b"):
        if register not in REGISTERS:
            raise ValueError(f"unknown register {register!r}")
        if text in OVERRIDES:
            return OVERRIDES[text]
        if text in PERSONA_NAMES:
            return PERSONA_NAMES[text]
        k = self.key(text, register)
        hit = self.cache.get(k)
        if hit:
            return self.postprocess(text, hit["ja"])
        placeholders = re.findall(r"⟦\d+⟧", text)
        ja = None
        for attempt in range(3):
            ja = self._call(text, register)
            # a translation must keep every placeholder exactly once
            if sorted(re.findall(r"⟦\d+⟧", ja)) == sorted(placeholders) and ja:
                break
        else:
            raise RuntimeError(f"placeholder mismatch after retries: {text!r} -> {ja!r}")
        with self.lock:
            self.cache[k] = {"en": text, "ja": ja}
        return self.postprocess(text, ja)

    def translate_many(self, items, save_every=25):
        """items: list of (text, register). Returns list of translations (None on failure)."""
        out = [None] * len(items)
        done = 0

        def job(i):
            text, reg = items[i]
            try:
                out[i] = self.translate(text, reg)
            except Exception as e:  # keep going; report at the end
                print(f"  ! failed: {text[:60]!r}: {type(e).__name__}: {e}", file=sys.stderr)

        with ThreadPoolExecutor(self.workers) as ex:
            for _ in ex.map(job, range(len(items))):
                done += 1
                if done % save_every == 0:
                    self.save()
                    print(f"  {done}/{len(items)}", file=sys.stderr)
        self.save()
        return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--register", choices=REGISTERS, default="b2b")
    a = ap.parse_args()
    t = Translator()
    print(t.translate(a.text, a.register))
    t.save()

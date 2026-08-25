#!/usr/bin/env python3
"""
Отслеживание изменений на веб-странице с уведомлением в Telegram.

Настройки берутся из переменных окружения:
  TARGET_URL          - адрес отслеживаемой страницы (обязательно)
  TELEGRAM_BOT_TOKEN  - токен бота от @BotFather (обязательно)
  TELEGRAM_CHAT_ID    - id чата, куда слать уведомления (обязательно)
  MODE                - "text" (по умолчанию, только видимый текст)
                        или "html" (весь код страницы)
"""
import os
import sys
import difflib
import requests
from bs4 import BeautifulSoup

URL = os.environ.get("TARGET_URL", "").strip()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
MODE = os.environ.get("MODE", "text").strip().lower()
SNAPSHOT_FILE = "snapshot.txt"

# Теги, которые почти всегда содержат «шум» (реклама, скрипты, счётчики).
# Убираем их, чтобы не получать ложные срабатывания при каждой загрузке.
NOISE_TAGS = ["script", "style", "noscript", "template", "svg"]


def fetch_content(url):
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; change-monitor/1.0)"},
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    if MODE == "html":
        content = str(soup)
    else:
        content = soup.get_text(separator="\n")

    # Нормализуем: убираем пустые строки и лишние пробелы
    lines = [ln.strip() for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Нет токена или chat_id — уведомление не отправлено.")
        return
    if len(text) > 3900:  # лимит сообщения Telegram ~4096 символов
        text = text[:3900] + "\n…(обрезано)"
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        api,
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def main():
    if not URL:
        print("Не задан TARGET_URL.")
        sys.exit(1)

    try:
        new_content = fetch_content(URL)
    except Exception as e:
        # Не роняем весь запуск из-за временной ошибки сети
        print(f"Не удалось загрузить страницу: {e}")
        sys.exit(0)

    # Первый запуск — просто сохраняем снимок
    if not os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Первый запуск: снимок сохранён, сравнивать пока не с чем.")
        return

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        old_content = f.read()

    if new_content == old_content:
        print("Изменений нет.")
        return

    # Строим построчный diff
    diff = difflib.unified_diff(
        old_content.splitlines(), new_content.splitlines(), lineterm="", n=0
    )
    diff_lines = [d for d in diff if d and not d.startswith(("+++", "---", "@@"))]
    added = [d[1:].strip() for d in diff_lines if d.startswith("+") and d[1:].strip()]
    removed = [d[1:].strip() for d in diff_lines if d.startswith("-") and d[1:].strip()]

    parts = [f"🔔 Изменения на странице:\n{URL}"]
    if added:
        parts.append("➕ Появилось:\n" + "\n".join(added[:40]))
    if removed:
        parts.append("➖ Пропало:\n" + "\n".join(removed[:40]))
    message = "\n\n".join(parts)

    send_telegram(message)
    print("Изменение найдено, уведомление отправлено.")

    # Обновляем снимок
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


if __name__ == "__main__":
    main()

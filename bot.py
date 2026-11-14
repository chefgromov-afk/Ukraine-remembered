"""
Автоответчик на комментарии YouTube-канала «Забута Україна».

Раз в запуск:
  1. берёт свежие комментарии канала (YouTube Data API);
  2. пропускает те, где канал уже ответил, свои собственные и слишком старые;
  3. отправляет комментарий в Claude — тот решает: ответить / пропустить;
  4. публикует ответ от имени канала.

Секреты берутся из переменных окружения:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, ANTHROPIC_API_KEY
Необязательные:
  MAX_REPLIES (по умолчанию 15) — максимум ответов за один запуск
  MAX_AGE_HOURS (по умолчанию 48) — не отвечать на комментарии старше
  DRY_RUN=1 — ничего не публиковать, только показать, что бы ответил
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHANNEL_ID = "UCyXY4lu8PGR6a5u2pHMu3Og"  # Забута Україна
MODEL = "claude-haiku-5-5"
SIGNATURE = "Підписуйтеся — попереду ще багато забутого 🙏"

MAX_REPLIES = int(os.getenv("MAX_REPLIES", "15"))
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "48"))
DRY_RUN = os.getenv("DRY_RUN") == "1"

SYSTEM_PROMPT = f"""Ти — автор україномовного YouTube-каналу «Забута Україна» про побут, традиції та історію українського села.
Тобі дають коментар глядача і назву відео. Вирішуєш, чи відповідати, і пишеш відповідь.

ПРАВИЛА ВІДПОВІДІ:
- Тільки українською мовою, тепло й по-людськи, 1–2 КОРОТКІ речення.
- Схема: тепла реакція на конкретні слова глядача + одне просте питання до нього (про його родину, бабусю й дідуся, рідне село, спогади, страви, звичаї чи його думку).
- ЖОДНИХ фактів: не називай дат, цифр, указів, історичних тверджень — навіть якщо здається, що знаєш.
- Нічого не обіцяй від імені каналу (майбутні відео, теми тощо).
- Не додумуй за глядача: не пиши, де він ріс, що пережив чи відчуває, якщо він сам цього не сказав.
- Питання ніколи не має торкатися війни, політики чи сучасних подій.
- КОЖНА ВІДПОВІДЬ УНІКАЛЬНА: чергуй початки й питання, не повторюй фраз із уже написаних відповідей (їх дадуть нижче). Не починай щоразу з «Дякуємо».
- ТЕМА ВІЙНИ — ТАБУ: ніколи не згадуй війну, фронт, обстріли, окупацію, армію, сучасну політику.
- Наприкінці додай рядок: «{SIGNATURE}»
- Без образ. Без емодзі, крім 💙💛 чи 🙏 у доречних місцях.

КОЛИ ПРОПУСКАТИ (action = "skip"):
- коментар про війну, політику, владу, корупцію, сучасних політиків;
- натяки на Росію чи сучасні події, навіть якщо звучать побутово: «сусід», «сусіди», «вони», «рашка», «варвари», «орда», «ті що на сході», «зараз», «раби» тощо у розмові про народи чи долю країни;
- проросійський, грубий, образливий, з лайкою або зневагою до будь-якого народу;
- спам, реклама, посилання, незрозумілий набір символів;
- коментар, на який неможливо відповісти без вигадування фактів;
- сарказм або провокація.
У сумнівних випадках — пропускай.

Своє рішення повертай ЛИШЕ через інструмент decide.
"""


DECIDE_TOOL = {
    "name": "decide",
    "description": "Рішення щодо коментаря: відповісти чи пропустити.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["reply", "skip"]},
            "reason": {"type": "string", "description": "коротко чому"},
            "text": {"type": "string", "description": "текст відповіді або порожньо"},
        },
        "required": ["action", "reason", "text"],
    },
}


def youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def fetch_threads(yt, pages=2):
    """Свежие ветки комментариев по всему каналу (новые сверху)."""
    threads, token = [], None
    for _ in range(pages):
        resp = yt.commentThreads().list(
            part="snippet,replies",
            allThreadsRelatedToChannelId=CHANNEL_ID,
            order="time",
            maxResults=50,
            textFormat="plainText",
            pageToken=token,
        ).execute()
        threads.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return threads


def channel_already_replied(thread):
    for r in thread.get("replies", {}).get("comments", []):
        author = r["snippet"].get("authorChannelId", {}).get("value")
        if author == CHANNEL_ID:
            return True
    return False


def video_titles(yt, video_ids):
    titles = {}
    ids = list(video_ids)
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            titles[v["id"]] = v["snippet"]["title"]
    return titles


def ask_claude(client, comment, title, previous):
    prev = "\n".join(f"- {p}" for p in previous[-15:]) or "(ще немає)"
    content = (
        f"Відео: «{title}»\nКоментар глядача:\n{comment}\n\n"
        f"Вже написані відповіді (НЕ повторюй їхні початки й фрази):\n{prev}"
    )
    for _ in range(2):  # повтор, если Claude не вызвал инструмент
        msg = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            tools=[DECIDE_TOOL],
            tool_choice={"type": "tool", "name": "decide"},
            messages=[{"role": "user", "content": content}],
        )
        for b in msg.content:
            if b.type == "tool_use":
                return b.input
    raise ValueError("Claude не вернул решение")


def post_reply(yt, parent_id, text):
    yt.comments().insert(
        part="snippet",
        body={"snippet": {"parentId": parent_id, "textOriginal": text}},
    ).execute()


def main():
    yt = youtube_client()
    claude = anthropic.Anthropic()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    candidates, previous = [], []
    threads = fetch_threads(yt)
    # свежие ответы канала — чтобы новые не повторяли старые
    for t in threads:
        for r in t.get("replies", {}).get("comments", []):
            if r["snippet"].get("authorChannelId", {}).get("value") == CHANNEL_ID:
                previous.append(r["snippet"]["textDisplay"].replace(SIGNATURE, "").strip()[:200])
    previous = previous[:15][::-1]

    for t in threads:
        top = t["snippet"]["topLevelComment"]
        s = top["snippet"]
        author = s.get("authorChannelId", {}).get("value")
        published = datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00"))
        if author == CHANNEL_ID or published < cutoff or channel_already_replied(t):
            continue
        candidates.append((top["id"], s.get("videoId"), s["authorDisplayName"], s["textDisplay"]))

    if not candidates:
        print("Нових коментарів без відповіді немає.")
        return

    titles = video_titles(yt, {c[1] for c in candidates if c[1]})
    replied = 0
    for comment_id, video_id, author, text in reversed(candidates):  # от старых к новым
        if replied >= MAX_REPLIES:
            break
        try:
            decision = ask_claude(claude, text, titles.get(video_id, ""), previous)
        except Exception as e:
            print(f"[ERR] {author}: Claude — {e}")
            continue

        if decision.get("action") != "reply" or not decision.get("text"):
            print(f"[SKIP] {author}: {text[:80]!r} — {decision.get('reason')}")
            continue

        reply = decision["text"].strip()
        if SIGNATURE not in reply:
            reply = f"{reply}\n{SIGNATURE}"
        previous.append(reply.replace(SIGNATURE, "").strip())

        if DRY_RUN:
            print(f"[DRY] {author}: {text[:80]!r}\n      → {reply}")
        else:
            try:
                post_reply(yt, comment_id, reply)
                print(f"[OK] {author}: {text[:80]!r}\n     → {reply}")
            except Exception as e:
                print(f"[ERR] {author}: публикация — {e}")
                continue
        replied += 1

    print(f"Готово: ответов {replied}, кандидатов {len(candidates)}.")


if __name__ == "__main__":
    sys.exit(main())

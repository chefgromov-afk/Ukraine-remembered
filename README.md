# Бот-автоответчик «Забута Україна»

Раз в час бот сам отвечает на новые комментарии YouTube-канала.
Грубые, политические, военные и пророссийские комментарии пропускает.

## 1. Ключ Claude API
1. Зайдите на https://console.anthropic.com, пополните баланс (хватит $5).
2. API Keys → Create Key → скопируйте ключ.

## 2. Доступ к YouTube
1. https://console.cloud.google.com → создайте проект «zabuta-bot».
2. «APIs & Services» → «Library» → включите **YouTube Data API v3**.
3. «OAuth consent screen» → External, заполните название и почту.
   Затем нажмите **Publish app** (иначе токен перестанет работать через 7 дней).
4. «Credentials» → «Create credentials» → «OAuth client ID» → тип **Desktop app** → скачайте JSON, переименуйте в `client_secret.json`.
5. На компьютере:
   ```
   pip install google-auth-oauthlib
   python get_token.py client_secret.json
   ```
   В браузере выберите аккаунт **Забута Україна**. Google предупредит, что приложение не проверено, — нажмите «Дополнительно → Перейти». В консоли появятся три значения.

## 3. Запуск на GitHub (бесплатно)
1. Создайте **приватный** репозиторий на github.com и загрузите туда все файлы этой папки (включая `.github/workflows/bot.yml`). Файл `client_secret.json` НЕ загружайте.
2. Settings → Secrets and variables → Actions → New repository secret. Добавьте 4 секрета:
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
   - `ANTHROPIC_API_KEY`
3. Вкладка **Actions** → «Zabuta comment bot» → **Run workflow** (dry_run = 1). В логе будет видно, что бот ответил бы, — ничего не публикуется.
4. Если ответы нравятся — дальше бот сам запускается каждый час и публикует.

## Настройки
- Правила ответов — переменная `SYSTEM_PROMPT` в `bot.py`.
- `MAX_REPLIES` — ответов за запуск (по умолчанию 15).
- `MAX_AGE_HOURS` — не трогать комментарии старше (48 ч).
- Остановить бота: Actions → бот → «…» → Disable workflow.

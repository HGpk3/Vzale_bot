# VZALE Bot

## Настройка окружения
Создайте файл `.env` в каталоге `VZALE_BOT` (рядом с `app.py` и `bot_with_broadcast_poll.py`).
Пример содержимого:

```
BOT_TOKEN=your_bot_token_here
DB_PATH=./tournament.db
API_SECRET=some_random_string
```

> При необходимости добавьте сюда и другие переменные, описанные в `config.py`.

## Запуск
- Бот: `python VZALE_BOT/bot_with_broadcast_poll.py`
- HTTP API: `uvicorn VZALE_BOT.app:app --reload`

Обе части используют один и тот же SQLite-файл, путь к которому задаётся переменной `DB_PATH` в `.env`.

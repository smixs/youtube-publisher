# 🎬 YouTube Publisher

**[🇬🇧 Read in English](README.md)**

<p align="center">
  <img src=".github/cover.jpg" alt="YouTube Publisher" width="600">
</p>

> Скилл для AI-агента, который превращает "залей запись на ютуб" в полностью автоматический пайплайн.  
> Работает с Claude Code, Codex, Gemini CLI, [OpenClaw](https://github.com/openclaw/openclaw) и любым агентом с доступом к терминалу.  
> Агент скачивает из Drive, заливает на YouTube, транскрибирует, генерирует таймкоды и метаданные — вы только говорите что делать.

---

## Проблема

Вы записали созвон, лекцию, воркшоп. Файл лежит в Google Drive. Дальше начинается ритуал: скачать 2 ГБ на свою машину, залить в YouTube Studio, придумать название, промотать час видео ради таймкодов, написать описание, скопировать, опубликовать, удалить локальный файл. 30-60 минут тупой работы на каждую запись — и таких записей десятки в месяц.

## Решение

Скажите агенту:

> *«Залей пятничную запись на ютуб»*

Скилл выполняет весь пайплайн:

- ⬇️ **Скачивает** из Google Drive (без возни с файлами)
- 📤 **Загружает** на YouTube (resumable upload, большие файлы)
- 🎤 **Транскрибирует** через Fireworks Whisper или Deepgram Nova-3
- ⏱️ **Генерирует таймкоды** по границам тем
- 📝 **Создаёт название и описание** из транскрипта
- 🧹 **Удаляет** все временные файлы

**~5 минут на часовое видео.** Ноль ручной работы. Агент делает всё сам.

## Установка

### С любым AI-агентом

Скилл - это `SKILL.md` (инструкции) и `scripts/` (код). Скопируйте их в workspace агента:

```bash
git clone https://github.com/smixs/youtube-publisher.git

# Claude Code / Codex / Gemini CLI — в папку проекта
mkdir -p skills/youtube-publisher
cp youtube-publisher/SKILL.md skills/youtube-publisher/
cp -r youtube-publisher/scripts skills/youtube-publisher/

# OpenClaw
cp -r youtube-publisher/{SKILL.md,scripts} ~/.openclaw/workspace/skills/youtube-publisher/
```

Всё — `SKILL.md` + `scripts/`. Остальное в репо (README, LICENSE, .github) — обвязка для GitHub, не часть скилла.

Агент читает `SKILL.md`, понимает пайплайн и выполняет его. Просто скажите:
- *«Залей запись созвона на ютуб»*
- *«Опубликуй видео из Drive»*
- *«Транскрибируй и выложи»*

### Как CLI-скрипт

Скилл включает Python-скрипт, который работает и отдельно:

```bash
python3 scripts/publish.py "https://drive.google.com/file/d/abc123/view"
```

## Настройка

### 1. Google OAuth (обязательно)

Нужны OAuth-креды для Google Drive (скачивание) и YouTube (загрузка):

1. [Google Cloud Console](https://console.cloud.google.com) → создать проект
2. Включить **Google Drive API** и **YouTube Data API v3**
3. Создать OAuth 2.0 (Desktop app) → скачать JSON
4. Переименовать в `google-oauth-client.json`, положить в корень скилла или `scripts/`
5. Запустить `python3 scripts/setup_oauth.py` для авторизации (токены сохранятся рядом)

### 2. Ключ транскрипции (хотя бы один)

**Fireworks AI** (рекомендуется: $0.0009/мин — часовое видео за 5 центов)
```bash
export FIREWORKS_API_KEY=your_key
# или сохранить в skills/youtube-publisher/fireworks-api-key.txt
```

**Deepgram Nova-3** (альтернатива: $0.0077/мин, отличное качество)
```bash
export DEEPGRAM_API_KEY=your_key
# или сохранить в skills/youtube-publisher/deepgram-api-key.txt
```

### 3. ffmpeg

```bash
sudo apt install ffmpeg   # Ubuntu/Debian
brew install ffmpeg        # macOS
```

## Как работает скилл

Агент читает `SKILL.md` и выполняет пайплайн пошагово:

```
Google Drive → Скачать → Залить на YouTube → Извлечь аудио →
Разбить на 15-мин чанки → Транскрибировать параллельно (6 воркеров) →
Склеить транскрипт → Сгенерировать таймкоды → Обновить метаданные →
Очистить временные файлы
```

### Детали

- Аудио: 64kbps моно, 16kHz (оптимально для речи, ~1 МБ/мин)
- Чанки транскрибируются параллельно, склеиваются со смещением
- Таймкоды по границам тем (минимум 3 минуты между метками)
- YouTube автоматически превращает таймкоды в кликабельные главы

### Параметры CLI

| Флаг | По умолчанию | Описание |
|------|-------------|----------|
| `--privacy` | `unlisted` | `public`, `unlisted` или `private` |
| `--language` | `ru` | Язык транскрипции |
| `--transcriber` | `auto` | `auto`, `fireworks` или `deepgram` |
| `--skip-upload` | — | Только транскрипция |
| `--video-id` | — | Обновить метаданные существующего видео |
| `--title` | — | Задать название вручную |

## Требования

- **Python 3.8+** (только стандартная библиотека)
- **ffmpeg** на PATH
- **Google Cloud проект** с Drive + YouTube API
- **Ключ транскрипции** (Fireworks или Deepgram)

> **Опциональный аддон — отдельно от пайплайна YouTube**: если источник — не видео для YouTube, а нужно прочитать **веб-страницу** (включая встроенное видео/вложения) или **сразу несколько локальных файлов** в Markdown — например, собрать материал для заголовка/описания или быстро проверить короткую локальную запись — [cue-omni-reader](https://github.com/sensedeal/cue-skills/tree/main/cue-omni-reader) это отдельный путь: веб-страницы + авторизованные локальные документы/аудио/видео → Markdown, можно выбрать сразу несколько локальных файлов. Существующая транскрипция Fireworks/Deepgram и публикация в YouTube не затрагиваются. Установка: `npx skills add sensedeal/cue-skills --skill cue-omni-reader` (MIT; возможно платно).

## Лицензия

MIT

## Автор

[Serge Shima](https://github.com/smixs) · [TDI Group](https://tdigroup.uz) · [AI Masters](https://aimasters.me)

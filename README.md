# Antigravity IDE & 2.0 Chat Sync

[🇬🇧 English](#-english-documentation) | [🇷🇺 Русская версия](#-русская-версия)

---

## 🇬🇧 English Documentation

Export, import, and synchronize **Antigravity IDE** and **Antigravity 2.0** AI conversations across multiple machines (e.g., **iMac ↔ MacBook**) and across moved or renamed project directories.

> **Zero external dependencies:** The extension runs on VS Code's built-in Node.js runtime and standard **Python 3** (pre-installed on macOS/Linux). No API keys, cloud servers, or external Python/npm packages are required.

---

### 🎯 Why This Exists

By default, Antigravity IDE stores all project conversations locally in the user's home directory rather than inside the project folder:
- `~/.gemini/antigravity/conversations/<uuid>.db` — Full conversation trajectory, steps, messages, and tool calls (SQLite WAL).
- `~/.gemini/antigravity/brain/<uuid>/` — Artifacts, transcripts, scratchpads, and media files.
- `~/.gemini/antigravity/conversation_summaries.db` — Global conversation registry linked to encoded `workspace_uris`.
- `~/.gemini/antigravity/agyhub_summaries_proto.pb` — Binary protobuf cache used by the background `agy --hub` process.

When you switch between devices (via **iCloud Drive** or **Git**) or move/rename a project directory, your local `~/.gemini/antigravity` on the other machine doesn't have the chat history—or Antigravity flags the chat as belonging to the old directory path.

#### How Chat Sync Solves It
1. **Atomic SQLite Export:** Uses `sqlite3.backup()` to flush active WAL caches cleanly into `.antigravity_chats/` inside your project folder without risking database corruption.
2. **Portable Bundle:** Saves conversations, `brain` artifacts, search index chunks (`conversations_fts`), metadata (`metadata.json`), and human-readable Markdown transcripts (`readable_transcripts/*.md`).
3. **Full Protobuf Wire-Format Remapping:** Recursively parses and re-serializes `CascadeTrajectorySummary`, `TrajectoryMetadata`, and `agyhub_summaries_proto.pb` so moved, renamed, or cross-user paths bind seamlessly to the current folder.
4. **IDE State Binding:** Automatically sets `lastConversationId` in Antigravity IDE's workspace `state.vscdb` and restarts the project's background `agy --hub` process so restored chats appear immediately on reload.

---

### 📦 Prebuilt Releases & Updates

You can download ready-to-use builds directly from [GitHub Releases](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases):

| Version | Date | Highlights | Downloads |
| :--- | :--- | :--- | :--- |
| **[v1.1.0](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.1.0)** *(Latest)* | 2026-11-25 | English-primary documentation, MIT license packaging metadata, Unicode/untitled transcript resolution fix, smart `sync` reload check, safer hub restart matching, and `.vsix` + `.zip` builds. | [antigravity-chat-sync-1.1.0.vsix](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.1.0/antigravity-chat-sync-1.1.0.vsix) • [antigravity-chat-sync-v1.1.0.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.1.0/antigravity-chat-sync-v1.1.0.zip) |
| **[v1.0.1](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.0.1)** | 2026-11-24 | Full recursive protobuf wire-format decoder/encoder for workspace URIs, eliminated `"This conversation is in a different workspace"` banner, updated `agyhub_summaries_proto.pb`, and graceful `agy --hub` restart. | [antigravity-chat-sync-v1.0.1.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.0.1/antigravity-chat-sync-v1.0.1.zip) |
| **[v1.0.0](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.0.0)** | 2026-11-23 | Initial release: Python CLI (`list`, `export`, `import`, `sync`), VS Code extension with Activity Bar & Status Bar controls, offline Markdown transcripts, and GitHub update checker. | [antigravity-chat-sync-v1.0.0.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.0.0/antigravity-chat-sync-v1.0.0.zip) |

#### Updating the Extension
- **Inside Antigravity IDE:** Press `Cmd + Shift + P` (or `Ctrl + Shift + P`), run **`Antigravity: Check for Extension Updates`**, or click the download icon in the **Antigravity Chats** sidebar title bar. Automatic startup checks are enabled by default (`antigravity.chatSync.autoCheckUpdates`).
- **From a cloned repository:**
  ```bash
  git pull origin main
  ./install_extension.sh
  ```
  Then run **`Developer: Reload Window`** inside Antigravity IDE.

---

### 🚀 Installation

#### Option 1: Install from VSIX (Recommended)
1. Download `antigravity-chat-sync-1.1.0.vsix` from the [Latest Release](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/latest).
2. In Antigravity IDE, open the **Extensions** panel (`Cmd + Shift + X`), click the **`...`** menu in the top-right corner, and choose **Install from VSIX...**.
3. Select the downloaded `.vsix` file and reload the window.

#### Option 2: Install via Shell Script (from ZIP or Git Clone)
```bash
git clone https://github.com/byMaker-art/antigravity_extension_export_import_chats.git
cd antigravity_extension_export_import_chats
./install_extension.sh
```
This installs the extension into `~/.antigravity-ide/extensions/bymaker.antigravity-chat-sync-1.1.0/`.

#### Option 3: Standalone CLI Usage (No Extension Needed)
Copy `antigravity_chat_sync.py` into any project (or keep it globally) and run it with Python 3:
```bash
# List conversations linked to the current project
python3 antigravity_chat_sync.py list

# Export current project's conversations into ./.antigravity_chats/
python3 antigravity_chat_sync.py export

# Import conversations from ./.antigravity_chats/ on another Mac (remaps paths automatically)
python3 antigravity_chat_sync.py import

# Bidirectional smart sync (exports if local is newer, imports if bundle is newer)
python3 antigravity_chat_sync.py sync
```

---

### 🧩 IDE Features & Settings

Once installed, **Antigravity Chat Sync** provides:
- **Activity Bar View (`Antigravity Chats`):** Lists all conversations for the open workspace with step counts and timestamps.
  - Click a conversation to view its exported offline Markdown transcript.
  - Click the **▶ (`Set as Active Chat in Panel`)** inline button to bind that conversation to the main Antigravity chat panel.
- **Status Bar Controls:** Quick-access **`Export Chats`**, **`Import Chats`**, and **`Sync Chats`** buttons at the bottom-left of the IDE.
- **VS Code Tasks (`.vscode/tasks.json`):** Pre-configured tasks accessible via `Cmd + Shift + P` → `Tasks: Run Task`.
- **Extension Settings:**
  - `antigravity.chatSync.autoImportOnOpen` *(default: `false`)* — Auto-sync when opening a workspace containing `.antigravity_chats/`.
  - `antigravity.chatSync.showStatusBarButtons` *(default: `true`)* — Toggle bottom Status Bar buttons.
  - `antigravity.chatSync.pythonPath` *(default: `"python3"`)* — Path to Python 3 executable.
  - `antigravity.chatSync.githubRepo` *(default: `"byMaker-art/antigravity_extension_export_import_chats"`)* — Repository used for update checks.
  - `antigravity.chatSync.autoCheckUpdates` *(default: `true`)* — Check for new GitHub releases on startup.

---

### 🔒 Security, Privacy & License

- **Privacy by Default:** `.gitignore` strictly excludes `.antigravity_chats/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.jsonl`, `readable_transcripts/`, `.env*`, keys, tokens, and credentials so private conversations are never accidentally pushed to public repositories.
- **No Telemetry or External Services:** All conversation data stays strictly local between your machines (via iCloud Drive, local transfer, or private storage). Network requests only occur when checking for updates against GitHub's public API.
- **License:** Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

### ❓ FAQ

**Why shouldn't I just symlink `~/.gemini/antigravity` to iCloud Drive or Dropbox?**  
Antigravity's SQLite databases use **WAL (Write-Ahead Logging)** mode (`-wal` and `-shm` files) with OS file locks. Cloud sync clients synchronize asynchronously and cannot preserve atomic SQLite locks, frequently leading to `"database is locked"`, sync conflict duplicates, or database corruption (`database disk image is malformed`) if both Macs are online or mid-write. This tool uses `sqlite3.backup()` to snapshot clean, self-contained database files safely.

---
---

## 🇷🇺 Русская версия

Инструмент и расширение для **Antigravity IDE** и **Antigravity 2.0**, позволяющие экспортировать, импортировать и синхронизировать историю AI-диалогов между разными компьютерами (например, **iMac ↔ MacBook**), а также при переносе или переименовании папок проекта.

> **Без внешних зависимостей:** работает на встроенном Node.js среды IDE и стандартном **Python 3** (предустановлен в macOS/Linux). Никаких сторонних пакетов, API-ключей и облачных серверов не требуется.

---

### 🎯 Зачем это нужно?

По умолчанию Antigravity IDE хранит все диалоги не в папке проекта, а локально в домашней директории пользователя:
- `~/.gemini/antigravity/conversations/<uuid>.db` — полная история шагов, сообщений и вызовов инструментов (SQLite WAL).
- `~/.gemini/antigravity/brain/<uuid>/` — артефакты, транскрипты, черновики (`scratch`) и медиафайлы.
- `~/.gemini/antigravity/conversation_summaries.db` — единый реестр бесед с привязкой к URI проекта (`workspace_uris`).
- `~/.gemini/antigravity/agyhub_summaries_proto.pb` — бинарный protobuf-кэш фонового процесса `agy --hub`.

Когда вы открываете проект на втором Mac (через **iCloud Drive** или **Git**) или переименовываете папку проекта, на другом устройстве история чата пуста либо IDE считает чат привязанным к старому пути.

#### Как работает синхронизация
1. **Безопасный дамп SQLite:** использует встроенный `sqlite3.backup()` для атомарного сброса WAL-журнала в папку `.antigravity_chats/` внутри проекта без риска повреждения базы.
2. **Портативный пакет:** сохраняет базы диалогов, артефакты `brain`, поисковый индекс (`conversations_fts`), метаданные (`metadata.json`) и читаемые Markdown-транскрипты (`readable_transcripts/*.md`).
3. **Полноценный парсер Protobuf:** рекурсивно пересобирает структуры `CascadeTrajectorySummary`, `TrajectoryMetadata` и `agyhub_summaries_proto.pb`, автоматически перепривязывая пути к новой папке или другому имени пользователя на втором Mac.
4. **Мгновенная активация в окне IDE:** обновляет `lastConversationId` в `state.vscdb` текущей рабочей области и корректно перезапускает фоновый процесс `agy --hub`.

---

### 📦 Готовые сборки и обновления

Скачать готовые пакеты можно напрямую со страницы [GitHub Releases](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases):

| Версия | Дата | Описание изменений | Ссылки на сборки |
| :--- | :--- | :--- | :--- |
| **[v1.1.0](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.1.0)** *(Актуальная)* | 25.11.2026 | Английский раздел сделан основным в README + добавлена информация о релизах, добавлены метаданные MIT-лицензии в пакет расширения, исправлено открытие Unicode- и безымянных транскриптов в расширении, улучшена проверка перезапуска хаба и `sync`-уведомлений, собраны пакеты `.vsix` и `.zip`. | [antigravity-chat-sync-1.1.0.vsix](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.1.0/antigravity-chat-sync-1.1.0.vsix) • [antigravity-chat-sync-v1.1.0.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.1.0/antigravity-chat-sync-v1.1.0.zip) |
| **[v1.0.1](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.0.1)** | 24.11.2026 | Полный рекурсивный парсер/сериализатор Protobuf для обновления URI, устранено предупреждение о другом workspace, обновление кэша `agyhub_summaries_proto.pb` и автоматический перезапуск `agy --hub`. | [antigravity-chat-sync-v1.0.1.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.0.1/antigravity-chat-sync-v1.0.1.zip) |
| **[v1.0.0](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/tag/v1.0.0)** | 23.11.2026 | Первый релиз: Python CLI (`list`, `export`, `import`, `sync`), нативное расширение для VS Code / Antigravity IDE с боковой панелью и кнопками в статус-баре, экспорт в Markdown, проверка обновлений через GitHub. | [antigravity-chat-sync-v1.0.0.zip](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/download/v1.0.0/antigravity-chat-sync-v1.0.0.zip) |

#### Как обновить расширение
- **Внутри Antigravity IDE:** нажмите `Cmd + Shift + P` и выполните **`Antigravity: Check for Extension Updates`** (или нажмите иконку облака на панели **Antigravity Chats**). Фоновая проверка при запуске включена по умолчанию.
- **Через Git и установщик:**
  ```bash
  git pull origin main
  ./install_extension.sh
  ```
  Затем выполните **`Developer: Reload Window`** в Antigravity IDE.

---

### 🚀 Установка и использование

#### Способ 1: Установка через `.vsix` (Рекомендуемый)
1. Скачайте `antigravity-chat-sync-1.1.0.vsix` из [последнего релиза](https://github.com/byMaker-art/antigravity_extension_export_import_chats/releases/latest).
2. В Antigravity IDE откройте **Extensions** (`Cmd + Shift + X`) → меню **`...`** справа вверху → **Install from VSIX...**.
3. Выберите файл и перезагрузите окно IDE.

#### Способ 2: Установка скриптом из репозитория
```bash
git clone https://github.com/byMaker-art/antigravity_extension_export_import_chats.git
cd antigravity_extension_export_import_chats
./install_extension.sh
```

#### Способ 3: Использование из терминала (CLI)
```bash
# Список диалогов текущего проекта
python3 antigravity_chat_sync.py list

# Экспорт диалогов проекта в ./.antigravity_chats/
python3 antigravity_chat_sync.py export

# Импорт на втором Mac (с автоматической перепривязкой путей)
python3 antigravity_chat_sync.py import

# Умная двусторонняя синхронизация
python3 antigravity_chat_sync.py sync
```

---

### 🔒 Безопасность и лицензия

- **Защита личных данных:** в `.gitignore` добавлены `.antigravity_chats/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.jsonl`, `readable_transcripts/`, `.env*`, ключи и токены — приватные чаты не попадут в репозиторий при `git push`.
- **Лицензия:** проект распространяется свободно по лицензии **MIT** — см. файл [LICENSE](LICENSE).

---

### ❓ Частый вопрос: почему нельзя просто сделать симлинк `~/.gemini/antigravity` в iCloud?
Базы данных Antigravity работают в режиме **SQLite WAL**. Облачные диски (iCloud, Dropbox) синхронизируют файлы асинхронно и не поддерживают системные блокировки файлов (`flock`), что при одновременной работе или обрыве связи приводит к повреждению базы (`database disk image is malformed`). Скрипт использует `sqlite3.backup()` для безопасного создания чистых слепков.

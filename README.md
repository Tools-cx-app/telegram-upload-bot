# Telegram upload bot action

Reusable GitHub Action that sends CI or release information, optionally with
build artifacts, to Telegram.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `bot-token` | Yes | — | Telegram bot token, usually from `secrets` |
| `chat-id` | Yes | — | Telegram chat ID, usually from `secrets` |
| `is-release` | No | `false` | Send a release notification instead of a CI notification |
| `files` | No | `./output/*.zip` | File path or glob of files to upload |

## Setup

Create these repository secrets in **Settings → Secrets and variables →
Actions**:

- `TELEGRAM_BOT_TOKEN`: token from `@BotFather`
- `TELEGRAM_CHAT_ID`: target chat or channel ID

The bot must have permission to send messages to the target chat and upload
documents.

## CI notification with default files

This sends a CI notification and uploads every ZIP file under `output/`:

```yaml
name: Build and notify

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: |
          mkdir -p output
          zip -r output/my-app.zip src/

      - name: Send CI notification
        uses: Tools-cx-app/telegram-upload-bot@v1
        with:
          bot-token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          chat-id: ${{ secrets.TELEGRAM_CHAT_ID }}
```

The default value of `files` is:

```yaml
files: ./output/*.zip
```

## Upload a custom glob

Use `files` to upload files from another directory or several matching files:

```yaml
- name: Send build artifacts
  uses: Tools-cx-app/telegram-upload-bot@v1
  with:
    bot-token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    chat-id: ${{ secrets.TELEGRAM_CHAT_ID }}
    files: ./dist/*.tar.gz
```

Multiple patterns can be supplied as a shell-style brace glob when supported
by the runner:

```yaml
files: ./output/*.{zip,tar.gz}
```

To upload one specific file:

```yaml
files: ./release/my-app.zip
```

If no files match, the action still sends the Telegram message without an
attachment.

## Release notification

Set `is-release` to `true` for a release message. The action uses the GitHub
release tag from the workflow context:

```yaml
name: Release and notify

on:
  release:
    types: [published]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download release files
        run: |
          mkdir -p output
          # Replace this with the real release build/download command.
          cp path/to/my-app.zip output/my-app.zip

      - name: Send release notification
        uses: Tools-cx-app/telegram-upload-bot@v1
        with:
          bot-token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          chat-id: ${{ secrets.TELEGRAM_CHAT_ID }}
          is-release: "true"
          files: ./output/*.zip
```

## Notes

- The action reads the current workflow's GitHub event and commit metadata.
- One matching file is sent as a document with the message as its caption.
- Multiple matching files are sent as a Telegram media group.
- Empty or missing files are skipped.

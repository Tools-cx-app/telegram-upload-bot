# Telegram upload bot action

Reusable GitHub Action that sends CI or release information and GitHub Actions
artifact links to Telegram. It sends a text message without downloading artifacts
or uploading attachments to Telegram.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `bot-token` | Yes | — | Telegram bot token, usually from `secrets` |
| `chat-id` | Yes | — | Telegram chat ID, usually from `secrets` |
| `is-release` | No | `false` | Send a release notification instead of a CI notification |
| `artifact-names` | No | Empty | Artifact names or glob patterns from the current workflow run, separated by newlines or commas |
| `github-token` | No | `${{ github.token }}` | GitHub token with `actions: read` permission to look up artifacts |

The previous `files` input has been replaced by `artifact-names`. Pass the names
used in `actions/upload-artifact`, or patterns matching those names, rather than local file paths. Leave
`artifact-names` empty to send only commit or release information.

## Setup

Create these repository secrets in **Settings → Secrets and variables → Actions**:

- `TELEGRAM_BOT_TOKEN`: token from `@BotFather`.
- `TELEGRAM_CHAT_ID`: target chat or channel ID.

The bot must have permission to send messages to the target chat. Give the
workflow token `actions: read` permission when using `artifact-names`.

## CI notification with artifact links

Upload artifacts before running this action. The action finds their IDs in the
current workflow run and automatically builds their GitHub download page links.

```yaml
name: Build and notify

on:
  push:
    branches: [main]

permissions:
  contents: read
  actions: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: |
          mkdir -p output
          zip -r output/my-app.zip src/

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: my-app
          path: output/my-app.zip

      - name: Send CI notification
        uses: Tools-cx-app/telegram-upload-bot@master
        with:
          bot-token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          chat-id: ${{ secrets.TELEGRAM_CHAT_ID }}
          artifact-names: my-app
```

The Telegram message places `artifacts` and the clickable artifact names above
the commit history:

```text
New push to Github
artifacts:
my-app                 ← clickable GitHub artifact link
abc1234 Fix build
See commit detail here
#ci_42
```

For several artifacts, use one name per line:

```yaml
artifact-names: |
  my-app-linux
  my-app-windows
```

Comma-separated names are also supported:

```yaml
artifact-names: my-app-linux, my-app-windows
```

Use wildcards to match several artifact names:

```yaml
artifact-names: "my-app-*"
```

Patterns support `*` (any sequence), `?` (one character), and `[abc]` or `[a-z]`
(a character set or range). Matching is case-sensitive. Quote patterns in YAML,
especially when they start with `*`. Names and patterns can be mixed:

```yaml
artifact-names: |
  my-app-*
  build-report
```

If artifacts are uploaded by other jobs, make the notification job depend on
those jobs using `needs`. The artifacts must belong to the same workflow run.

## Release notification

Set `is-release` to `true` for a release message. The action uses the release tag
from the workflow context. Artifact names still refer to GitHub Actions artifacts,
including in release mode; they do not refer to release assets.

```yaml
- name: Upload artifact
  uses: actions/upload-artifact@v4
  with:
    name: my-app-release
    path: output/my-app.zip

- name: Send release notification
  uses: Tools-cx-app/telegram-upload-bot@master
  with:
    bot-token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    chat-id: ${{ secrets.TELEGRAM_CHAT_ID }}
    is-release: "true"
    artifact-names: my-app-release
```

Release messages include the artifact links above the release detail link.

## Notes

- Links follow the supplied name/pattern order. Matches within each pattern follow
  GitHub API order; overlapping patterns display each artifact only once.
- Each name or pattern must match at least one artifact that has not expired;
  otherwise the action fails before sending the notification.
- API failures, including insufficient token permissions, also fail the action.
- Downloading artifacts requires GitHub sign-in and access to the repository.
- Links stop working when the artifacts expire or are deleted.
- Commit metadata comes from the current workflow's event payload or local Git
  history.

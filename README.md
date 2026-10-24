# ⚡ FAST LIKE — Telegram Bot

A clean, dark-brand-friendly Telegram bot with a standard reply keyboard (not inline buttons), points, daily bonus, redeem codes, profile, leaderboard, statistics, and admin controls.

## 1. Deploy the Like API first
You currently have only the API ZIP. The bot needs the API to be deployed separately. Follow the original API project's instructions, then test:
`https://YOUR-API-DOMAIN/like?uid=PLAYER_UID&server_name=BD`

The URL above is a placeholder, not a live API.

## 2. Create the Telegram bot
Open `@BotFather`, run `/newbot`, and save the token privately.

## 3. Configure hosting environment variables
- `BOT_TOKEN`: Telegram BotFather token
- `LIKE_API_URL`: deployed API base URL, without `/like`
- `ADMIN_IDS`: your numeric Telegram user ID
- `DAILY_BONUS`: default 5
- `LIKE_COST`: default 1

Do not paste secrets into source code or public GitHub. The supplied guest JSON contains login credentials; do not upload it to a public repository. This bot does not need the guest JSON itself—the API server's credential handling is separate.

## 4. Run
`pip install -r requirements.txt`
`python bot.py`

Deploy it as a persistent Python worker. GitHub stores source but does not run a bot continuously by itself. Check current hosting plans before selecting a free worker; free plans can change.

## 5. Important
The bot expects JSON from `/like` with `status: 1` for confirmed success. Actual like delivery depends on the API, upstream account/token validity, and game service. Test only with accounts you own or are authorized to use.


## Premium message design
The bot includes branded welcome, help-center, UID-entry, request-processing, success, and failure messages using Telegram HTML formatting and a standard reply keyboard. Admin actions are available through `/admin`.

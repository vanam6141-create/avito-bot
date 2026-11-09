# Avito Sniper AI — Telegram Mini App

Static frontend. No paid APIs or subscriptions are used by this interface.

## Publish with GitHub Pages
1. In the repository, open **Settings → Pages**.
2. Under **Build and deployment**, select **Deploy from a branch**.
3. Select branch `main` (or the repository's default branch) and folder `/ (root)`.
4. Save and wait for GitHub Pages to publish.

Because the app is in `miniapp/`, either set Pages source to `/docs` after moving files, or copy `miniapp/index.html` to repository root as `index.html`. For simplest publishing, this repository should serve the root `index.html`.

The app is a frontend shell. Real Avito listing search, persistent cross-device settings, and scheduled notifications are not implemented. Do not enter bot tokens or secrets in this folder.

Telegram requires an HTTPS URL. After Pages is live, set the bot's menu button URL in @BotFather with `/setmenubutton`.

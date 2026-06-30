# Security Notes

This is a public portfolio repository.

Do not commit:

- `.env` files or production configuration.
- API tokens, Telegram credentials, cookies, sessions, or private keys.
- User data, customer data, private datasets, trained models, logs, or local databases.
- Generated binaries, installers, or local dependency folders.

Use `.env.example` files for public configuration examples.

If a secret is ever committed, rotate the secret immediately and remove it from Git history before continuing to use the repository publicly.


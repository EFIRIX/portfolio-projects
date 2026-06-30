# EFIRIX Portfolio Projects

This repository is a sanitized portfolio collection of selected projects.

Important: public GitHub repositories can always be cloned or downloaded. For that reason this repo contains portfolio-safe snapshots only: source code, documentation, configuration examples, and workflow files. Secrets, local `.env` files, generated binaries, trained models, logs, private data, dependency folders, and heavy artifacts were removed before publishing.

## Featured Projects

| Project | Stack | Notes |
|---|---|---|
| Online School Intella | Next.js, TypeScript, Python, Docker | Educational platform for history exam preparation |
| AERIX Education Avatar | TypeScript, Vite, Node.js | Real-time AI avatar education MVP |
| AERIX Energy Pilot | Python, ML, frontend JS | Energy forecasting and optimization prototype |
| LifeOS | Swift | Personal operating system / iOS-style project |
| Telegram Automation Bot | Python, Telethon, FastAPI | Automation bot with packaging and tests |
| Media Converter | Python | Desktop media conversion utility |
| Marketplace Recruiter AI Copilot | n8n workflow | Automation case for recruiting operations |
| Dating Photo Analyzer | React/Vite | Small browser-based AI-style analyzer UI |
| EGE Materials Generator | Python | Educational PDF/card generation scripts |

## Live Portfolio Page

After GitHub Pages is enabled, open:

`https://efirix.github.io/portfolio-projects/`

Some static demos are directly viewable from the page. Backend, ML, mobile, and automation projects are shown as case studies/source snapshots because they require runtime services or private data.

## Repository Layout

- `index.html` - public portfolio landing page.
- `projects/` - sanitized project snapshots.
- `PROJECTS.md` - full project inventory and publication notes.
- `SECURITY.md` - publication safety notes.

## Publication Safety

Before this repo was pushed, the collection was filtered for:

- `.env` and `.env.*`
- private keys and credential filenames
- dependency folders
- generated binaries and app bundles
- model files and logs
- large generated PDFs/DOCX artifacts
- local Git histories from copied projects

This repository is for portfolio review, not for storing production secrets or private datasets.


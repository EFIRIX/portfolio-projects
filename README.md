# EFIRIX Portfolio Projects

This repository is a sanitized portfolio collection of selected projects.

Important: public GitHub repositories can always be cloned or downloaded. For that reason this repo contains portfolio-safe snapshots only: source code, documentation, configuration examples, and workflow files. Secrets, local `.env` files, generated binaries, trained models, logs, private data, dependency folders, and heavy artifacts were removed before publishing.

## Projects

| Project | Stack | Portfolio Description |
|---|---|---|
| [Online School Intella](projects/online-school-intella/PORTFOLIO_DESCRIPTION.md) | Next.js, TypeScript, Python, Docker | Full-stack educational platform for history exam preparation with auth, roles, uploads, migrations, CI, and deployment documentation. |
| [AERIX Education Avatar](projects/aerix-education-avatar/PORTFOLIO_DESCRIPTION.md) | TypeScript, Vite, Node.js | Real-time AI education MVP focused on streaming, avatar animation, audio, latency budgets, and learning-assistant architecture. |
| [AERIX Energy Pilot](projects/aerix-energy-pilot/PORTFOLIO_DESCRIPTION.md) | Python, ML, frontend JS | Energy intelligence prototype for forecasting, anomaly detection, optimization, AutoML, explainability, and monitoring. |
| [LifeOS](projects/lifeos/PORTFOLIO_DESCRIPTION.md) | Swift | Native-style personal operating system concept with dashboards, reports, strategy views, statistics, and local persistence. |
| [Telegram Automation Bot](projects/telegram-automation-bot/PORTFOLIO_DESCRIPTION.md) | Python, Telethon, FastAPI, pytest | Automation bot with secure setup, storage, GUI flow, web module, packaging templates, and tests. |
| [Media Converter](projects/media-converter/PORTFOLIO_DESCRIPTION.md) | Python | Desktop utility for media conversion with GUI entry points, install script, packaging metadata, and dependency definitions. |
| [Marketplace Recruiter AI Copilot](projects/marketplace-recruiter-ai-copilot/PORTFOLIO_DESCRIPTION.md) | n8n workflow | Recruiting automation workflow that structures candidate/job data, estimates AI cost, and prepares recruiter-facing outputs. |
| [n8n AI Automation Factory](projects/n8n-ai-automation-factory/PORTFOLIO_DESCRIPTION.md) | n8n, Telegram, AI workflows | Collection of sanitized n8n workflows: a 133-node Telegram AI content factory, auto-debug loop, HTTP prototype, and recruiter automation. |
| [Dating Photo Analyzer](projects/dating-photo-analyzer/PORTFOLIO_DESCRIPTION.md) | React, Vite | Lightweight browser UI demo for analyzing dating profile photos. |
| [EGE Materials Generator](projects/ege-materials-generator/PORTFOLIO_DESCRIPTION.md) | Python | Educational tooling for generating exam-preparation materials from source content. |
| [Static Site 4](projects/static-site-4/PORTFOLIO_DESCRIPTION.md) | HTML, CSS, JavaScript | Small static web archive demo. |
| [Static Site 9](projects/static-site-9/PORTFOLIO_DESCRIPTION.md) | HTML, CSS, JavaScript | Compact static web archive demo. |
| [Static Site Pre:pri](projects/static-site-prepri/PORTFOLIO_DESCRIPTION.md) | HTML, CSS, JavaScript | Small static landing/static-page project. |
| [Informatics Static Site](projects/informatics-static-site/PORTFOLIO_DESCRIPTION.md) | HTML | Lightweight educational static site snapshot. |
| [Video Editing Course Site](projects/video-editing-course-site/PORTFOLIO_DESCRIPTION.md) | HTML, CSS, JavaScript | Older static educational/course website about video editing. |
| [iOS Project 123](projects/ios-project-123/PORTFOLIO_DESCRIPTION.md) | Swift, Xcode | Small Swift/Xcode archive project with app, watch app, unit test, and UI test targets. |
| [iOS Project 1234](projects/ios-project-1234/PORTFOLIO_DESCRIPTION.md) | Swift, Xcode | Small Swift/Xcode archive project with app, unit test, and UI test targets. |

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

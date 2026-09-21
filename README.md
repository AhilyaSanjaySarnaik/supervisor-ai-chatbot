
---

## ⚠️ Known limitations

Stated plainly, because knowing the gap is part of the engineering:

- **Sanitizer is regex-based**, not a trained classifier — it catches common injection phrasing but will miss heavily-reworded or Unicode-obfuscated attempts. A production version would add an LLM-based classifier as a second layer.
- **Auth is static API keys**, not a real identity provider — appropriate for a self-contained demo, not for multiple real users. A production version would verify tokens from an actual SSO/OAuth provider instead of a fixed key-to-role map in `.env`.
- **No persistent storage** — the HITL queue and security log are in-memory and reset on restart. A production version would back both with Redis/Postgres.
- **CORS is wide open** to support the dashboard being opened as a local file — restrict this before deploying beyond localhost.

---

## 📊 Live repo activity

<div align="center">

[![GitHub repo size](https://img.shields.io/github/repo-size/AhilyaSanjaySarnaik/supervisor-ai-chatbot?style=flat&color=3fb950)](https://github.com/AhilyaSanjaySarnaik/supervisor-ai-chatbot)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/AhilyaSanjaySarnaik/supervisor-ai-chatbot?style=flat&color=58a6ff)](https://github.com/AhilyaSanjaySarnaik/supervisor-ai-chatbot/commits/main)
[![GitHub contributors](https://img.shields.io/github/contributors/AhilyaSanjaySarnaik/supervisor-ai-chatbot?style=flat&color=d29922)](https://github.com/AhilyaSanjaySarnaik/supervisor-ai-chatbot/graphs/contributors)
[![GitHub top language](https://img.shields.io/github/languages/top/AhilyaSanjaySarnaik/supervisor-ai-chatbot?style=flat&color=f85149)](https://github.com/AhilyaSanjaySarnaik/supervisor-ai-chatbot)

</div>

*All badges above are shields.io-backed and pulled live from GitHub's API on every page load — repo size, monthly commit activity, contributor count, and primary language all reflect the current real state of the repo.*

## License

MIT

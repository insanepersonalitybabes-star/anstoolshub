# ANS Tools

A free online multi-tool website (anstools.xyz) offering 25+ browser-based utilities including image tools, PDF tools, text utilities, calculators, converters, and downloaders.

## Run & Operate

- Flask app auto-starts via the "ANS Tools" workflow
- `python3 artifacts/ans-tools/app.py` — run manually (reads `PORT` env var, defaults to 5000)
- `pnpm --filter @workspace/api-server run dev` — run the Node.js API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- **Frontend/Backend**: Python 3.11, Flask 3.0, Jinja2 templates
- **Image processing**: Pillow 10.2
- **PDF**: fpdf2 2.7.6, PyPDF2 3.0.1
- **QR codes**: qrcode 7.4.2
- **Node.js API**: Express 5, Drizzle ORM, PostgreSQL

## Where things live

- `artifacts/ans-tools/app.py` — Flask app with all 25+ tool routes
- `artifacts/ans-tools/templates/` — Jinja2 HTML templates
  - `base.html` — layout with nav, footer, AdSense placeholders, Google Analytics placeholder
  - `index.html` — homepage with search, category pills, tool grid
  - `tools/` — individual tool templates (25 tools)
- `artifacts/ans-tools/static/css/style.css` — full design system (Coolvetica, DM Sans, Space Grotesk, JetBrains Mono)
- `artifacts/ans-tools/static/js/main.js` — search, filter, TTS, copy, unit converter JS
- `artifacts/ans-tools/requirements.txt` — Python dependencies

## Architecture decisions

- Pure server-side rendering with Flask + Jinja2 — no build step needed, instant startup
- All tool logic lives in `app.py` — easy to add/modify tools without touching frontend
- RapidAPI key read from `RAPIDAPI_KEY` env var (for TikTok/Instagram downloaders)
- AdSense placeholder uses `ca-pub-XXXXXXXXXXXXXXXX` — replace with real publisher ID
- Google Analytics placeholder `G-XXXXXXXXXX` in base.html — replace with real ID

## Product

25+ free online tools organized into categories:
- **Image Tools**: Compress, resize, convert (JPG↔PNG), image to PDF
- **PDF Tools**: Merge PDFs, image to PDF
- **Text Tools**: Word counter, case converter, base64 encode/decode, URL encode/decode
- **Calculators**: Age, BMI, percentage, EMI loan, tip calculator
- **Converters**: Unit converter, random number generator
- **Generators**: QR code, password, invoice, meta tag generator
- **Other**: Color picker, text to speech, TikTok downloader, Instagram downloader

## User preferences

- Clean white/minimal design using Coolvetica (headings), DM Sans (body), Space Grotesk (labels), JetBrains Mono (code)
- AdSense and Google Analytics ready with placeholder IDs
- Full SEO: meta tags, Open Graph, JSON-LD structured data, sitemap.xml, robots.txt
- Mobile responsive

## Gotchas

- Run `python3 -m pip install -r artifacts/ans-tools/requirements.txt` if Python packages are missing
- TikTok/Instagram downloaders require `RAPIDAPI_KEY` env var to function
- Replace `ca-pub-XXXXXXXXXXXXXXXX` in base.html with real AdSense publisher ID before going live
- Replace `G-XXXXXXXXXX` in base.html with real Google Analytics measurement ID

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details

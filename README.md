<p align="center"><a href="https://sourcethemes.com/academic/" target="_blank" rel="noopener"><img src="https://sourcethemes.com/academic/img/logo_200px.png" alt="Academic logo"></a></p>

# Academic Kickstart: The Template for [Academic Website Builder](https://sourcethemes.com/academic/)

[**Academic**](https://github.com/gcushen/hugo-academic) makes it easy to create a beautiful website for free using Markdown, Jupyter, or RStudio. Customize anything on your site with widgets, themes, and language packs. [Check out the latest demo](https://academic-demo.netlify.app/) of what you'll get in less than 10 minutes, or [view the showcase](https://sourcethemes.com/academic/#expo).

**Academic Kickstart** provides a minimal template to kickstart your new website.

- 👉 [**Get Started**](#install)
- 📚 [View the **documentation**](https://sourcethemes.com/academic/docs/)
- 💬 [Chat with the **Academic community**](https://spectrum.chat/academic) or [**Hugo community**](https://discourse.gohugo.io)
- 🐦 Twitter: [@source_themes](https://twitter.com/source_themes) [@GeorgeCushen](https://twitter.com/GeorgeCushen) [#MadeWithAcademic](https://twitter.com/search?q=%23MadeWithAcademic&src=typd)
- 💡 [Request a **feature** or report a **bug**](https://github.com/gcushen/hugo-academic/issues)
- ⬆️ **Updating?** View the [Update Guide](https://sourcethemes.com/academic/docs/update/) and [Release Notes](https://sourcethemes.com/academic/updates/)
- :heart: **Support development** of Academic:
  - ☕️ [**Donate a coffee**](https://paypal.me/cushen)
  - 💵 [Become a backer on **Patreon** and **unlock rewards**](https://www.patreon.com/cushen)
  - 🖼️ [Decorate your laptop or journal with an Academic **sticker**](https://www.redbubble.com/people/neutreno/works/34387919-academic)
  - 👕 [Wear the **T-shirt**](https://academic.threadless.com/)
  - :woman_technologist: [**Contribute**](https://sourcethemes.com/academic/docs/contribute/)

[![Screenshot](https://raw.githubusercontent.com/gcushen/hugo-academic/master/academic.png)](https://github.com/gcushen/hugo-academic/)

## Install

You can choose from one of the following four methods to install:

* [**one-click install using your web browser (recommended)**](https://sourcethemes.com/academic/docs/install/#install-with-web-browser)
* [install on your computer using **Git** with the Command Prompt/Terminal app](https://sourcethemes.com/academic/docs/install/#install-with-git)
* [install on your computer by downloading the **ZIP files**](https://sourcethemes.com/academic/docs/install/#install-with-zip)
* [install on your computer with **RStudio**](https://sourcethemes.com/academic/docs/install/#install-with-rstudio)

Then [personalize your new site](https://sourcethemes.com/academic/docs/get-started/).

## Ecosystem

* **[Academic Admin](https://github.com/sourcethemes/academic-admin):** An admin tool to import publications from BibTeX or import assets for an offline site
* **[Academic Scripts](https://github.com/sourcethemes/academic-scripts):** Scripts to help migrate content to new versions of Academic

## Deployment (123-reg / cPanel hosting)

This site used to deploy via Netlify. It now builds and deploys with
GitHub Actions (`.github/workflows/deploy.yml`), which builds the Hugo
site and uploads `public/` over plain FTP to your hosting account. This
works regardless of whether your cPanel plan supports Git deploys - it
only needs FTP, which virtually every shared hosting package (including
123-reg) provides.

**One-time setup:**

1. In cPanel, find your FTP account details (Files -> FTP Accounts), or use
   your main hosting account login. Note the host, username and password.
2. In the GitHub repo, go to Settings -> Secrets and variables -> Actions
   and add:
   - `FTP_SERVER` - the hosting provider's own FTP hostname (check your
     123-reg hosting control panel's FTP Accounts/Details page - this is
     often a provider hostname, not `ftp.yourdomain`)
   - `FTP_USERNAME`
   - `FTP_PASSWORD`
   - `FTP_SERVER_DIR` (optional) - the remote folder to publish into, e.g.
     `/public_html/`. If your FTP account already lands in the right
     folder, leave this unset.
3. Push to `master` (or run the workflow manually from the Actions tab) to
   trigger a deploy.
4. Verify the new hosting serves the site correctly (e.g. via the
   hosting's temporary/IP-based URL or a test subdomain) **before**
   pointing your domain's DNS at it, so you don't get downtime if
   something's misconfigured.
5. Once verified, update your domain's DNS (A/CNAME records, or
   nameservers if 123-reg also manages the domain) to point at the new
   hosting, and delete/pause the old site on Netlify.

If your hosting package does support FTPS, you can switch `protocol: ftp`
to `protocol: ftps` in the workflow for an encrypted connection.

## Google Scholar publication sync

`.github/workflows/scholar-sync.yml` runs weekly (and can be triggered
manually from the Actions tab) and checks the configured Google Scholar
profile for papers that aren't yet in `content/publication/`. Any new
paper is added as a draft (`draft: true`, tagged `Needs review`) and
opened as a pull request - nothing is published automatically.

To use it: review the PR, fill in/check the DOI, authors, venue, tags and
`projects` (e.g. `projects: [markerless]`), then set `draft: false` and
merge.

The scraper (`scholarly`) has no official Google API behind it, and Google
routinely CAPTCHA-blocks requests coming from datacenter/CI IPs - including
GitHub-hosted runners - which makes an unconfigured scheduled run fairly
likely to fail. To make it reliable:

- Sign up for a free [ScraperAPI](https://www.scraperapi.com/) account
  (free tier is enough for a weekly check) and add its API key as a
  repository secret named `SCRAPERAPI_KEY`. The workflow will then route
  requests through it automatically.
- Without that secret, the script falls back to `scholarly`'s free public
  proxy pool, which is best-effort and can still get blocked.

If a run still fails, re-run it later or trigger it manually via
`workflow_dispatch`. See `scripts/scholar_sync.py` for details, including
how to point it at a different `--scholar-id`.

## License

Copyright 2017-present [George Cushen](https://georgecushen.com).

Released under the [MIT](https://github.com/sourcethemes/academic-kickstart/blob/master/LICENSE.md) license.

[![Analytics](https://ga-beacon.appspot.com/UA-78646709-2/academic-kickstart/readme?pixel)](https://github.com/igrigorik/ga-beacon)

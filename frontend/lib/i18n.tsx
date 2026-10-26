"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type Locale = "en" | "fa";

type Entry = { en: string; fa: string };

export const dict = {
  "nav.features": { en: "Features", fa: "ویژگی‌ها" },
  "nav.output": { en: "Output", fa: "خروجی‌ها" },
  "nav.how": { en: "How it works", fa: "چطور کار می‌کند" },
  "nav.studio": { en: "Open Studio", fa: "ورود به استودیو" },
  "nav.signIn": { en: "Sign in", fa: "ورود" },
  "nav.signOut": { en: "Log out", fa: "خروج" },
  "nav.settings": { en: "Settings", fa: "تنظیمات" },
  "nav.projects": { en: "Projects", fa: "پروژه‌ها" },
  "nav.back": { en: "Back", fa: "بازگشت" },

  /* ── Landing: hero ─────────────────────────────────────────────────── */
  "landing.heroTitle1": {
    en: "Translate manga into Persian.",
    fa: "مانگا را به فارسی ترجمه کنید.",
  },
  "landing.heroAccent": { en: "Publish-ready", fa: "آماده انتشار" },
  "landing.heroTitle3": { en: "in minutes.", fa: "در چند دقیقه." },
  "landing.heroSub": {
    en: "Upload a manga chapter and automate detection, translation, cleanup, and typesetting — all in one studio.",
    fa: "چپتر مانگا را آپلود کنید و تشخیص، ترجمه، پاکسازی و حروف‌چینی را خودکار انجام دهید — همه در یک استودیو.",
  },
  "landing.cta.free": {
    en: "Try Studio — Free",
    fa: "استودیو را رایگان امتحان کنید",
  },
  "landing.openStudio": { en: "Open Studio", fa: "ورود به استودیو" },
  "landing.chip.persian": { en: "Persian-first", fa: "فارسی‌محور" },
  "landing.chip.ai": { en: "AI-assisted", fa: "با کمک هوش مصنوعی" },
  "landing.chip.scanlation": { en: "Scanlation-ready", fa: "آماده‌ی اسکنلیشن" },
  "landing.labelOriginal": { en: "Original", fa: "اصلی" },
  "landing.labelPersian": { en: "Persian output", fa: "خروجی فارسی" },
  "landing.dragCompare": { en: "Drag to compare", fa: "برای مقایسه بکشید" },

  /* ── Landing: workflow strip ───────────────────────────────────────── */
  "landing.wfTitle": {
    en: "From raw pages to finished chapters.",
    fa: "از صفحات خام تا چپترهای آماده.",
  },
  "landing.wfSub": {
    en: "One workflow for the repetitive parts of manga translation.",
    fa: "یک گردش کار برای کارهای تکراری ترجمه مانگا.",
  },
  "landing.wf.detect": { en: "Detect", fa: "تشخیص" },
  "landing.wf.translate": { en: "Translate", fa: "ترجمه" },
  "landing.wf.clean": { en: "Clean", fa: "پاکسازی" },
  "landing.wf.typeset": { en: "Typeset", fa: "حروف‌چینی" },
  "landing.wf.export": { en: "Export", fa: "خروجی" },

  /* ── Landing: features (CH. 01) ────────────────────────────────────── */
  "landing.featuresTitle": {
    en: "Everything you need to translate a chapter.",
    fa: "هرچه برای ترجمه یک چپتر لازم دارید.",
  },
  "landing.featuresSub": {
    en: "Detection, translation, cleanup and Persian typesetting in one workflow.",
    fa: "تشخیص، ترجمه، پاکسازی و حروف‌چینی فارسی در یک گردش کار.",
  },
  "landing.f1.t": { en: "Smart text detection", fa: "تشخیص هوشمند متن" },
  "landing.f1.d": {
    en: "Detect dialogue and text automatically, even across busy manga pages.",
    fa: "دیالوگ و متن به‌صورت خودکار شناسایی می‌شود، حتی در صفحات شلوغ مانگا.",
  },
  "landing.f2.t": { en: "Context-aware translation", fa: "ترجمه با آگاهی از بافت" },
  "landing.f2.d": {
    en: "Generate natural Persian dialogue while keeping names and terminology consistent.",
    fa: "دیالوگ فارسی روان تولید می‌شود، همراه با یکدستی نام‌ها و اصطلاح‌ها.",
  },
  "landing.f3.t": { en: "Visual editor", fa: "ویرایشگر بصری" },
  "landing.f3.d": {
    en: "Review, edit, resize and reposition translated text directly on the page.",
    fa: "متن ترجمه‌شده را مستقیم روی صفحه بازبینی، ویرایش، تغییر اندازه و جابه‌جا کنید.",
  },
  "landing.f4.t": { en: "Clean pages", fa: "پاکسازی صفحه‌ها" },
  "landing.f4.d": {
    en: "Remove original text and clean speech bubbles without manually editing every page.",
    fa: "متن اصلی حذف و حباب‌های گفتگو بدون ویرایش دستی هر صفحه پاک می‌شوند.",
  },
  "landing.f5.t": { en: "Persian typesetting", fa: "حروف‌چینی فارسی" },
  "landing.f5.d": {
    en: "RTL-aware Persian text rendering with control over placement and appearance.",
    fa: "رندر متن فارسی راست‌به‌چپ با کنترل کامل روی جای‌گذاری و ظاهر.",
  },
  "landing.f6.t": { en: "One-click export", fa: "خروجی با یک کلیک" },
  "landing.f6.d": {
    en: "Export finished chapters as ready-to-publish image files.",
    fa: "چپترهای آماده را به‌صورت فایل‌های تصویری آماده انتشار خروجی بگیرید.",
  },

  /* ── Landing: see the difference ───────────────────────────────────── */
  "landing.diffTag": { en: "See the output", fa: "خروجی را ببینید" },
  "landing.diffTitle": { en: "See the difference.", fa: "تفاوت را ببینید." },
  "landing.diffSub": {
    en: "Same page. Automated workflow. Persian-ready output.",
    fa: "همان صفحه. گردش کار خودکار. خروجی آماده فارسی.",
  },

  /* ── Landing: real output (CH. 02) ─────────────────────────────────── */
  "landing.outputTitle": {
    en: "Real output. Real chapters.",
    fa: "خروجی واقعی. چپترهای واقعی.",
  },
  "landing.outputSub": {
    en: "See actual pages processed and prepared by the studio.",
    fa: "صفحات واقعی را ببینید که توسط استودیو پردازش و آماده شده‌اند.",
  },

  /* ── Landing: automation value ─────────────────────────────────────── */
  "landing.autoTitle": {
    en: "Stop doing the repetitive work.",
    fa: "کارهای تکراری را رها کنید.",
  },
  "landing.autoSub": {
    en: "Vira automates the repetitive parts while keeping the final result under your control.",
    fa: "ویرا کارهای تکراری را خودکار می‌کند و نتیجه نهایی همچنان در کنترل شماست.",
  },
  "landing.auto.s1.t": { en: "Detect", fa: "تشخیص" },
  "landing.auto.s1.d": { en: "Find text automatically.", fa: "متن به‌صورت خودکار پیدا می‌شود." },
  "landing.auto.s2.t": { en: "Translate", fa: "ترجمه" },
  "landing.auto.s2.d": { en: "Generate a Persian draft.", fa: "پیش‌نویس فارسی تولید می‌شود." },
  "landing.auto.s3.t": { en: "Clean", fa: "پاکسازی" },
  "landing.auto.s3.d": { en: "Remove the original text.", fa: "متن اصلی حذف می‌شود." },
  "landing.auto.s4.t": { en: "Typeset", fa: "حروف‌چینی" },
  "landing.auto.s4.d": { en: "Place Persian text on the page.", fa: "متن فارسی روی صفحه می‌نشیند." },
  "landing.auto.closingA": { en: "You review.", fa: "شما بازبینی می‌کنید." },
  "landing.auto.closingB": { en: "Vira handles the repetition.", fa: "ویرا کار تکراری را انجام می‌دهد." },

  /* ── Landing: how it works (CH. 03) ────────────────────────────────── */
  "landing.howTitle": {
    en: "From chapter to publish-ready pages.",
    fa: "از چپتر تا صفحات آماده انتشار.",
  },
  "landing.step1.t": { en: "Upload", fa: "آپلود" },
  "landing.step1.d": {
    en: "Drop your manga chapter as a PDF.",
    fa: "چپتر مانگا را به‌صورت PDF بارگذاری کنید.",
  },
  "landing.step2.t": { en: "Detect", fa: "تشخیص" },
  "landing.step2.d": {
    en: "Text is detected automatically across every page.",
    fa: "متن در همه صفحات به‌طور خودکار شناسایی می‌شود.",
  },
  "landing.step3.t": { en: "Translate & edit", fa: "ترجمه و ویرایش" },
  "landing.step3.d": {
    en: "AI generates Persian drafts. Review and adjust them in the editor.",
    fa: "هوش مصنوعی پیش‌نویس فارسی تولید می‌کند. در ویرایشگر بازبینی و تنظیمش کنید.",
  },
  "landing.step4.t": { en: "Export", fa: "خروجی" },
  "landing.step4.d": {
    en: "Export your finished pages and publish.",
    fa: "صفحات آماده را خروجی بگیرید و منتشر کنید.",
  },

  /* ── Landing: who it is for ────────────────────────────────────────── */
  "landing.whoTitle": {
    en: "Built for Persian scanlation teams.",
    fa: "ساخته‌شده برای تیم‌های اسکنلیشن فارسی.",
  },
  "landing.who1.t": { en: "Independent translators", fa: "مترجم‌های مستقل" },
  "landing.who1.d": {
    en: "Speed up repetitive production work without giving up manual control.",
    fa: "کارهای تکراری تولید را سریع‌تر کنید، بدون اینکه کنترل دستی را از دست بدهید.",
  },
  "landing.who2.t": { en: "Scanlation teams", fa: "تیم‌های اسکنلیشن" },
  "landing.who2.d": {
    en: "Standardize translation and typesetting across your workflow.",
    fa: "ترجمه و حروف‌چینی را در کل گردش کار تیم استاندارد کنید.",
  },
  "landing.who3.t": { en: "Manga & manhwa publishers", fa: "ناشران مانگا و مانهوا" },
  "landing.who3.d": {
    en: "Reduce repetitive image-processing work before publication.",
    fa: "کارهای تکراری پردازش تصویر را پیش از انتشار کم کنید.",
  },

  /* ── Landing: FAQ ──────────────────────────────────────────────────── */
  "landing.faqTitle": {
    en: "Frequently asked questions.",
    fa: "سؤال‌های پرتکرار.",
  },
  "landing.faq1q": { en: "Is Vira fully automatic?", fa: "آیا ویرا کاملاً خودکار است؟" },
  "landing.faq1a": {
    en: "No. Vira automates repetitive parts of the workflow while keeping the final result editable.",
    fa: "نه. ویرا بخش‌های تکراری گردش کار را خودکار می‌کند و نتیجه نهایی همچنان قابل ویرایش می‌ماند.",
  },
  "landing.faq2q": { en: "Can I edit the translation?", fa: "آیا می‌توانم ترجمه را ویرایش کنم؟" },
  "landing.faq2a": {
    en: "Yes. Detected text and translations can be reviewed and edited in the studio.",
    fa: "بله. متن‌های شناسایی‌شده و ترجمه‌ها را می‌توانید در استودیو بازبینی و ویرایش کنید.",
  },
  "landing.faq3q": {
    en: "Does it support Persian RTL?",
    fa: "از فارسی راست‌به‌چپ پشتیبانی می‌کند؟",
  },
  "landing.faq3a": {
    en: "Yes. The typesetting workflow is designed for Persian and right-to-left text.",
    fa: "بله. گردش کار حروف‌چینی برای فارسی و متن راست‌به‌چپ طراحی شده است.",
  },
  "landing.faq4q": { en: "What files can I upload?", fa: "چه فایل‌هایی می‌توانم آپلود کنم؟" },
  "landing.faq4a": {
    en: "Chapters as PDF files — both manga and manhwa (webtoon) layouts are supported.",
    fa: "چپترها را به‌صورت PDF — هم چیدمان مانگا و هم مانهوا (وبتون) پشتیبانی می‌شود.",
  },
  "landing.faq5q": { en: "Is Vira free?", fa: "آیا ویرا رایگان است؟" },
  "landing.faq5a": {
    en: "Yes. Vira is free to use. Gemini and OpenRouter work with free-tier API keys you add in Settings, and the Custom provider works with any OpenAI-compatible endpoint (including local ones like LM Studio or Ollama).",
    fa: "بله. ویرا رایگان است. Gemini و OpenRouter با کلیدهای رایگانِ در تنظیمات کار می‌کنند، و سرویس سفارشی (Custom) با هر Endpoint سازگار با OpenAI کار می‌کند (حتی سرویس‌های لوکال مثل LM Studio یا Ollama).",
  },

  /* ── Landing: final CTA + footer ───────────────────────────────────── */
  "landing.ctaTitle": {
    en: "Ready to translate your next chapter?",
    fa: "برای ترجمه چپتر بعدی آماده‌اید؟",
  },
  "landing.ctaSub": {
    en: "Upload your pages. Let Vira handle the repetitive work.",
    fa: "صفحاتتان را آپلود کنید. کار تکراری را به ویرا بسپارید.",
  },
  "landing.ctaLine": {
    en: "Detection · Translation · Cleanup · Typesetting",
    fa: "تشخیص · ترجمه · پاکسازی · حروف‌چینی",
  },
  "landing.footer": {
    en: "Translation automation for Persian manga and scanlation teams.",
    fa: "اتوماسیون ترجمه برای مانگا و تیم‌های اسکنلیشن فارسی.",
  },
  "landing.copyright": { en: "© 2026 Vira Studio", fa: "© 2026 ویرا استودیو" },

  "login.tagline": {
    en: "Manga into Persian. Publish-ready in minutes.",
    fa: "مانگا به فارسی. آماده انتشار در چند دقیقه.",
  },

  "ws.noImage": {
    en: "No page image — run Extract OCR first.",
    fa: "تصویری از صفحه نیست — اول استخراج OCR را اجرا کنید.",
  },
  "ws.zoomFit": { en: "Fit", fa: "اندازه پنجره" },
  "ws.zoom100": { en: "Actual size", fa: "اندازه واقعی" },
  "ws.notFound": {
    en: "Project not found — it may have been deleted.",
    fa: "پروژه پیدا نشد — ممکن است حذف شده باشد.",
  },
  "ws.backToProjects": { en: "Back to projects", fa: "بازگشت به پروژه‌ها" },

  "login.welcome": { en: "Welcome back", fa: "خوش برگشتی" },
  "login.subtitle": { en: "Sign in to your studio", fa: "وارد استودیو شوید" },
  "login.username": { en: "Username", fa: "نام کاربری" },
  "login.password": { en: "Password", fa: "رمز عبور" },
  "login.submit": { en: "Sign in", fa: "ورود" },
  "login.submitting": { en: "Signing in…", fa: "در حال ورود…" },

  "dash.libraryIntro": { en: "Your chapters, ready for the next step. Pick up where you left off.", fa: "چپترهای شما آمادهٔ مرحلهٔ بعد هستند. از همان‌جا که متوقف شدید ادامه دهید." },
  "dash.filterProjects": { en: "Filter projects", fa: "فیلتر پروژه‌ها" },
  "dash.search": { en: "Search by name or chapter ID…", fa: "جست‌وجوی نام یا شناسهٔ چپتر…" },
  "dash.clearSearch": { en: "Clear search", fa: "پاک کردن جست‌وجو" },
  "dash.filterStatus": { en: "Filter by status", fa: "فیلتر بر اساس وضعیت" },
  "dash.filterType": { en: "Filter by type", fa: "فیلتر بر اساس نوع" },
  "dash.allStatuses": { en: "All statuses", fa: "همهٔ وضعیت‌ها" },
  "dash.allTypes": { en: "All types", fa: "همهٔ انواع" },
  "dash.refresh": { en: "Refresh projects", fa: "تازه‌سازی پروژه‌ها" },
  "dash.showing": { en: "Showing {count} of {total} projects", fa: "نمایش {count} از {total} پروژه" },
  "dash.clearFilters": { en: "Clear filters", fa: "پاک کردن فیلترها" },
  "dash.noMatches": { en: "No matching projects", fa: "پروژه‌ای پیدا نشد" },
  "dash.noMatchesHint": { en: "Try another name or clear your filters to see every project.", fa: "نام دیگری جست‌وجو کنید یا فیلترها را پاک کنید تا همهٔ پروژه‌ها نمایش داده شوند." },
  "dash.loadError": { en: "Couldn't load your projects", fa: "بارگذاری پروژه‌ها انجام نشد" },
  "dash.loadErrorHint": { en: "Check your connection and try again. Your projects haven't been changed.", fa: "اتصال خود را بررسی کنید و دوباره تلاش کنید. پروژه‌های شما تغییری نکرده‌اند." },
  "dash.retry": { en: "Try again", fa: "تلاش دوباره" },
  "dash.previewPending": { en: "Page preview unavailable", fa: "پیش‌نمایش صفحه در دسترس نیست" },
  "dash.translationProgress": { en: "Translation progress", fa: "پیشرفت ترجمه" },
  "dash.waitingForOcr": { en: "Extract text to start translating", fa: "برای شروع ترجمه، متن را استخراج کنید" },
  "dash.projectFailed": { en: "The last step failed. Open the studio to review the details.", fa: "مرحلهٔ آخر ناموفق بود. برای بررسی جزئیات، استودیو را باز کنید." },
  "dash.reviewProject": { en: "Open to review", fa: "باز کردن برای بررسی" },
  "dash.deleteNamed": { en: 'Delete "{name}"', fa: "حذف «{name}»" },
  "dash.deleting": { en: "Deleting…", fa: "در حال حذف…" },
  "dash.deleted": { en: "Project deleted", fa: "پروژه حذف شد" },
  "dash.deleteError": { en: "Couldn't delete the project. Please try again.", fa: "حذف پروژه انجام نشد. دوباره تلاش کنید." },
  "dash.createIntro": { en: "Start with a PDF. We'll open your workspace as soon as it's uploaded.", fa: "با یک PDF شروع کنید. پس از بارگذاری، فضای کاری شما باز می‌شود." },
  "dash.dropPdf": { en: "Drop your PDF here", fa: "فایل PDF را اینجا رها کنید" },
  "dash.pdfOnly": { en: "PDF files · Manga or Manhwa", fa: "فایل PDF · مانگا یا وبتون" },
  "dash.linkTab": { en: "Link", fa: "لینک" },
  "dash.fileTab": { en: "PDF file", fa: "فایل PDF" },
  "dash.chapterUrl": { en: "Chapter URL", fa: "لینک فصل" },
  "dash.chapterUrlHint": { en: "Paste a public chapter webpage URL. We'll find the page images for you to select.", fa: "لینک عمومی صفحه فصل را وارد کنید. تصاویر صفحات را برای انتخاب پیدا می‌کنیم." },
  "dash.findImages": { en: "Find images", fa: "یافتن تصاویر" },
  "dash.selectImagesHint": { en: "Select the page images to import; exclude logos and ads.", fa: "تصاویر صفحات را برای ورود انتخاب کنید؛ لوگو و تبلیغات را حذف کنید." },
  "dash.selectAll": { en: "Select all", fa: "انتخاب همه" },
  "dash.clearSelection": { en: "Clear selection", fa: "لغو انتخاب" },
  "dash.importSelected": { en: "Import selected pages", fa: "ورود صفحات انتخابی" },
  "dash.importing": { en: "Importing pages…", fa: "در حال ورود صفحات…" },
  "dash.linkError": { en: "Could not load images from this link. Make sure it's a public chapter page.", fa: "بارگذاری تصاویر از این لینک انجام نشد. مطمئن شوید این یک صفحه فصل عمومی است." },
  "dash.noImagesFound": { en: "No page images found on this page.", fa: "هیچ تصویر صفحه‌ای در این صفحه یافت نشد." },
  "dash.truncatedHint": { en: "Only the first 300 images are shown for very long chapters.", fa: "برای فصل‌های خیلی طولانی فقط ۳۰۰ تصویر اول نمایش داده می‌شود." },
  "dash.removeImage": { en: "Remove image", fa: "حذف تصویر" },
  "dash.importedChapter": { en: "Imported chapter", fa: "فصل واردشده" },
  "dash.replaceFile": { en: "Change file", fa: "تغییر فایل" },
  "dash.invalidPdf": { en: "Choose a non-empty PDF file to continue.", fa: "برای ادامه، یک فایل PDF غیرخالی انتخاب کنید." },
  "dash.mangaHint": { en: "Page-based chapters", fa: "چپترهای صفحه‌بندی‌شده" },
  "dash.manhwaHint": { en: "Vertical, scrolling pages", fa: "صفحات عمودی و بلند" },
  "dash.additionalDetails": { en: "Additional details", fa: "جزئیات بیشتر" },
  "dash.createAndOpen": { en: "Create & open studio", fa: "ساخت و ورود به استودیو" },
  "dash.uploadWait": { en: "Uploading your PDF. Keep this window open.", fa: "فایل PDF در حال بارگذاری است. این پنجره را باز نگه دارید." },
  "dash.uploadError": { en: "Upload failed. Check your connection and PDF, then try again.", fa: "بارگذاری ناموفق بود. اتصال و فایل PDF را بررسی و دوباره تلاش کنید." },
  "dash.newProject": { en: "New project", fa: "پروژه جدید" },
  "dash.dropHere": {
    en: "Drag & drop a PDF here, or click to browse",
    fa: "PDF را اینجا رها کنید یا برای انتخاب کلیک کنید",
  },
  "dash.projectName": { en: "Project name", fa: "نام پروژه" },
  "dash.type": { en: "Type", fa: "نوع" },
  "dash.manga": { en: "Manga", fa: "مانگا" },
  "dash.manhwa": { en: "Manhwa", fa: "وبتون" },
  "dash.chapterId": { en: "Chapter ID (optional)", fa: "شناسه چپتر (اختیاری)" },
  "dash.file": { en: "PDF file", fa: "فایل PDF" },
  "dash.chooseFile": { en: "Choose file", fa: "انتخاب فایل" },
  "dash.changeFile": { en: "Click to change", fa: "برای تغییر کلیک کنید" },
  "dash.create": { en: "Create project", fa: "ساخت پروژه" },
  "dash.creating": { en: "Uploading…", fa: "در حال آپلود…" },
  "dash.myProjects": { en: "Your projects", fa: "پروژه‌های شما" },
  "dash.emptyTitle": { en: "No projects yet", fa: "هنوز پروژه‌ای نیست" },
  "dash.emptySub": {
    en: "Drop your first PDF here, or create a project to start translating your next chapter.",
    fa: "اولین PDF خود را اینجا رها کنید یا برای شروع ترجمهٔ چپتر بعدی یک پروژه بسازید.",
  },
  "dash.open": { en: "Open studio", fa: "باز کردن استودیو" },
  "dash.delete": { en: "Delete", fa: "حذف" },
  "dash.deleteTitle": { en: "Delete project", fa: "حذف پروژه" },
  "dash.deleteBody": {
    en: 'Delete "{name}"? Page images and exports are removed too.',
    fa: "«{name}» حذف شود؟ تصاویر صفحات و خروجی‌ها هم پاک می‌شوند.",
  },
  "dash.fileSize": { en: "Size", fa: "حجم" },
  "dash.removeFile": { en: "Remove file", fa: "برداشتن فایل" },
  "dash.confirmDelete": {
    en: "Delete project?",
    fa: "پروژه حذف شود؟",
  },
  "dash.pages": { en: "pages", fa: "صفحه" },
  "dash.blocks": { en: "blocks", fa: "بلوک" },
  "dash.translatedOf": { en: "{a}/{b} translated", fa: "{a} از {b} ترجمه‌شده" },

  "status.created": { en: "Created", fa: "ساخته‌شده" },
  "status.extracting": { en: "Extracting", fa: "در حال استخراج" },
  "status.ready": { en: "Ready", fa: "آماده" },
  "status.translating": { en: "Translating", fa: "در حال ترجمه" },
  "status.applying": { en: "Rendering", fa: "در حال رندر" },
  "status.done": { en: "Done", fa: "تمام" },
  "status.failed": { en: "Failed", fa: "ناموفق" },

  "ws.extractPages": { en: "Extract pages", fa: "استخراج صفحات" },
  "ws.ocrEngine": { en: "OCR engine", fa: "موتور OCR" },
  "ws.provider": { en: "Translation provider", fa: "سرویس ترجمه" },
  "ws.export": { en: "Export", fa: "خروجی" },
  "ws.previewUnavailable": { en: "Preview unavailable", fa: "پیش‌نمایش در دسترس نیست" },
  "transfer.title": { en: "OCR text / translations", fa: "متن OCR / ترجمه‌ها" },
  "transfer.export": { en: "Export originals & translations (.json)", fa: "خروجی متن اصلی و ترجمه‌ها (.json)" },
  "transfer.upload": { en: "Upload translation file (.json)", fa: "بارگذاری فایل ترجمه (.json)" },
  "transfer.readFailed": { en: "Could not read this file. Try again or paste its contents below.", fa: "خواندن فایل ناموفق بود. دوباره تلاش کنید یا محتوای آن را در کادر زیر بچسبانید." },
  "transfer.import": { en: "Import translations", fa: "ورود ترجمه‌ها" },
  "transfer.scope": { en: "Pages", fa: "صفحه‌ها" },
  "transfer.current": { en: "Current page", fa: "صفحه فعلی" },
  "transfer.all": { en: "All pages", fa: "همه صفحه‌ها" },
  "transfer.hint": { en: "Export JSON, edit the translated values, then upload or paste the file here. Keep project_id and [[block IDs]] unchanged. Use \\n for line breaks in JSON strings. Blank translations are skipped; original text is never changed. Older marked .txt files are also accepted.", fa: "فایل JSON را خروجی بگیرید، مقدارهای translated را ویرایش کنید و فایل را بارگذاری کنید یا اینجا بچسبانید. project_id و شناسه‌های [[بلوک]] را تغییر ندهید. برای شکست خط در رشته‌های JSON از \\n استفاده کنید. ترجمه‌های خالی نادیده گرفته می‌شوند و متن اصلی تغییر نمی‌کند. فایل‌های قدیمی .txt با نشانگر نیز پذیرفته می‌شوند." },
  "transfer.paste": { en: "Paste translation JSON", fa: "محتوای JSON ترجمه را بچسبانید" },
  "transfer.preview": { en: "Preview import", fa: "پیش‌نمایش ورود" },
  "transfer.new": { en: "New translations", fa: "ترجمه‌های جدید" },
  "transfer.replace": { en: "Replacements", fa: "جایگزینی‌ها" },
  "transfer.unchanged": { en: "Unchanged", fa: "بدون تغییر" },
  "transfer.skipped": { en: "Blank blocks skipped", fa: "بلوک‌های خالی نادیده گرفته‌شده" },
  "transfer.confirm": { en: "I confirm replacing the existing translations shown below.", fa: "جایگزینی ترجمه‌های موجود نمایش‌داده‌شده را تأیید می‌کنم." },
  "transfer.apply": { en: "Apply and save translations", fa: "اعمال و ذخیره ترجمه‌ها" },
  "transfer.saving": { en: "Saving…", fa: "در حال ذخیره…" },
  "transfer.saved": { en: "Translations saved", fa: "ترجمه‌ها ذخیره شدند" },
  "transfer.failed": { en: "Could not save these blocks. Your pasted text is retained; preview again to retry.", fa: "ذخیره این بلوک‌ها ناموفق بود. متن ورودی حفظ شده؛ برای تلاش دوباره پیش‌نمایش بگیرید." },
  "transfer.stale": { en: "Blocks changed. Preview again before importing.", fa: "بلوک‌ها تغییر کرده‌اند. پیش از ورود دوباره پیش‌نمایش بگیرید." },
  "transfer.format": { en: "Invalid file format. Use exported JSON with project_id, blocks, and string original/translated values, or an unchanged legacy marked-text structure.", fa: "قالب فایل نامعتبر است. از JSON خروجی با project_id، blocks و مقدارهای متنی original و translated یا ساختار صحیح متن قدیمی با نشانگر استفاده کنید." },
  "transfer.project": { en: "This text belongs to a different project.", fa: "این متن مربوط به پروژه دیگری است." },
  "transfer.duplicate": { en: "A block marker appears more than once.", fa: "یک نشانگر بلوک بیش از یک بار تکرار شده است." },
  "transfer.unknown": { en: "Unknown block or page outside the selected scope. Check the scope or export again after OCR.", fa: "بلوک ناشناخته یا صفحه خارج از محدوده انتخاب‌شده است. محدوده را بررسی کنید یا پس از OCR دوباره خروجی بگیرید." },
  "ws.format": { en: "Format", fa: "قالب" },
  "ws.translateAll": { en: "Translate all", fa: "ترجمه همه" },
  "ws.clean": { en: "Clean", fa: "پاکسازی" },
  "ws.render": { en: "Render text", fa: "رندر متن" },
  "ws.finish": { en: "Finish", fa: "اتمام" },
  "ws.finishing": { en: "Finishing…", fa: "در حال اتمام…" },
  "ws.finishHint": {
    en: "Run the remaining steps automatically: Clean → Render → Export",
    fa: "اجرای خودکار مراحل باقی‌مانده: پاکسازی → رندر → خروجی",
  },
  "ws.needExtract": { en: "Extract pages first", fa: "اول صفحات را استخراج کنید" },
  "ws.needClean": { en: "Clean pages first", fa: "اول صفحات را پاکسازی کنید" },
  "ws.needTranslate": { en: "Translate blocks first", fa: "اول بلوک‌ها را ترجمه کنید" },
  "ws.needRender": { en: "Render text first", fa: "اول متن را رندر کنید" },
  "ws.jobRunning": { en: "A job is running…", fa: "یک کار در حال اجرا است…" },
  "ws.cleanPage": { en: "Clean page", fa: "پاکسازی صفحه" },
  "ws.toolSelect": { en: "Select tool", fa: "ابزار انتخاب" },
  "ws.toolBrush": { en: "Clean brush — paint areas to erase", fa: "قلم‌موی پاکسازی — ناحیه‌ها را رنگ کنید" },
  "ws.toolEraser": { en: "Erase marks", fa: "پاک کردن نشانه‌ها" },
  "ws.toolCrop": { en: "Crop page — drag a rectangle to keep", fa: "برش صفحه — مستطیل ناحیه نگه‌داشتنی را بکشید" },
  "ws.cropApply": { en: "Crop", fa: "برش" },
  "ws.cropCancel": { en: "Cancel crop", fa: "لغو برش" },
  "ws.reclean": { en: "Re-clean", fa: "پاکسازی دوباره" },
  "ws.jumpTo": { en: "Jump to page", fa: "برو به صفحه" },
  "ws.filterUntranslated": { en: "Untranslated only", fa: "فقط بدون ترجمه" },
  "ws.searchBlocks": { en: "Search blocks…", fa: "جستجوی بلوک‌ها…" },
  "ws.noMatch": { en: "No blocks match.", fa: "بلوکی مطابقت ندارد." },
  "ws.hintShortcuts": {
    en: "←/→ pages · 1/2/3 views · Del delete box · Esc select tool",
    fa: "→/← صفحه · ۱/۲/۳ نما · Del حذف کادر · Esc ابزار انتخاب",
  },
  "ws.translatePage": { en: "Translate page", fa: "ترجمه صفحه" },
  "ws.multiSelected": { en: "{n} boxes selected", fa: "{n} کادر انتخاب‌شده" },
  "ws.deleteAll": { en: "Delete all", fa: "حذف همه" },
  "ws.copyStyle": { en: "Copy style", fa: "کپی استایل" },
  "ws.pasteStyle": { en: "Paste style", fa: "چسباندن استایل" },
  "ws.applyStylePage": { en: "To whole page", fa: "به کل صفحه" },
  "ws.styleCopied": { en: "Style copied", fa: "استایل کپی شد" },
  "ws.stylePasted": { en: "Style applied", fa: "استایل اعمال شد" },
  "ws.nothingToPaste": { en: "Copy a style first", fa: "اول یک استایل کپی کنید" },
  "ws.fontsFailed": { en: "Fonts couldn't load", fa: "بارگذاری فونت‌ها ناموفق بود" },
  "ws.retry": { en: "Retry", fa: "تلاش دوباره" },
  "ws.reocr": { en: "Re-OCR page", fa: "OCR دوباره صفحه" },
  "ws.deleteBox": { en: "Delete box", fa: "حذف کادر" },
  "ws.nextUntranslated": { en: "Next untranslated", fa: "بعدی بدون ترجمه" },
  "ws.undo": { en: "Undo", fa: "واگرد" },
  "ws.redo": { en: "Redo", fa: "از نو" },
  "ws.brushSize": { en: "Brush size (px)", fa: "اندازه قلم‌مو (پیکسل)" },
  "set.keysHint": {
    en: "Environment variables OPENROUTER_API_KEY / GEMINI_API_KEY / CUSTOM_BASE_URL override values saved here.",
    fa: "متغیرهای محیطی OPENROUTER_API_KEY / GEMINI_API_KEY / CUSTOM_BASE_URL بر مقادیر ذخیره‌شدهٔ اینجا اولویت دارند.",
  },
  "set.keyOpenrouter": { en: "OpenRouter API key", fa: "کلید API اوپن‌روتر" },
  "set.keyGemini": { en: "Gemini API key", fa: "کلید API جِمینای" },
  "set.keyCustom": { en: "Custom API key (optional)", fa: "کلید API سفارشی (اختیاری)" },
  "set.baseUrl": { en: "Base URL", fa: "آدرس پایه (Endpoint)" },
  "set.customHint": {
    en: "any OpenAI-compatible endpoint",
    fa: "هر سرویس سازگار با OpenAI",
  },
  "set.inUse": { en: "In use", fa: "در حال استفاده" },
  "set.testConn": { en: "Test", fa: "تست" },
  "set.testTrying": { en: "Testing…", fa: "در حال تست…" },
  "set.testOk": { en: "Connected", fa: "ارتباط برقرار شد" },
  "set.testFail": { en: "Connection failed", fa: "اتصال ناموفق" },
  "set.helpOpenrouter": {
    en: "Create a free key — models marked :free need no credit card.",
    fa: "کلید رایگان بساز — مدل‌های دارای پسوندِ :free کارت بانکی نمی‌خواهند.",
  },
  "set.helpGemini": {
    en: "Free tier via Google AI Studio, no credit card. Limit: about 15 requests/min on flash models.",
    fa: "سرویس رایگان از طریق Google AI Studio، بدون کارت بانکی. محدودیت: حدود ۱۵ درخواست در دقیقه.",
  },
  "set.helpCustom": {
    en: "Any OpenAI-compatible endpoint: LM Studio (http://localhost:1234/v1), Ollama (http://localhost:11434/v1), relay servers like one-api/new-api. The model name must match the server exactly.",
    fa: "هر سرویس سازگار با OpenAI: مثل LM Studio (http://localhost:1234/v1)، Ollama (http://localhost:11434/v1) یا رله‌ها (one-api/new-api). نام مدل باید دقیقاً با نامی که سرویس می‌دهد یکی باشد.",
  },
  "set.helpKeys": {
    en: "Get a key",
    fa: "ساخت کلید",
  },
  "set.showKey": { en: "Show key", fa: "نمایش کلید" },
  "set.hideKey": { en: "Hide key", fa: "پنهان کردن کلید" },
  "set.fontMin": { en: "Min font size (px)", fa: "کمینه اندازه فونت (px)" },
  "set.fontMax": { en: "Max font size (px)", fa: "بیشینه اندازه فونت (px)" },
  "set.model": { en: "Model", fa: "مدل" },
  "guide.scNext": { en: "Next untranslated block", fa: "بلوک بعدی بدون ترجمه" },
  "ws.original": { en: "Original", fa: "اصلی" },
  "ws.cleaned": { en: "Cleaned", fa: "پاکسازی‌شده" },
  "ws.rendered": { en: "Rendered", fa: "رندرشده" },
  "ws.untranslated": { en: "untranslated", fa: "بدون ترجمه" },
  "ws.hint": {
    en: "Drag to move · corner handle to resize · double-click box to edit · double-click empty area to add",
    fa: "کشیدن = جابه‌جایی · گوشه = تغییر اندازه · دوبار کلیک روی کادر = ویرایش · دوبار کلیک روی فضای خالی = کادر جدید",
  },
  "ws.noPages": { en: "No pages yet", fa: "هنوز صفحه‌ای نیست" },
  "ws.noBlocks": { en: "No blocks on this page.", fa: "این صفحه بلوکی ندارد." },
  "ws.page": { en: "Page", fa: "صفحه" },
  "ws.exportsReady": { en: "Exports ready:", fa: "خروجی‌ها آماده:" },
  "ws.log": { en: "log", fa: "لاگ" },
  "ws.hideLog": { en: "hide", fa: "پنهان" },
  "ws.cancel": { en: "Cancel", fa: "لغو" },
  "ws.cancelling": { en: "Cancelling…", fa: "در حال لغو…" },

  // Canvas guide modal (opened from the workspace header "?" button)
  "ws.guide": { en: "Guide", fa: "راهنما" },
  "guide.workflow": { en: "Workflow", fa: "گردش کار" },
  "guide.stepExtract": {
    en: "Scan pages and detect the text blocks",
    fa: "اسکن صفحه‌ها و شناسایی بلوک‌های متن",
  },
  "guide.stepTranslate": {
    en: "AI translates every block with your provider",
    fa: "هوش مصنوعی همه بلوک‌ها را با سرویس انتخابی ترجمه می‌کند",
  },
  "guide.stepClean": {
    en: "Erase the original text from the pages",
    fa: "متن اصلی از صفحه‌ها پاک می‌شود",
  },
  "guide.stepRender": {
    en: "Typeset the translations onto the pages",
    fa: "ترجمه‌ها با حروف‌چینی روی صفحه‌ها می‌نشینند",
  },
  "guide.stepExport": {
    en: "Download the finished files",
    fa: "فایل‌های نهایی را دانلود کنید",
  },
  "guide.views": { en: "Views", fa: "نماها" },
  "guide.viewOriginal": {
    en: "Editable — boxes visible; move, resize, type",
    fa: "قابل ویرایش — کادرها دیده می‌شوند؛ جابه‌جایی، تغییر اندازه، تایپ",
  },
  "guide.viewCleaned": {
    en: "Original text removed — proof the erase result",
    fa: "متن اصلی حذف شده — نتیجه پاکسازی را بازبینی کنید",
  },
  "guide.viewRendered": {
    en: "Final pages with your translations",
    fa: "صفحه‌های نهایی با ترجمه‌های شما",
  },
  "guide.editing": { en: "Editing boxes (Original view)", fa: "ویرایش کادرها (نمای اصلی)" },
  "guide.editMove": { en: "Drag a box to move it", fa: "برای جابه‌جایی، کادر را بکشید" },
  "guide.editResize": {
    en: "Resize from any corner or edge handle",
    fa: "تغییر اندازه از هر گوشه یا لبه کادر",
  },
  "guide.editText": {
    en: "Double-click a box to edit its translation",
    fa: "برای ویرایش ترجمه، روی کادر دوبار کلیک کنید",
  },
  "guide.editAdd": {
    en: "Double-click empty canvas to add a box",
    fa: "برای افزودن کادر جدید، روی فضای خالی دوبار کلیک کنید",
  },
  "guide.editDelete": {
    en: "Select a box, then Delete key or the Delete box button",
    fa: "کادر را انتخاب کنید، کلید Delete یا دکمه حذف کادر",
  },
  "guide.cleanBrush": { en: "Clean brush (Original view)", fa: "قلم‌موی پاکسازی (نمای اصلی)" },
  "guide.brushPaint": {
    en: "Paint over any text to mark it for erasing",
    fa: "روی متنی که باید پاک شود، رنگ بکشید",
  },
  "guide.brushErase": {
    en: "Eraser removes painted marks",
    fa: "پاک‌کن نشانه‌های رنگ‌شده را برمی‌دارد",
  },
  "guide.brushReclean": {
    en: "Re-clean inpaints the marked areas",
    fa: "پاکسازی دوباره ناحیه‌های نشانه‌گذاری‌شده را ترمیم می‌کند",
  },
  "guide.brushReocr": {
    en: "Re-OCR re-reads the page's text",
    fa: "OCR دوباره متن صفحه را از نو می‌خواند",
  },
  "guide.editZoom": {
    en: "Ctrl+wheel zooms the page · hold Space and drag (or middle-drag) to pan",
    fa: "با Ctrl+چرخ ماوس صفحه را بزرگ/کوچک کنید · با نگه‌داشتن Space و کشیدن (یا دکمه وسط ماوس) جابه‌جا شوید",
  },
  "guide.editMulti": {
    en: "Drag on empty canvas to box-select · Shift+click adds boxes · then move or delete them together",
    fa: "روی فضای خالی صفحه بکشید تا چند کادر با هم انتخاب شود · Shift+کلیک کادرها را اضافه/کم می‌کند · سپس همه را هم‌زمان بکشید یا حذف کنید",
  },
  "guide.editNudge": {
    en: "With a selected box, arrow keys move it 1px (Shift = 10px); pages still switch when nothing is selected",
    fa: "وقتی کادری انتخاب شده، کلیدهای جهت‌دار آن را ۱ پیکسل جابه‌جا می‌کنند (با Shift ده پیکسل)؛ وقتی چیزی انتخاب نباشد، صفحات عوض می‌شوند",
  },
  "guide.editTab": {
    en: "Tab / Shift+Tab move to the next/previous dialog — write, Tab, write",
    fa: "کلید Tab / Shift+Tab به دیالوگ بعدی/قبلی می‌رود — بنویسید، Tab، بنویسید",
  },
  "guide.editStyle": {
    en: "Style copy/paste: copy a dialog's font, size, color and rotation, then paste onto other dialogs or the whole page (one undo)",
    fa: "کپی استایل: فونت، اندازه، رنگ و چرخش یک دیالوگ را کپی کنید و روی دیالوگ‌های دیگر یا کل صفحه بچسبانید (یک بازگردانی)",
  },
  "guide.scZoom": { en: "Zoom / pan", fa: "بزرگ‌نمایی / جابه‌جایی" },
  "guide.scTab": { en: "Next / previous dialog", fa: "دیالوگ بعدی / قبلی" },
  "guide.scNudge": { en: "Move selection 1px / 10px", fa: "جابه‌جایی انتخاب ۱ پیکسل / ۱۰ پیکسل" },
  "guide.shortcuts": { en: "Shortcuts", fa: "میان‌برها" },
  "guide.scPages": { en: "Previous / next page", fa: "صفحه قبل / بعد" },
  "guide.scViews": { en: "Switch view", fa: "تعویض نما" },
  "ws.translationPlaceholder": { en: "Persian translation…", fa: "ترجمه فارسی…" },
  "ws.type": { en: "Type", fa: "نوع" },
  "pages.link": { en: "Load pages from link", fa: "بارگذاری صفحات از لینک" },
  "pages.url": { en: "Chapter URL", fa: "لینک فصل" },
  "pages.linkHint": { en: "Paste a public chapter webpage. Select and order its images to append pages without changing existing translations. Login-protected and JavaScript-only readers may not work.", fa: "لینک عمومی فصل را وارد کنید. تصاویر را انتخاب و مرتب کنید تا بدون تغییر ترجمه‌های قبلی اضافه شوند. سایت‌های نیازمند ورود یا جاوااسکریپت ممکن است پشتیبانی نشوند." },
  "pages.find": { en: "Find images", fa: "یافتن تصاویر" },
  "pages.selectHint": { en: "Choose page images; exclude logos and ads.", fa: "تصاویر صفحات را انتخاب کنید؛ لوگو و تبلیغات را حذف کنید." },
  "pages.toggleAll": { en: "Select / clear all", fa: "انتخاب / لغو همه" },
  "pages.append": { en: "Add selected pages", fa: "افزودن صفحات انتخابی" },
  "pages.up": { en: "Move page up", fa: "انتقال به بالا" },
  "pages.down": { en: "Move page down", fa: "انتقال به پایین" },
  "pages.delete": { en: "Delete page", fa: "حذف صفحه" },
  "pages.deleteWarning": { en: "This permanently removes the page, its translations, boxes, and cleaning marks. Other pages are not changed.", fa: "این کار صفحه، ترجمه‌ها، کادرها و نشانه‌های پاک‌سازی آن را برای همیشه حذف می‌کند. سایر صفحات تغییر نمی‌کنند." },
  "pages.addPages": { en: "Add pages from images", fa: "افزودن صفحه از تصویر" },
  "pages.appendHint": { en: "Upload JPG, PNG, WEBP or GIF files (up to 20 at once). Later pages are renumbered so numbering stays dense.", fa: "فایل‌های JPG ،PNG ،WEBP یا GIF را بارگذاری کنید (حداکثر ۲۰ فایل همزمان). شماره صفحات بعدی جابه‌جا می‌شود تا شماره‌گذاری پیوسته بماند." },
  "pages.chooseImages": { en: "Choose image files", fa: "انتخاب فایل‌های تصویری" },
  "pages.imagesOnly": { en: "Only JPG, PNG, WEBP or GIF images.", fa: "فقط تصاویر JPG ،PNG ،WEBP یا GIF." },
  "pages.maxFiles": { en: "Upload 1 to {max} images at a time.", fa: "هر بار ۱ تا {max} تصویر بارگذاری کنید." },
  "pages.maxOneFile": { en: "Each image must be a non-empty file under 20 MB.", fa: "هر تصویر باید فایل غیرخالی کمتر از ۲۰ مگابایت باشد." },
  "pages.maxTotal": { en: "Images exceed 500 MB in total.", fa: "مجموع تصاویر از ۵۰۰ مگابایت بیشتر است." },
  "pages.removeImage": { en: "Remove image", fa: "حذف تصویر" },
  "pages.insertPosition": { en: "Insert position", fa: "محل درج" },
  "pages.insertStart": { en: "At the start", fa: "در ابتدا" },
  "pages.insertAfter": { en: "After page {page}", fa: "بعد از صفحه {page}" },
  "pages.insertEnd": { en: "At the end", fa: "در انتها" },
  "pages.upload": { en: "Upload {count} pages", fa: "بارگذاری {count} صفحه" },
  "pages.uploading": { en: "Uploading pages…", fa: "در حال بارگذاری صفحات…" },
  "pages.appended": { en: "Added {count} pages", fa: "{count} صفحه اضافه شد" },
  "pages.cropTitle": { en: "Crop page", fa: "برش صفحه" },
  "pages.cropBody": { en: "Keep {kept} boxes fully inside and delete {removed} touching outside? Cleaned and rendered previews for this page will be rebuilt.", fa: "{kept} کادر کاملاً داخل نگه داشته و {removed} کادر مماس با بیرون حذف شود؟ پیش‌نمایش‌های تمیزشده و رندرشده این صفحه بازسازی می‌شوند." },
  "pages.cropEmpty": { en: "The crop keeps no text boxes. Crop anyway?", fa: "برش هیچ کادر متنی نگه نمی‌دارد. باز هم برش انجام شود؟" },
  "pages.cropped": { en: "Page cropped: {kept} boxes kept, {removed} removed", fa: "صفحه برش خورد: {kept} کادر نگه داشته شد، {removed} حذف شد" },
  "pages.cropTooSmall": { en: "Crop must be at least 50×50 px.", fa: "برش باید حداقل ۵۰×۵۰ پیکسل باشد." },
  "pages.cancel": { en: "Cancel", fa: "انصراف" },
  "ws.alignment": { en: "Alignment", fa: "چینش" },
  "ws.rotation": { en: "Rotation", fa: "چرخش" },
  "ws.rotationDegrees": { en: "Rotation (degrees)", fa: "چرخش (درجه)" },
  "ws.color": { en: "Color", fa: "رنگ" },
  "ws.fontSize": { en: "Font size override", fa: "اندازه فونت دستی" },
  "ws.font": { en: "Font", fa: "فونت" },

  "modal.extractTitle": { en: "Extract (OCR)", fa: "استخراج (OCR)" },
  "modal.docType": { en: "Document type", fa: "نوع سند" },
  "modal.covers": { en: "Cover pages", fa: "صفحات کاور" },
  "modal.coversHint": { en: "comma-separated", fa: "با کاما جدا کنید" },
  "modal.skip": { en: "Skip pages", fa: "صفحات رد شده" },
  "modal.skipHint": { en: "OCR ignores these", fa: "OCR نادیده می‌گیرد" },
  "modal.reExtractWarn": {
    en: "Re-extracting replaces all detected blocks and translations.",
    fa: "استخراج مجدد همه بلوک‌ها و ترجمه‌ها را جایگزین می‌کند.",
  },
  "modal.startExtract": { en: "Start extraction", fa: "شروع استخراج" },
  "modal.applyTitle": { en: "Apply & Export", fa: "اعمال و خروجی" },
  "modal.chapterStamp": { en: "Chapter ID stamp", fa: "مهر شناسه چپتر" },
  "modal.optional": { en: "optional", fa: "اختیاری" },
  "modal.formats": { en: "Output formats", fa: "فرمت‌های خروجی" },
  "modal.renderBtn": { en: "Render & export", fa: "رندر و خروجی" },
  "modal.cancel": { en: "Cancel", fa: "انصراف" },

  "set.title": { en: "Studio Settings", fa: "تنظیمات استودیو" },
  "set.save": { en: "Save changes", fa: "ذخیره تغییرات" },
  "set.saving": { en: "Saving…", fa: "در حال ذخیره…" },
  "set.saved": { en: "Saved", fa: "ذخیره شد" },
  "set.sec.translator": { en: "Translator", fa: "مترجم" },
  "set.sec.ocr": { en: "OCR", fa: "OCR" },
  "set.sec.font": { en: "Fonts & Text", fa: "فونت و متن" },
  "set.sec.chapter_id": { en: "Chapter ID", fa: "شناسه چپتر" },
  "set.sec.inpaint": { en: "Inpainting", fa: "پاکسازی" },
  "set.sec.typography": { en: "Typography", fa: "تایپوگرافی" },
  "set.autoDetect": { en: "Auto-detect", fa: "تشخیص خودکار" },
  "set.inherit": { en: "(inherit)", fa: "(پیش‌فرض)" },
  "set.emptyValue": { en: "(empty)", fa: "(خالی)" },
  "set.subtitle": {
    en: "Global defaults used by every project's jobs.",
    fa: "پیش‌فرض‌های سراسری که در کارهای همه پروژه‌ها اعمال می‌شود.",
  },
  "set.unsaved": { en: "unsaved changes", fa: "تغییر ذخیره‌نشده" },

  /* Section descriptions (shown at the top of each tab panel) */
  "set.desc.translator": {
    en: "Choose the translation provider, tune each request, and edit the prompts used for every job.",
    fa: "سرویس‌دهنده ترجمه را انتخاب کنید، درخواست‌ها را تنظیم کنید و پرامپت‌های هر کار را ویرایش کنید.",
  },
  "set.desc.ocr": {
    en: "How pages are scanned and text blocks are detected.",
    fa: "نحوه اسکن صفحه‌ها و شناسایی بلوک‌های متن.",
  },
  "set.desc.font": {
    en: "Typefaces used for rendering, plus sizes and text colors.",
    fa: "فونت‌های حروف‌چینی به‌همراه اندازه‌ها و رنگ‌های متن.",
  },
  "set.desc.chapter_id": {
    en: "The chapter stamp drawn onto exported pages.",
    fa: "مهر شناسه چپتری که روی صفحه‌های خروجی درج می‌شود.",
  },
  "set.desc.inpaint": {
    en: "How the original text is erased from pages before typesetting.",
    fa: "نحوه پاک شدن متن اصلی از صفحه‌ها پیش از حروف‌چینی.",
  },
  "set.desc.typography": {
    en: "How rendered text picks its color from the original page.",
    fa: "نحوه هم‌رنگ شدن متن رندرشده با رنگ صفحه اصلی.",
  },

  /* Group headings inside a tab panel */
  "set.grp.provider": { en: "Provider", fa: "سرویس‌دهنده" },
  "set.grp.prompts": { en: "Prompts", fa: "پرامپت‌ها" },
  "set.grp.engine": { en: "Engine", fa: "موتور" },
  "set.grp.detection": { en: "Detection", fa: "تشخیص" },
  "set.grp.pages": { en: "Pages & chunks", fa: "صفحه‌ها و تکه‌ها" },
  "set.grp.strips": { en: "Long strips (webtoon)", fa: "نوارهای بلند (وبتون)" },
  "set.grp.fonts": { en: "Fonts", fa: "فونت‌ها" },
  "set.grp.size": { en: "Font size", fa: "اندازه فونت" },
  "set.grp.colorMatch": { en: "Color matching", fa: "تطبیق رنگ" },
  "set.grp.general": { en: "General", fa: "عمومی" },
  "set.grp.opencv": { en: "OpenCV", fa: "OpenCV" },
  "set.grp.autoMode": { en: "Auto mode", fa: "حالت خودکار" },
  "set.grp.neural": { en: "Neural (LaMa)", fa: "شبکه عصبی (LaMa)" },
  "set.grp.pcleaner": { en: "PCleaner", fa: "PCleaner" },
  "set.grp.other": { en: "Other", fa: "سایر" },

  /* Field labels + hints for the fields users touch most; unlisted fields
     fall back to a humanized version of the raw config key. */
  "set.temperature": { en: "Temperature", fa: "Temperature (خلاقیت)" },
  "set.chunkSize": { en: "Lines per request", fa: "دیالوگ در هر درخواست" },
  "set.systemPrompt": { en: "System prompt", fa: "پرامپت سیستمی" },
  "set.userPrompt": { en: "User prompt", fa: "پرامپت کاربر" },
  "set.fontNormal": { en: "Dialogue font", fa: "فونت دیالوگ" },
  "set.fontSfx": { en: "SFX font", fa: "فونت افکت صوتی" },
  "set.fontThinking": { en: "Thought-bubble font", fa: "فونت حباب فکر" },
  "set.textColor": { en: "Text color", fa: "رنگ متن" },
  "set.strokeWidth": { en: "Stroke width", fa: "ضخامت دورخط" },
  "set.strokeColor": { en: "Stroke color", fa: "رنگ دورخط" },
  "set.dpi": { en: "Scan DPI", fa: "وضوح اسکن (DPI)" },
  "set.method": { en: "Method", fa: "روش" },
  "set.stampColor": { en: "Stamp color", fa: "رنگ مهر" },
  "set.stampSize": { en: "Stamp size", fa: "اندازه مهر" },
  "set.recScore": { en: "Min OCR confidence", fa: "کمینه اطمینان OCR" },
  "set.matchColor": { en: "Match original color", fa: "هم‌رنگ با متن اصلی" },
  "set.contrastMin": { en: "Min contrast ratio", fa: "کمینه نسبت کنتراست" },
  "set.inkDistance": {
    en: "Ink color distance threshold",
    fa: "آستانه فاصله رنگ جوهر",
  },
  "set.inkQuant": {
    en: "Ink color quantization step",
    fa: "گام کوانتیزه شدن رنگ جوهر",
  },
  "set.hintTemperature": {
    en: "Lower values translate more literally, higher ones more freely.",
    fa: "مقادیر کم ترجمه را تحت‌اللفظی‌تر و مقادیر بیشتر آزادتر می‌کنند.",
  },
  "set.hintChunk": {
    en: "Dialogue blocks sent to the model per request.",
    fa: "تعداد بلوک دیالوگ ارسالی به مدل در هر درخواست.",
  },
  "set.hintSystemPrompt": {
    en: "Sent to the model as the system instruction on every request.",
    fa: "به‌عنوان دستور سیستمی با هر درخواست برای مدل ارسال می‌شود.",
  },
  "set.hintUserPrompt": {
    en: "Use {dialogs} where the dialogue JSON is inserted.",
    fa: "از {dialogs} برای محل درج JSON دیالوگ‌ها استفاده کنید.",
  },

  /* Enum option labels */
  "set.optManga": { en: "Manga", fa: "مانگا" },
  "set.optManhwa": { en: "Manhwa (long strip)", fa: "مانهوا (نوار بلند)" },
  "set.optAutoInpaint": {
    en: "Auto — OpenCV + solid fill",
    fa: "خودکار — OpenCV + پرکننده تک‌رنگ",
  },
  "set.optSolid": { en: "Solid color fill", fa: "پرکردن تک‌رنگ" },

  "toast.loginFailed": { en: "Login failed", fa: "ورود ناموفق بود" },
  "toast.uploadFailed": { en: "Upload failed", fa: "آپلود ناموفق بود" },
  "toast.deleteFailed": { en: "Delete failed", fa: "حذف ناموفق بود" },
  "toast.actionFailed": { en: "Action failed", fa: "عملیات ناموفق بود" },
  "toast.saveFailed": { en: "Saving failed", fa: "ذخیره ناموفق بود" },
  "toast.saved": { en: "Settings saved", fa: "تنظیمات ذخیره شد" },
  "toast.jobDone": { en: "Job finished successfully", fa: "کار با موفقیت انجام شد" },
  "toast.jobFailed": { en: "Job failed", fa: "کار ناموفق بود" },
  "toast.chainDone": { en: "All steps completed", fa: "همه مراحل انجام شد" },
  "toast.loadFailed": { en: "Failed to load data", fa: "بارگذاری داده‌ها ناموفق بود" },

  "err.title": { en: "Something went wrong", fa: "مشکلی پیش آمد" },
  "err.desc": {
    en: "An unexpected error occurred. You can retry or head back to the studio.",
    fa: "خطای غیرمنتظره‌ای رخ داد. می‌توانید دوباره تلاش کنید یا به استودیو برگردید.",
  },
  "err.retry": { en: "Try again", fa: "تلاش دوباره" },
  "nf.title": { en: "Page not found", fa: "صفحه پیدا نشد" },
  "nf.desc": {
    en: "The page you're looking for doesn't exist or has moved.",
    fa: "صفحه‌ای که دنبالش هستید وجود ندارد یا جابه‌جا شده است.",
  },
  "nf.back": { en: "Back to home", fa: "بازگشت به خانه" },

  "common.loading": { en: "Loading…", fa: "در حال بارگذاری…" },
  "common.close": { en: "Close", fa: "بستن" },
} satisfies Record<string, Entry>;

export type DictKey = keyof typeof dict;

interface I18nCtx {
  locale: Locale;
  dir: "ltr" | "rtl";
  setLocale: (l: Locale) => void;
  t: (key: DictKey, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<I18nCtx>({
  locale: "en",
  dir: "ltr",
  setLocale: () => {},
  t: (k) => k,
});

export function LanguageProvider({
  children,
  initialLocale = "en",
}: {
  children: React.ReactNode;
  /** Server-read cookie value so the first paint already matches (no flash). */
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  // First visit (no saved choice): detect from the browser language. The
  // root layout's bootstrap script already set <html lang/dir> pre-paint;
  // this persists the choice as a cookie so future server renders match.
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem("mww.locale");
    } catch {
      /* private mode */
    }
    if (saved === "fa" || saved === "en") return;
    const detected: Locale = navigator.language
      ?.toLowerCase()
      .startsWith("fa")
      ? "fa"
      : "en";
    setLocaleState((prev) => (detected === prev ? prev : detected));
    if (detected !== initialLocale) {
      try {
        document.cookie = `mww.locale=${detected}; path=/; max-age=31536000; samesite=lax`;
      } catch {
        /* ignore */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const dir = locale === "fa" ? "rtl" : "ltr";
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem("mww.locale", l);
      document.cookie = `mww.locale=${l}; path=/; max-age=31536000; samesite=lax`;
    } catch {
      /* private mode */
    }
  }, []);

  const t = useCallback(
    (key: DictKey, vars?: Record<string, string | number>) => {
      let s = dict[key]?.[locale] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.split(`{${k}}`).join(String(v));
        }
      }
      return s;
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, dir: locale === "fa" ? ("rtl" as const) : ("ltr" as const), setLocale, t }),
    [locale, setLocale, t],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);

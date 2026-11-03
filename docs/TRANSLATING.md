# Translating Luma / 翻译指南

The source language is Simplified Chinese. English translations are in `locales/en.json`; keys remain stable Chinese source strings. Numbered placeholders such as `{0}` must match the source. Renderer code calls `tr` from `src/i18n.ts`; native menus use `electron/i18n.cjs`.

Run `node tools/check_i18n.cjs` and `npm run build` after editing. To add a language, register it in the language selector and locale resolver before adding its catalogue. Do not translate user-authored names, aliases, notes, collections, original post text or arbitrary upstream errors.

原文为简体中文，英文词条位于 `locales/en.json`。保留原文键名及 `{0}` 等占位符，界面和原生菜单分别通过 `src/i18n.ts` 与 `electron/i18n.cjs` 使用。新增语言需同时注册选择项与语言解析。不要翻译用户昵称、别名、备注、合集、原帖等数据。

# Ironclad Connector — идеальный первый запуск

Источник: `ONBOARDING_FIRST_LAUNCH_STANDARD.md`. Целевой пользователь: Legal Ops/
контракт-менеджер enterprise-компании на Ironclad CLM.

## 1. Credential type
OAuth client-credentials (Client ID + Client Secret).

## 2. Идеальный флоу
1. **Первое открытие** — `Empty` со ссылкой на создание OAuth Client в Ironclad admin +
   явный список нужных scopes.
2. **Форма** — client_id + client_secret с лейблами.
3. **После успеха** — `audit_contract_health`: активные контракты, приближающиеся сроки
   истечения — сразу, максимально actionable для Legal Ops.
4. **Expiring contracts emphasis** — контракты, истекающие в ближайшие 30/60/90 дней,
   должны визуально доминировать (это прямая финансовая/юридическая потеря при
   пропуске renewal window).
5. **Ошибка "insufficient workflow permissions"** — конкретное сообщение, если
   OAuth Client не имеет прав на конкретный тип workflow (Ironclad разделяет права по
   типам контрактов).

## 3. Разница с реализацией сейчас
См. `UI_COMPONENT_PLAN.md` §0.

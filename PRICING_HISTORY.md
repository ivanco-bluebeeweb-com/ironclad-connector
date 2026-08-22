# Pricing History — Ironclad Connector

Обязательный журнал: каждое выставление или изменение цен на функции этого
приложения фиксируется здесь — что изменилось, почему, и на основании
чего. Не переписывать прошлые записи — только дописывать новые сверху.

---

## 2026-08-22 — первичный прайсинг, до submit_for_review (по канону)

**Порядок соблюдён строго по `PRICING_POLICY.md` §1:** код готов → чистая
валидация (`imperal validate`: 0 errors) → `deploy_app` (20/21, warning
только про длину файлов — не блокер) → `update_pricing` → (этот шаг) →
`submit_for_review` следующим.

**Шкала — строго фиксированная (`PRICING_POLICY.md` §2): 0, 8, 16, 20, 40, 60.**

- `0` — `connect_ironclad`, `disconnect_ironclad`, `list_connections`
  (подключение/список подключений, без обращения к чужому Ironclad API).
- `8` — простые read-функции (list/get) по Workflows, Records, Entities,
  Obligations, Webhooks, Reports, включая `get_signature_status` и
  `get_records_schema`.
- `16` — write/mutating функции: launch/cancel/revert workflow, update
  attributes, attachments, comments, signature request, approvals,
  create/update/delete на Records/Entities/Obligations/Webhooks/Reports,
  apply_contract_action.
- `20` — `smart_import_record` (вызывает Ironclad-стороннее AI-извлечение
  атрибутов из документа — дороже обычного create по вычислительной
  стоимости на их стороне).
- `40` — Tier-3 агрегирующие отчёты: `audit_contract_health`,
  `find_expiring_contracts` (несколько внутренних вызовов на один ответ).
- `60` — bulk-операции: `bulk_launch_workflow`, `bulk_tag_records` (цикл
  из N вызовов за один вызов инструмента).

**Метод применения — `developer.update_pricing` с `pricing_config` как
НАСТОЯЩИМ вложенным JSON-объектом (не строкой) + `revenue_split_dev=95`
явным параметром, `pricing_model="per_action"` явным параметром —
подтверждённо рабочий метод (канонический `PRICING_POLICY.md` §3,
прецедент n8n Connector 2026-08-19, MuleSoft Connector 2026-08-20).**

Первый вызов в этой сессии ошибочно передал `pricing_config` как
JSON-**строку** (`"{\"tool_prices\": ...}"`) — платформа откатила это
явной ошибкой "did NOT save correctly: model stored as 'free'... was
not stored" для каждого поля. Это тот же класс платформенного/клиентского
несоответствия, что уже задокументирован в Imperal Cloud task #2230
(`gitlab-cicd-connector`) и task #2260 (`mirth-connect-connector`,
"object/array параметры доходят как строка"). Повторный вызов с
`pricing_config` как реальным Python dict/JSON-объектом прошёл без
ошибки. `imperal.json`'s локальное `pricing` поле дополнено вручную тем
же содержанием для консистентности зеркала манифеста.

Read-back подтверждения платформа не даёт (известное ограничение,
Imperal Cloud task #2113 — "нет инструмента прямой проверки применённого
прайсинга") — успех вызова без вернувшейся ошибки принят как
подтверждение по тому же прецеденту, что и для предыдущих коннекторов
в этом портфеле.

**Итоговый файл со значениями:** `tool-prices.json` в этой директории.

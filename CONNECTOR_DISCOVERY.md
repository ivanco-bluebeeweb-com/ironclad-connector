# Ironclad Connector — Connector Discovery

**Дата discovery:** 2026-08-22
**Статус:** Ярусы 1-3 пройдены (свежее чтение официальной документации
developer.ironcladapp.com, 2026-08-22). Задача #2269 явно заявляла
"максимальный функционал, полный максимум" — это ЯВНОЕ заранее заявленное
решение объёма ("максимум"), поэтому §7 (решение по объёму) не требует
повторного вопроса Владу — тот же прецедент, что GitLab CI/CD/MuleSoft/
Power Automate/UiPath/Blue Prism/Automation Anywhere/CircleCI/Cin7 Core/
ShipStation/PagerDuty/Mirth Connect коннекторы.

---

## 1. Целевой сервис и источники

Ironclad Public API (`/public/api/v1`) — REST/JSON, зрелая, полностью
документированная поверхность плюс отдельный SCIM API и MCP-прокси.
Прочитаны 2026-08-22:

- `developer.ironcladapp.com/llms.txt` — машиночитаемый индекс всех
  guide-страниц (использован для карты guides)
- `developer.ironcladapp.com/reference/getting-started-api` — Workflows
  vs Records концептуальное разделение, Unique IDs, Exports (gated)
- `developer.ironcladapp.com/reference/authenticate-a-request`,
  `.../client-credentials-grant`, `.../authorization-code-grant`,
  `.../legacy-access-token`, `.../guidance-for-oauth-migration`,
  `.../auth-design-considerations`, `.../oauth-20-faqs` — полная модель
  авторизации
- `apis.io/scopes/ironclad/ironclad-scopes/` — полный список 60 OAuth
  scopes, сгруппированных по доменам (entities/export/obligations/
  records/search/webhooks/workflows)
- `developer.ironcladapp.com/reference/clm-api-rate-limits` — полная
  таблица rate-limit buckets (Public API + SCIM + MCP)
- `developer.ironcladapp.com/docs/entities-integration-guide`,
  `.../entities-crud-api-guide`,
  `.../ironclad-repository-to-entities-migration-guide` — Entities API
  (counterparty CRM внутри Ironclad)
- `developer.ironcladapp.com/reference/create-a-webhook`,
  `.../list-all-workflows`, `.../create-a-new-workflow-async`,
  `.../list-all-records`, `.../retrieve-an-attachment-on-a-record`,
  `.../revert-to-review`, `.../send-signature-request` — конкретные
  endpoint-страницы
- `openapi.city/providers/ironclad` — независимый индекс (41+ endpoint)
  структурированного REST API, использован для перекрёстной проверки
  путей `/records`, `/workflows`, `/workflows/async`
- `support.ironcladapp.com/.../Ironclad-s-Public-API-Overview` —
  overview трёх API-областей (Workflow endpoints, Records endpoints,
  Webhooks)

## 2. КРИТИЧНО: несколько разных API-поверхностей — сознательный выбор

Ironclad — это НЕ один плоский API, а несколько логически разных
областей под одним базовым путём `/public/api/v1`, которые легко
перепутать:

1. **Workflows API** — активные, ЕЩЁ НЕ завершённые процессы
   согласования контракта (launch/list/get/cancel/pause/comments/
   approvals/documents/participants/signatures). Это "живой" процесс,
   у которого есть шаги (steps), назначенные пользователи (turn),
   вложения-черновики и т.д.
2. **Records API** — репозиторий уже ЗАВЕРШЁННЫХ (обычно подписанных)
   соглашений и их метаданных/вложений. Записи создаются автоматически
   по завершении workflow, но можно и создавать вручную напрямую через
   API (`POST /records`) — например, для миграции старых бумажных
   контрактов, минуя сам процесс согласования.
3. **Entities API** — отдельный "counterparty CRM" внутри Ironclad:
   создание/чтение/обновление контрагентов (юрлиц/физлиц), с которыми
   заключаются контракты, плюс Relationship Types между ними. НЕ то же
   самое, что Records/Workflows — это справочник контрагентов, который
   Records/Workflows затем ссылаются.
4. **Obligations API** — пост-подписные обязательства по контракту
   (то, что стороны должны сделать/выполнить после подписания — сроки,
   поставки, платежи). Отдельный домен от Records/Workflows.
5. **Exports API** — bulk-экспорт данных, ЗАБЛОКИРОВАН за отдельным
   платным add-on "Security & Data Pro" (`getting-started-api`,
   раздел "Purchase Required") — реализуем обёртки, но чётко
   документируем в handler docstring, что вызов вернёт ошибку доступа
   без этого add-on на стороне клиента.
6. **Webhooks API** — исходящие уведомления Ironclad → внешний URL по
   событиям workflow/record/entity/obligation изменений.
7. **SCIM API** (`/scim/v2`) — управление пользователями/группами
   компании через SCIM 2.0 стандарт — это IdP-provisioning слой
   (обычно настраивается через Okta/Azure AD, а не напрямую вручную).
   Технически в периметре Public API (общий rate-limit пул), но по
   назначению — HR/IT provisioning, не контрактный workflow. Решение
   ниже (§6).
8. **Ironclad Clickwrap** — ПОЛНОСТЬЮ ОТДЕЛЬНЫЙ продукт (click-to-accept
   для условий использования/политик), со своей ОТДЕЛЬНОЙ
   документацией на другом домене/разделе ("If you are looking for API
   documentation on Ironclad's Clickwrap product, please see the
   Clickwrap Developer Docs" — прямо на главной developer hub).
   **ВНЕ ОХВАТА этого коннектора** — та же ловушка, что Platform vs
   Embedded API у Tray.io (#2149). Clickwrap — другой продукт с другой
   моделью подписки/embedding, не CLM-контрактный workflow.
9. **Conversational Search** (`public.search.conversational`) — AI
   агент-поиск по контрактам, доступен ТОЛЬКО через Authorization Code
   grant (не Client Credentials) — узкая, AI-specific фича, для
   которой нет отдельного публичного REST-описания эндпоинта на момент
   discovery (только упоминание в scope-списке). Зафиксировано как
   Ярус 4 (см. §6) до появления более детальной документации endpoint.

**Решение:** строить коннектор на Workflows + Records + Entities +
Obligations + Webhooks + Exports как основные пять доменов Public API
(общий ROI для контрактной автоматизации), SCIM — отдельным
второстепенным модулем (Ярус 3, ограниченный), Clickwrap и
Conversational Search — сознательно вне охвата (Ярус 4, см. §6).

## 3. Авторизация — миграция Legacy → OAuth 2.0

Ironclad документирует явный, официально анонсированный переход:

- **Legacy Access Token** (deprecated, "will be disabled in the near
  future" — прямая цитата официальной страницы) — company-wide токен
  уровня полного admin-доступа, генерируется в Company Settings > API >
  Access Tokens, требует permission "API configuration" у создающего
  пользователя. Используется как простой `Authorization` header без
  дополнительных заголовков.
- **OAuth 2.0 Authorization Code grant** — user-scoped: токен привязан
  к согласившемуся пользователю, наследует ЕГО права видимости (не
  видит workflows, к которым у пользователя нет доступа). Требует
  интерактивный OAuth-редирект флоу с согласием пользователя.
- **OAuth 2.0 Client Credentials grant** — машинный токен (`POST
  https://ironcladapp.com/oauth/token`, `grant_type=client_credentials`,
  client_id/client_secret/scope), НЕ привязан к пользователю сам по
  себе, НО **каждый запрос обязан включать заголовок `x-as-user-id`
  ИЛИ `x-as-user-email`**, указывающий, от чьего имени действовать —
  ответ фильтруется по правам ЭТОГО пользователя (не company-wide
  admin, как Legacy Token).

**Решение (BYOK, как MuleSoft/Stripe/PagerDuty/CircleCI/GitLab CI/CD):**
основной механизм — **OAuth 2.0 Client Credentials grant**, это
официально рекомендованный Ironclad forward-путь (Legacy Token
"будет отключён"), не требует интерактивного пользовательского
редиректа (что плохо ложится в chat-first Imperal UX — Authorization
Code grant потребовал бы открытия браузера и обратного колбэка, чего
нет ни у одного текущего коннектора портфеля). Пользователь создаёт
OAuth Client Application в Ironclad Company Settings, вставляет
`client_id` + `client_secret` + рабочий email пользователя (для
`x-as-user-email`) + subdomain (na1/eu1/demo) в `connect_ironclad`;
коннектор сам обменивает их на bearer-токен через client_credentials
flow и кеширует токен до истечения. Явно НЕ поддерживаем Legacy Access
Token как основной путь (сам вендор отговаривает от него), но можно
зафиксировать заметку в docstring на случай, если у Влада или
пользователей уже есть старые токены — не Ярус 1.

**Три возможных региона данных** — не единый хост: `na1`, `eu1`, `demo`
(sandbox для разработки/тестирования), плюс упомянутый в OpenAPI YML
`preview`. Subdomain — обязательное пользовательское поле подключения
(как account_id у Cin7 Core, org/env у MuleSoft), не константа.

## 4. Модель ресурсов — три разных типа адресации ID

- **Workflow ID** — непрозрачный ID конкретного запущенного экземпляра
  workflow (получаем через List All Workflows или в URL при запуске
  вручную).
- **Template ID / Workflow Schema ID** — ID ДИЗАЙНА workflow (меняется
  при unpublish/republish!), нужен для запуска нового workflow через
  API и для получения списка полей формы запуска (`Retrieve a Workflow
  Schema`).
- **Record ID / Ironclad ID** — Record использует либо собственный
  `id`, либо `Ironclad ID` (человекочитаемый номер, показываемый в UI)
  — оба валидны как идентификатор в некоторых эндпоинтах, задокументи-
  ровано отдельно в getting-started ("Unique IDs (Records)" +
  "Ironclad ID").
- **Attribute ID** — ID конкретного поля формы workflow, получаемый
  через Retrieve a Workflow Schema (для полей, доступных на launch-
  форме) либо через Retrieve a Workflow на тестовом запуске (для
  формул/dropdown/системных полей, которые нельзя редактировать через
  API напрямую).

## 5. Rate limits (подтверждено 2026-08-22, `clm-api-rate-limits`)

Отдельные bucket-квоты per HTTP-метод и пути, RPM (requests per
minute), плюс общий company-wide кап **4,500 RPM** по ВСЕМ запросам
(включая SCIM):

| Bucket | RPM | Методы |
|---|---|---|
| workflows:read | 400 | GET/HEAD |
| workflows:write | 40 | POST/PUT/PATCH/DELETE |
| workflows:sign-status | 50 | POST/PATCH |
| workflows:signatures | 50 | POST/PATCH |
| records:read | 600 | GET/HEAD |
| records:write | 200 | POST/PUT/PATCH/DELETE |
| records:export | 10 | GET/HEAD |
| entities:read / write | 600 / 200 | |
| obligations:read / write | 600 / 200 | |
| exports:create | 20 | POST |
| exports:download | 20 | GET/HEAD |
| exports:status | 600 | GET/HEAD |
| webhooks | 600 | ANY |
| attribute-source:write | 40 | POST/PUT/PATCH/DELETE |
| signature-requests | 40 | ANY |
| other (Public API catch-all) | 800 | ANY |
| SCIM users read-write / write | 600 / 50 | |
| SCIM groups read / write | 200 / 50 | |

Отдаёт `X-RateLimit-Limit/Remaining/Reset` на каждом лимитированном
ответе, `Retry-After` на 429. Официально рекомендуемая стратегия:
pacing + exponential backoff + caching + webhooks вместо polling —
задокументировать это явно в `ironclad_client.py` docstring для
будущих правок (retry/backoff обязателен на 429, не молчаливый drop).

## 6. Осознанно вне охвата (Ярус 4 / не строим)

- **Ironclad Clickwrap** — отдельный продукт с отдельной документацией
  и моделью подписки (embed-виджеты click-to-accept для юридических
  условий использования), НЕ CLM-контрактный workflow. Прямо
  предупреждён вендором на главной странице developer hub как отдельная
  документация. Не строим без явного отдельного запроса.
- **Conversational Search** (`public.search.conversational`) — только
  Authorization Code grant (несовместим с выбранной моделью Client
  Credentials из §3), и нет отдельной публичной REST-документации
  конкретного endpoint на момент discovery (только заголовок scope) —
  недостаточно информации для реализации без риска написать код по
  догадке.
- **SCIM API** (`/scim/v2/users`, `/scim/v2/groups`) — HR/IT
  provisioning слой, обычно настраиваемый через внешний IdP (Okta/Azure
  AD SCIM connector), а не вручную через chat-интерфейс. Berkeley
  overlap с доменом, для которого у портфеля уже есть паттерн
  (`create_user`/`list_users` в WordPress Hub/UiPath/Ansible и т.д.), но
  здесь это провижининг live-компании через федеративный IdP-контракт —
  прямое ручное создание пользователей компании через API высокого
  риска (это НЕ "добавить участника в workflow", а "создать live
  сотрудника с доступом ко всей компании в Ironclad"). Решение:
  РЕАЛИЗУЕМ ТОЛЬКО READ-операции (list_scim_users, list_scim_groups,
  get_scim_user) для видимости состава компании — не пишем/не удаляем
  через SCIM (write-операции остаются вне охвата, слишком высокий
  security-риск для стороннего коннектора без явного запроса).
- **Policy/Compliance-level admin operations** (создание/удаление самих
  OAuth Client Applications, ротация client_secret через API, если
  такая существует) — это операции над самим механизмом авторизации,
  выполняются в Ironclad UI (Company Settings), не через сам API.

## 7. Ярусы для реализации ("максимум" по прямому запросу задачи #2269)

**Ярус 1 (ключевые функции CLM-цикла):**
connect_ironclad (client_id/client_secret/subdomain/as_user_email,
обмен на bearer через client_credentials, кеш токена),
disconnect_ironclad, list_connections; list_workflows, get_workflow,
launch_workflow (sync), launch_workflow_async, list_workflow_schemas,
get_workflow_schema; list_records, get_record, create_record,
update_record, delete_record; list_record_attachments,
get_record_attachment, add_record_attachment, delete_record_attachment.

**Ярус 2 (полнота CLM-домена):**
cancel_workflow, pause_workflow, resume_workflow, revert_workflow_to_review;
list_workflow_comments, add_workflow_comment;
list_workflow_approvals, update_workflow_approval (approve/reject);
list_workflow_participants, list_workflow_role_assignees,
update_workflow_role_assignment; list_workflow_documents,
add_workflow_document; send_signature_request, cancel_signature_request,
remind_signers, get_sign_status, create_signature_recipient_url,
create_embeddable_signer_url, schedule_signature_request,
update_scheduled_signature_request, delete_scheduled_signature_request,
upload_signed_document; list_workflow_turn_history;
list_entities, get_entity, create_entity, update_entity, delete_entity,
list_entity_relationship_types; list_obligations, get_obligation,
create_obligation, update_obligation, delete_obligation;
list_webhooks, create_webhook, update_webhook, delete_webhook.

**Ярус 3 (value-add + bulk + отчётность + read-only SCIM):**
bulk_launch_workflows (по образцу bulk-launch guide), bulk_cancel_workflows,
create_export, get_export_status, download_export (с явным
docstring-предупреждением про Security & Data Pro add-on gate);
audit_ironclad_estate (value-add: агрегирует активные workflows по
статусу/просрочке + недавние ошибки подписания в один отчёт, тот же
паттерн что audit_cloudhub_environment/audit_org/audit_project_ci);
get_stuck_workflows_report (value-add: workflows, зависшие на одном шаге
дольше N дней — типичная "где застряли контракты" боль юридических
команд); list_scim_users, get_scim_user, list_scim_groups (read-only).

Итого ожидаемое покрытие: ~55-65 chat-функций (Ярус 1: ~16, Ярус 2:
~30, Ярус 3: ~12) — сопоставимо по масштабу с MuleSoft/GitLab CI/CD/
CircleCI, с поправкой на широту CLM-домена (5 API-областей вместо
одной плоской модели ресурсов).

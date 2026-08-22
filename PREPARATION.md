# Ironclad Connector — Preparation

**Статус:** Фаза 1 (Discovery + архитектурные решения) завершена. Объём
релиза заявлен пользователем явно в исходном запросе — "разработай это
приложение в максимальной форме со всеми доступными функциями... для
повышения эффективности" — трактуется как "максимум" (Ярус 1+2+3), по
прецеденту GitLab CI/CD/CircleCI/MuleSoft/Power Automate/UiPath/Blue
Prism/Automation Anywhere/Cin7 Core/ShipStation/PagerDuty/Mirth Connect.

**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-22, v0.1
**Vikunja task:** #2269 (BBW Imperal Apps), [App Development].

**Почему сейчас:** Ironclad — Leader на рынке Contract Lifecycle
Management (CLM), >$200M ARR (2026), закрывает нишу юридической
автоматизации договоров, которой в портфеле Imperal сейчас нет.
Естественно дополняет Salesforce/HubSpot Connector (контрактные данные
из CRM → юридический workflow) и Slack/PagerDuty Connector (уведомления
о статусе контракта через вебхуки).

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «Ironclad»**. Внутренний
app_id/папка: `ironclad-connector`.

**Ironclad Connector** — коннектор к Ironclad Public API
(`/public/api/v1`), покрывающий весь CLM-домен: Workflows (запуск и
управление процессом согласования контракта — approvals, signatures,
comments, participants, documents), Records (репозиторий завершённых
подписанных соглашений и их вложений), Entities (справочник
контрагентов/counterparties), Obligations (пост-подписные обязательства),
Webhooks (событийные подписки), плюс read-only SCIM (просмотр
пользователей/групп организации Ironclad). BYOK: пользователь
подключает свой собственный OAuth 2.0 Client Credentials клиент к
своей собственной Ironclad-организации. Imperal ничего не хостит и не
проксирует помимо самого запроса.

**Сознательно вне охвата** (см. CONNECTOR_DISCOVERY.md §6):
Ironclad Clickwrap (отдельный продукт, отдельная документация —
click-to-accept для условий использования, не CLM-контракты);
Conversational Search (`public.search.conversational`, только
Authorization Code, не подходит для машинного BYOK-сценария);
SCIM write-операции (создание/удаление пользователей — риск случайного
нарушения identity-провижининга организации, административная зона вне
CLM-функционала); Reports/Exports создание сложных custom-репортов
(доступно, но Exports API целиком gated за отдельным Security & Data
Pro add-on — реализуем с явным предупреждением в docstring, не
скрываем, но не проектируем вокруг него Ярус 1).

## 2. Архитектурное решение: BYOK, OAuth 2.0 Client Credentials

**WHY BYOK**, та же логика, что MuleSoft/CircleCI/GitLab CI/CD/
PagerDuty Connector. Ironclad-организация живёт в аккаунте
ПОЛЬЗОВАТЕЛЯ — Imperal не может и не должен централизованно брокерить
доступ к чужим юридическим договорам.

**WHY OAUTH 2.0 CLIENT CREDENTIALS, НЕ LEGACY ACCESS TOKEN, НЕ
AUTHORIZATION CODE.**

Ironclad предлагает три модели авторизации одновременно
(CONNECTOR_DISCOVERY.md §3):
- **Legacy Access Token** — company-wide полный доступ уровня admin,
  официально помечен **deprecated**, будет отключён в обозримом
  будущем (developer.ironcladapp.com/reference/legacy-access-token,
  подтверждено 2026-08-22). Строить новый коннектор на устаревающем
  механизме — заведомо временное решение, отклонено.
- **OAuth 2.0 Authorization Code grant** — требует явного согласия
  КОНКРЕТНОГО пользователя через браузерный редирект (человек логинится
  в Ironclad и одобряет доступ). Токен наследует права именно этого
  человека. Хорошо подходит для интерактивных пользовательских сессий,
  но требует redirect_uri callback инфраструктуры и постоянного
  относительно короткоживущего access+refresh token цикла.
- **OAuth 2.0 Client Credentials grant** — машинный, server-to-server
  токен без браузерного шага, ближе всего по форме к уже реализованным
  MuleSoft (Anypoint Connected App) и Power Automate (Azure AD App
  Registration) коннекторам. Требует ОБЯЗАТЕЛЬНОГО заголовка
  `x-as-user-id` или `x-as-user-email` на каждый запрос — токен
  действует "от имени" явно указанного пользователя Ironclad, и ответы
  фильтруются по правам ИМЕННО этого пользователя, а не company-wide
  (developer.ironcladapp.com/reference/guidance-for-oauth-migration,
  подтверждено 2026-08-22).

**Решение:** Client Credentials grant как основной механизм — не
требует браузерного OAuth-редиректа (нет UI-инфраструктуры для callback
на нашей стороне, тот же паттерн, что MuleSoft/Power Automate), при
этом является актуальной, НЕ deprecated моделью. Форма подключения
запрашивает: `client_id`, `client_secret`, `subdomain` (na1/eu1/demo —
конкретная региональная инсталляция клиента, как `region` у некоторых
других коннекторов), `as_user_email` (обязательное поле — от чьего
имени действовать, как явно требует API), и опциональный `scope`
(список OAuth scopes, разделённых пробелом; по умолчанию — набор
scopes, соответствующий заявленному объёму Ярус 1+2+3 из
CONNECTOR_DISCOVERY.md §5, но пользователь может указать другой набор,
если его Client Application зарегистрирован с более узким scope).

**WHY `as_user_email` — ОБЯЗАТЕЛЬНОЕ ПОЛЕ ПОДКЛЮЧЕНИЯ, НЕ ПАРАМЕТР
КАЖДОГО ВЫЗОВА.**

В отличие от `project-slug` у CircleCI/GitLab (варьируется от вызова к
вызову), `x-as-user-id`/`x-as-user-email` определяет ПОСТОЯННУЮ
идентичность, от чьего имени действует всё подключение — переключать
её на лету означало бы менять эффективные права посреди сессии без
явного повторного подключения. Хранится как часть connection-объекта,
как `environment_id` у MuleSoft/Power Automate.

**WHY ОДИН СЕКРЕТ, ХРАНЯЩИЙ JSON-МАССИВ (multi-org support).**

Тот же структурный прецедент, что MuleSoft (`mulesoft_connections`) и
Power Automate (`connections`) — пользователь может подключить
несколько Ironclad-организаций (например, продакшн + demo-инсталляцию,
или несколько юрлиц). `ironclad_connections` хранит JSON-массив
`{id, label, subdomain, client_id, client_secret, as_user_email, scope,
access_token, token_expires_at}` — токен кешируется и обновляется
автоматически при истечении (Client Credentials не имеет refresh token,
но токен можно перезапросить тем же client_id/client_secret без участия
пользователя — `_ensure_token` helper в клиенте).

**WHY `write_mode="both"`**, та же логика, что все остальные BYOK-
коннекторы портфеля.

**WHY BASE URL ПАРАМЕТРИЗОВАН ЧЕРЕЗ `subdomain`, А НЕ ФИКСИРОВАН.**

В отличие от CircleCI (единственный SaaS-хост), Ironclad явно
multi-region: `na1.ironcladapp.com` (Production US), `eu1.ironcladapp.com`
(Production EU), `demo.ironcladapp.com` (Demo/Sandbox) — три реальных
хоста, подтверждённых в OpenAPI `servers` (CONNECTOR_DISCOVERY.md §1).
`subdomain` — обязательное поле формы подключения с явным списком
допустимых значений в docstring/схеме.

## 3. HTTP-клиент — общая механика

- Base URL: `https://{subdomain}.ironcladapp.com/public/api/v1` (OAuth
  token endpoint: `https://{subdomain}.ironcladapp.com/oauth/token` —
  ВАЖНО: без `/public/api/v1`, отдельный путь).
- Auth: `Authorization: Bearer <access_token>` на каждый запрос данных,
  плюс обязательный `x-as-user-email: <as_user_email>` header.
- Token lifecycle: `_ensure_token` helper запрашивает новый access
  token через client_credentials grant при отсутствии/истечении
  кешированного токена (expires_in из ответа минус 60-секундный буфер),
  сохраняет обратно в `ironclad_connections` через `ctx.secrets.set`.
- Пагинация: `pageNumber`/`pageSize` query params (подтверждено в
  Records API OpenAPI, CONNECTOR_DISCOVERY.md §1) — `_paginate` helper.
- Rate limit: bucketed per-resource per-method (CONNECTOR_DISCOVERY.md
  §1) плюс company-wide cap 4500 RPM. 429 ответы прокидываются как
  `ClientFail` с `Retry-After` значением, если присутствует в заголовке
  — тот же паттерн различения 401/403/404/429, что во всех остальных
  клиентах портфеля.
- Workflows vs Records — РАЗДЕЛЕНЫ на отдельные handler-модули
  (`handlers_workflows.py` / `handlers_records.py`), не смешиваются в
  одном файле, по прецеденту Mirth Connect
  (handlers_channels/handlers_messages) — концептуально разные объекты
  с разным жизненным циклом.

## 4. Ярусы функционала (полный список — см. CONNECTOR_DISCOVERY.md §7)

**Ярус 1 — ключевые функции CLM-цикла (~16):**
connect_ironclad, disconnect_ironclad, list_connections,
list_workflow_schemas, get_workflow_schema, list_workflows,
get_workflow, launch_workflow, launch_workflow_async, cancel_workflow;
list_records, get_record, create_record, update_record, delete_record;
list_record_attachments, get_record_attachment, add_record_attachment,
delete_record_attachment.

**Ярус 2 — полнота CLM-домена (~30):**
pause_workflow, resume_workflow, revert_workflow_to_review;
list_workflow_comments, add_workflow_comment; list_workflow_approvals,
update_workflow_approval; list_workflow_participants,
list_workflow_role_assignees, update_workflow_role_assignment;
list_workflow_documents, add_workflow_document; send_signature_request,
cancel_signature_request, remind_signers, get_sign_status,
create_signature_recipient_url, create_embeddable_signer_url,
schedule_signature_request, update_scheduled_signature_request,
delete_scheduled_signature_request, upload_signed_document;
list_workflow_turn_history; list_entities, get_entity, create_entity,
update_entity, delete_entity, list_entity_relationship_types;
list_obligations, get_obligation, create_obligation, update_obligation,
delete_obligation; list_webhooks, create_webhook, update_webhook,
delete_webhook.

**Ярус 3 — value-add + bulk + отчётность + read-only SCIM (~12):**
bulk_launch_workflows, bulk_cancel_workflows, create_export,
get_export_status, download_export (с явным docstring-предупреждением
про Security & Data Pro add-on gate); audit_ironclad_estate (value-add:
агрегирует активные workflows по статусу/просрочке + недавние ошибки
подписания в один отчёт, тот же паттерн что audit_cloudhub_environment/
audit_org/audit_project_ci/audit_iguana_instance); get_stuck_workflows_
report (value-add: workflows, зависшие на одном шаге дольше N дней);
list_scim_users, get_scim_user, list_scim_groups (read-only).

Итого ~58 chat-функций.

## 5. Деструктивные операции — требуют явного подтверждения

Per стандартной архитектуре портфеля (`action_type="destructive"`):
delete_record, delete_record_attachment, cancel_workflow,
cancel_signature_request, delete_entity, delete_obligation,
delete_webhook, delete_scheduled_signature_request,
bulk_cancel_workflows. `launch_workflow`/`launch_workflow_async` и
`create_record`/`create_entity`/`create_obligation` — обычный write
(создание нового объекта не разрушает существующее состояние).

## 6. UI (panels.py / panels_settings.py) — per UI_INTERFACE_STANDARD.md

Левый сайдбар: список подключений + форма подключения с явными
лейблами на каждом поле ("Client ID", "Client Secret", "Subdomain",
"Acting as (email)", "Scope (optional)") и контекстно-подходящими
плейсхолдерами (например `na1` для Subdomain, `legal-ops@yourcompany.com`
для Acting as). Форма растянута на всю ширину сайдбара, содержимое — на
всю ширину формы. Кнопка "?" рядом с формой открывает модалку с
инструкцией, где создать OAuth Client Application (Company Settings →
API → OAuth Clients) — сайдбар инструкций не дублирует. Единственная
secondary-кнопка "App settings" — последний элемент сайдбара, ведёт в
центр-слот с disconnect per-connection.

## 7. Решение по объёму — уже принято пользователем

Исходный запрос прямо содержит "максимальная форма, все доступные
функции с их стороны и все возможные функции с нашей стороны" —
трактуется как явное решение строить Ярус 1+2+3 без дополнительного
вопроса, по прецеденту GitLab CI/CD/CircleCI/MuleSoft/Power Automate/
UiPath/Blue Prism/Automation Anywhere/Cin7 Core/ShipStation/PagerDuty/
Mirth Connect.

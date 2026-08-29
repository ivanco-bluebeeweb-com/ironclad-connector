# Ironclad Connector — UI component plan

Источники: `Docs/session-notes/UI_COMPONENT_VOCABULARY.md`, `UI_INTERFACE_STANDARD.md`,
`concepts/panels.md`. Основано на функционале `ironclad-connector`.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Column`(align="start") + `ui.Text`(company) + `ui.Divider` + navigation `ui.ListItem`(Workflows/Records/Obligations) + `ui.Button`("App settings") | Без карточек по стандарту. |
| Workflow List (center, `center_overlay=True`) | `ui.Stats`(Active/Awaiting Approval/Completed) + `ui.DataTable`(title, current step, status Badge, created; sortable) | `DataTable` — стандартный способ отслеживать contract request'ы в процессе. |
| Workflow Detail | Back-button + `ui.KeyValue`(step/participants/attributes) + `ui.Timeline`(workflow steps: draft→review→approval→signature) + `ui.TextArea`(param_name="comment", placeholder="Комментарий к workflow...") + `ui.Row`(Button "Approve", "Reject", "Send to Signature") | `Timeline` — прямое отражение прохождения workflow по шагам. |
| Approval Dialog | `ui.Dialog`(title="Утвердить этап?", content=`ui.TextArea`(param_name="approval_note"), confirm_label="Утвердить") | Approval-решение — значимое действие, требует явного подтверждения. |
| Records List (signed agreements) | `ui.DataTable`(name, type, counterparty, expiration date; sortable) | Список уже подписанных контрактов — табличный поиск по датам истечения критичен. |
| Record Detail | `ui.KeyValue`(properties по схеме типа записи) + `ui.List`(attachments) + `ui.List`(linked obligations) | Записи Ironclad имеют динамическую схему свойств — KeyValue подходит для произвольного набора полей. |
| Obligations Tracker | `ui.DataTable`(obligation, due date, linked record, status Badge) | Отслеживание пост-подписных обязательств (renewal reminders, SLA). |
| Expiring Contracts Report | `ui.Stats`(Expiring in 30/60/90 days) + `ui.DataTable`(record, expiration date, days left) | Ценность коннектора — заранее видеть истекающие контракты, а не искать их вручную. |
| App Settings | `ui.Accordion`([Connections+Disconnect, Webhooks CRUD, Records Schema Viewer]) | Централизованные настройки по стандарту. |

## 2. User flow (валидно по panel lifecycle)

1. **SESSION INIT** → `__panel__ironclad_sidebar` рендерит company + разделы;
   `auto_action` открывает Expiring Contracts Report (наивысшая срочность для этого
   коннектора), если `not active_view`.
2. Expiring Contracts Report: клик на запись → `ui.Call("__panel__ironclad_center",
   record_id=...)` → Record Detail.
3. Раздел "Workflows" → Workflow List → клик на строку → Workflow Detail →
   Button "Approve" → Dialog с TextArea → `update_approval` →
   `refresh_panels=["ironclad_center"]`.
4. Раздел "Obligations" → Obligations Tracker → клик на обязательство → детальный
   просмотр (KeyValue) с линком на связанную Record.
5. "App settings" → отдельный center overlay с Accordion-секциями.

## 3. Конкретные экраны (screens)

### Screen: Expiring Contracts Report (`ironclad_center`, default)
- Stats row: Expiring in 30 / 60 / 90 days.
- DataTable: record, expiration date, days left — row-click → Record Detail.

### Screen: Workflow Detail (`ironclad_center` + `workflow_id`)
- Back-button "← К workflow".
- KeyValue: текущий шаг, участники, ключевые атрибуты.
- Timeline: draft→review→approval→signature.
- TextArea комментария + Row кнопок: Approve (Dialog), Reject (Dialog), Send to Signature.

### Screen: Record Detail (`ironclad_center` + `record_id`)
- Back-button "← К записям".
- KeyValue: свойства записи (динамическая схема по типу контракта).
- List: приложенные файлы.
- List: связанные обязательства (obligations).

### Screen: App settings (`ironclad_settings`)
- Accordion "Подключение": company, Disconnect (Dialog-подтверждение).
- Accordion "Webhooks": List + Button "Добавить".
- Accordion "Схема записей": Tree (типы записей → их свойства).

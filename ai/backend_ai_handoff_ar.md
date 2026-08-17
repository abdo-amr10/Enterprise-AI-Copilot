# تسليم AI Runtime إلى فريق Backend

تاريخ المراجعة: 17 أغسطس 2026

## القرار المختصر

نعم، فريق الـBackend يستطيع البدء الآن في تنفيذ الـpublic APIs وحفظ البيانات
والـRLS وتنفيذ SQL. الـAI Runtime أصبح يوفّر endpoints داخلية واضحة للـretrieve
والـText-to-SQL وعمليات Semantic Layer الحسابية.

لكن المشروع ليس تطبيق Backend مكتملًا بعد: لا توجد حتى الآن public controllers
أو database persistence أو JWT/RLS أو SQL execution أو history/audit داخل هذا
المستودع. هذه عناصر مطلوبة من فريق الـBackend وليست فجوة في AI pipeline.

## تشغيل AI Runtime

```powershell
cd D:\git\Enterprise-AI-Copilot\ai
python -m pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

فحص التشغيل:

```text
GET http://localhost:8000/health
=> { "status": "ok" }
```

بعد التشغيل، صفحة العقود التفاعلية: `http://localhost:8000/docs`.

يتطلب الـruntime تشغيل Ollama وتوافر النماذج المحددة في
`ai/src/infrastructure/llm/model_config.py`. كما يحتاج ملف الـSemantic Layer
المعتمد وملف schema في المسارات الموضحة لاحقًا.

## الـAI APIs المنفذة

| Endpoint | يستخدمه من؟ | الناتج | الحالة |
| --- | --- | --- | --- |
| `GET /health` | التشغيل/المراقبة | صحة الخدمة | جاهز |
| `POST /internal/semantic/retrieve` | Backend أو Copilot flow | tables وbusinessRules ذات الصلة | جاهز |
| `POST /internal/copilot/text-to-sql` | Backend Copilot controller | SQL آمن للقراءة فقط أو error code | جاهز |
| `POST /internal/semantic/generate-draft` | Semantic Layer controller | draft جديد غير محفوظ | جاهز |
| `POST /internal/semantic/validate` | Semantic Layer controller | draft بعد auto-fix + validation | جاهز |
| `POST /internal/semantic/review` | Semantic Layer controller | draft بعد approve/reject + review metadata | جاهز |

كل endpoints التي تبدأ بـ`/internal` ليست public API للـbrowser. يجب أن تكون على
شبكة خاصة أو محمية بـservice-to-service authentication عند النشر.

## شرح dependencies.py

الملف: `ai/src/api/dependencies.py` - **263 سطرًا**.

لا يستقبل HTTP requests مباشرة ولا يحتوي routes. دوره هو إنشاء الكائنات الحقيقية
مرة واحدة عند الحاجة وتمريرها إلى FastAPI باستخدام `Depends`.

| الأسطر | الدالة/الجزء | ماذا يفعل |
| --- | --- | --- |
| 1-98 | Imports | يستورد pipelines وservices وrepositories وOllama configs فقط. |
| 100-105 | Paths | يحدد approved layer في `ai/outputs/semantic_layer/approved_semantic_layer.json` وschema في `docs/database_metadata/schema.json`. |
| 107-128 | Settings + singletons | يحتفظ بالـembedding index، schema provider، self-correction، وSemantic pipelines داخل process واحد بدل بنائها في كل request. |
| 131-144 | `get_semantic_repository` | يربط approved layer بـEmbeddingService وLocalVectorStore. |
| 147-154 | `get_context_service` | يبني ContextRetrievalService المستخدم في retrieve وText-to-SQL. |
| 157-161 | `get_schema_provider` | يقرأ physical database schema للتحقق من SQL. |
| 164-193 | `get_self_correction_service` | syntax/schema/relationship validation ثم critic/correction بواسطة Ollama، بأقصى retries من الإعدادات. |
| 196-209 | `get_copilot_pipeline` | يربط retrieval + Qwen SQL generation + self-correction. |
| 212-213 | `get_semantic_retrieval_pipeline` | dependency للـretrieve endpoint. |
| 216-238 | `get_semantic_generation_pipeline` | يربط FullRebuild/Incremental builder والـmerge والـIDs. |
| 241-252 | `get_semantic_validation_pipeline` | يربط SemanticLayerValidator وAutoFixer، وبحد أقصى محاولتين للإصلاح. |
| 255-263 | `get_semantic_review_pipeline` | يربط HumanReviewManager لقرار approve/reject. |

ملاحظة مهمة: الـrepository والـvector index والـself-correction services cached، أما
`get_copilot_pipeline` و`get_semantic_retrieval_pipeline` ينشئان wrapper خفيفًا لكل
طلب مع إعادة استخدام الـservices الثقيلة cached.

## تسلسل Semantic Layer بين Backend وAI

```text
Browser/Admin
  -> Backend public API + JWT/RLS + database/files
  -> AI internal endpoint (compute فقط)
  -> Backend يحفظ revision/status/audit
  -> Browser/Admin
```

### 1. Upload

ينفذه الـBackend عبر public endpoint. يحفظ الملفات وينشئ `semanticLayerId` وfile IDs.
الـAI لا يخزن الملفات ولا ينشئ layer ID الخاص بالـupload.

### 2. Generate Draft

الـBackend يقرأ محتوى الملفات من التخزين ثم يستدعي:

`POST /internal/semantic/generate-draft`

الطلب يحتوي على:

- `semanticLayerId`
- `triggerType`: `FullRebuild` أو `Incremental`
- `sourceFileIds`: للمصدر والتتبع، و`schema` إجباري
- `resolvedSources`: المحتوى الفعلي المحمّل من التخزين
- Incremental فقط: `baseRevisionId` و`baseSemanticLayer` و`affectedObjects`

شكل `affectedObjects` ثابت وحصريًا:

```json
{ "section": "measures", "id": "obj-123" }
```

لا يوجد `name` أو `action` أو `objectId`. الـresponse الداخلي يعيد draft، وفي
Incremental يعيد `affectedObjects` أيضًا. لا يعيد `baseRevisionId` كحقل response.

الـBackend يحفظ draft ويُصدر للعميل public response مثل `DraftGenerated` مع
`semanticLayerId`, `revisionId`, `regeneratedObjectsCount`, `buildTimestamp`,
`lastRegenerationType`، و`affectedObjects` للـIncremental فقط.

### 3. Validate

الـBackend يرسل draft وschema إلى `/internal/semantic/validate`.
الـAI يعيد draft النهائي ونتيجة validation؛ الـdraft النهائي هو الذي يجب حفظه لأنه
قد يكون auto-fixer عدله. لا يُسمح بالـApprove إلا عند `validation.status = passed`.

### 4. Review

الـBackend يأخذ المستخدم من JWT، لا من قيمة مرسلة من الـbrowser، ثم يمرره كـ
`reviewerId` إلى `/internal/semantic/review` مع draft وvalidation وقرار `Approve`
أو `Reject`. القرار Reject يجب أن يحتوي comments؛ هذا مفروض في الـinternal route
أيضًا. يحفظ الـBackend draft وreview metadata ويحدث الحالة/الإصدار.

### 5. Submit / Status / Get Revision

هذه ليست AI compute APIs:

- `POST /api/v1/semantic-layer/{semanticLayerId}/revisions/{revisionId}/submit`
- `GET /api/v1/semantic-layer/{semanticLayerId}/revisions/{revisionId}`
- `GET /api/v1/semantic-layer/{semanticLayerId}/status`

هي مسؤولية الـBackend: load revision، حفظ التعديل القادم من واجهة Admin، إعادة
validation عند submit، ثم إرجاع status/revision من قاعدة البيانات.

## الـPublic APIs المطلوب من فريق Backend

| المجموعة | APIs المطلوبة | المالك |
| --- | --- | --- |
| Auth | login, register, JWT | Backend |
| Semantic sources | upload, get file | Backend |
| Semantic revisions | generate-draft public facade, get revision, review, submit, status | Backend + internal AI calls |
| Copilot | `POST /api/v1/copilot/ask` | Backend orchestrates AI + RLS + DB execution + report |
| Copilot history | list/get by queryId | Backend |
| Audit | audit log APIs | Backend |
| Response envelope/errors | HTTP status mapping, `errorCode`, correlation/query IDs | Backend |

### Copilot public flow

```text
POST /api/v1/copilot/ask
  -> Backend authenticates user and applies RLS context
  -> POST /internal/copilot/text-to-sql
  -> Backend validates authorization again and executes read-only SQL
  -> Backend formats report (SummaryCard/Table/Chart)
  -> Backend saves query history and audit event
  -> returns public response containing queryId, status, report
```

الـAI endpoint يعيد SQL فقط، وليس `report` أو query history. مثال report مثل
`textSummary`, `presentationType`, و`data` مسؤولية الـBackend بعد التنفيذ.

## أماكن الملفات المهمة

| الغرض | الملف |
| --- | --- |
| FastAPI app وتسجيل routers | `ai/main.py` |
| Dependency composition root | `ai/src/api/dependencies.py` |
| Semantic internal endpoints | `ai/src/api/routers/semantic_router.py` |
| Copilot internal endpoint | `ai/src/api/routers/copilot_router.py` |
| Semantic generate pipeline | `ai/src/application/pipelines/semantic_layer/semantic_layer_generation_pipeline.py` |
| Semantic validate pipeline | `ai/src/application/pipelines/semantic_layer/semantic_layer_validation_pipeline.py` |
| Semantic review pipeline | `ai/src/application/pipelines/semantic_layer/semantic_layer_review_pipeline.py` |
| Text-to-SQL runtime pipeline | `ai/src/application/pipelines/text_to_sql/copilot_runtime_pipeline.py` |
| Internal Semantic API request/response guide | `docs/ai_runtime_semantic_layer_api.md` |
| Public-contract mock/integration transcript | `ai/tests/integration/semantic_layer_test_scripts/` |
| Copilot contract transcript | `ai/tests/integration/copilot_test_scripts/` |
| Dependencies/package config | `ai/pyproject.toml` |

## الاختبارات الحالية

من داخل `ai`:

```powershell
python -m pytest tests/unit
python -m pytest tests/integration/backend/test_semantic_layer_backend_flow.py
python -m tests.integration.semantic_layer_test_scripts.run_integration_scenarios
python -m tests.integration.copilot_test_scripts.run_integration_scenarios
```

آخر تشغيل مكتمل للـunit suite: **53 passed**. الـSemantic mock integration يغطي
FullRebuild وIncremental وApprove وReject وSubmit. الـCopilot transcript يغطي
retrieve ثم Text-to-SQL ثم response public mock من الـBackend.

## ما يجب إنهاؤه قبل Production

هذه لا تمنع فريق Backend من البدء، لكنها تمنع اعتبار النظام production-ready:

1. حماية `/internal/*` بـmTLS أو service token، وعدم جعلها public من الإنترنت.
2. إضافة Pydantic request/response models بدل `dict` الخام في الـrouters، مع error
   envelope موحّد. حاليًا endpoints الجديدة تعيد 422 لعقود Semantic غير الصحيحة.
3. تنفيذ public API controllers + database tables + file/object storage.
4. تطبيق JWT، authorization، وRLS قبل تنفيذ أي SQL.
5. تنفيذ read-only SQL execution بوقت وحجم نتائج محدودين، ثم بناء report.
6. حفظ history وaudit log وcorrelation/query IDs.
7. إضافة HTTP integration tests حقيقية بين Backend وAI وتشغيلها في CI.
8. تهيئة shared deployment/configuration للـOllama، embedding model، approved layer،
   وvector index.

## تعريف الجاهزية

- **جاهز لبدء Backend development:** نعم.
- **عقود AI الداخلية موثقة:** نعم.
- **Semantic Layer compute pipeline:** نعم.
- **Text-to-SQL مع validation/correction:** نعم.
- **Public API + persistence + execution:** مطلوب من Backend.
- **Production deployment/security/E2E:** يحتاج البنود الثمانية أعلاه.

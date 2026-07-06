# Walli

**Walli** es la aplicación web interna de **laWALL** para automatizar la generación de borradores de respuesta a clientes a partir de los correos recibidos en los buzones de la empresa (Nominalia).

Walli **no envía correos automáticamente**. Su función es leer los correos entrantes, generar un borrador de respuesta con un LLM usando el contexto disponible (el propio correo, el historial del hilo y los documentos de conocimiento de la empresa) e intentar dejar ese borrador guardado en el buzón correspondiente para que una persona lo revise, edite y envíe.

## Índice

- [Objetivo](#objetivo)
- [Arquitectura](#arquitectura)
- [Servicios de Docker Compose](#servicios-de-docker-compose)
- [Configuración (.env)](#configuración-env)
- [Puesta en marcha](#puesta-en-marcha)
- [Migraciones de base de datos](#migraciones-de-base-de-datos)
- [Usuario inicial (seed)](#usuario-inicial-seed)
- [Acceso al frontend](#acceso-al-frontend)
- [Cómo funcionan los buzones](#cómo-funcionan-los-buzones)
- [Cómo funciona el worker](#cómo-funciona-el-worker)
- [Cómo funciona la generación de borradores](#cómo-funciona-la-generación-de-borradores)
- [Langfuse (trazabilidad de IA)](#langfuse-trazabilidad-de-ia)
- [Tests, lint y formato](#tests-lint-y-formato)
- [Limitaciones actuales](#limitaciones-actuales)
- [Roadmap](#roadmap)

## Objetivo

Dar al equipo de laWALL un panel donde puedan:

1. Iniciar sesión de forma segura.
2. Configurar uno o varios buzones de correo (Nominalia u otro IMAP).
3. Editar el prompt que usa el asistente para redactar respuestas.
4. Subir, listar y eliminar documentos de conocimiento de la empresa.
5. Ver el historial de correos procesados, sus borradores y cualquier error.

Y, en segundo plano, un worker que cada minuto:

1. Revisa los buzones activos.
2. Descarga los correos nuevos por IMAP.
3. Genera un borrador de respuesta con un LLM usando el prompt activo, los documentos de conocimiento y el historial del hilo.
4. Intenta guardar ese borrador en la carpeta de borradores del buzón.
5. Registra todo el proceso (éxito, error, reintentos) para que sea visible desde el frontend.

## Arquitectura

Arquitectura en capas, pensada para poder sustituir piezas (proveedor de IA, proveedor de email, almacenamiento de documentos) sin tocar el resto del sistema.

```
Frontend (React + TS)  ──HTTP──►  Backend API (FastAPI)
                                        │
                                        ├── repositories/  (acceso a datos, SQLAlchemy)
                                        ├── services/      (lógica de negocio)
                                        └── schemas/       (contratos Pydantic)
                                        │
                                   PostgreSQL

Worker (Celery) ──beat cada minuto──► poll_active_mailboxes
                                        │
                                        ├── MailboxService   (IMAP → EmailMessage/EmailThread)
                                        └── ProcessingService (LLM → Draft, intento de creación en buzón)
                                        │
                                   Redis (broker) + PostgreSQL
```

Piezas clave pensadas para evolucionar sin acoplarse a un proveedor concreto:

- **`LLMProvider` / `LLMService`** (`backend/app/services/llm_service.py`): interfaz abstracta sobre el proveedor de IA. Hoy hay una implementación de OpenAI (`OpenAILLMProvider`) y una implementación `MockLLMProvider` que se usa automáticamente si no hay `OPENAI_API_KEY` configurada, para poder desarrollar y probar sin credenciales reales. Cambiar de proveedor implica añadir una clase nueva y registrarla en `get_llm_provider()`.
- **`EmailProvider`** (`backend/app/services/email_provider_service.py`): interfaz abstracta sobre "leer correos y crear un borrador en un buzón". `ImapEmailProvider` es la implementación genérica por IMAP; `NominaliaEmailProvider` (`nominalia_email_provider.py`) es un subtipo reservado para particularidades de Nominalia si aparecen.
- **`KnowledgeContextService`** (`backend/app/services/knowledge_context_service.py`): construye el bloque de "contexto de empresa" para el prompt concatenando el texto extraído de los documentos activos, con un límite de caracteres configurable. Es el punto de extensión para añadir RAG (embeddings + búsqueda semántica) en el futuro sin cambiar quién lo consume (`ProcessingService`).
- **Langfuse** (`backend/app/services/langfuse_client.py`): integración opcional y aislada; si no está activada o no está bien configurada, el resto de la aplicación funciona exactamente igual.

## Servicios de Docker Compose

| Servicio    | Descripción                                                        |
| ----------- | ------------------------------------------------------------------- |
| `postgres`  | Base de datos PostgreSQL.                                            |
| `redis`     | Broker/backend de Celery.                                            |
| `backend`   | API FastAPI (`uvicorn`, con recarga en desarrollo).                   |
| `worker`    | Worker de Celery que procesa correos y genera borradores.             |
| `scheduler` | Celery Beat: dispara `poll_active_mailboxes` cada `MAIL_POLL_INTERVAL_SECONDS`. |
| `frontend`  | Aplicación React servida con el servidor de desarrollo de Vite.       |

## Configuración (.env)

Copia `.env.example` a `.env` en la raíz del repo y ajusta los valores:

```bash
cp .env.example .env
```

Variables importantes:

- `DATABASE_URL`, `REDIS_URL`: cadenas de conexión (los valores por defecto ya apuntan a los servicios de `docker-compose.yml`).
- `JWT_SECRET_KEY`: secreto para firmar los tokens de sesión. Genera uno aleatorio en producción.
- `ENCRYPTION_KEY`: clave usada para cifrar las contraseñas IMAP de los buzones antes de guardarlas en base de datos. **Es obligatoria** para poder crear buzones. Generar una con:

  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

- `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`: configuración del proveedor de IA. Si `OPENAI_API_KEY` está vacío, Walli usa un proveedor "mock" que genera un borrador de relleno, para poder desarrollar sin coste ni credenciales.
- `LANGFUSE_ENABLED` y variables `LANGFUSE_*`: ver [Langfuse](#langfuse-trazabilidad-de-ia).
- `MAIL_POLL_INTERVAL_SECONDS`, `MAX_EMAILS_PER_RUN`, `MAX_RETRY_ATTEMPTS`: comportamiento del worker.
- `DOCUMENTS_STORAGE_PATH`: carpeta donde se guardan los documentos subidos (dentro del contenedor del backend; persistida con el volumen `walli_documents`).
- `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_FULL_NAME`: usadas por el script de seed para crear el usuario administrador inicial.
- `VITE_API_BASE_URL`: URL del backend **tal como la ve el navegador** (no la red interna de Docker), p. ej. `http://localhost:8000/api`.

**Nunca subas `.env` al repositorio** (ya está en `.gitignore`). Las contraseñas de los buzones que se configuren desde el frontend se guardan cifradas en base de datos usando `ENCRYPTION_KEY`; nunca en texto plano.

## Puesta en marcha

Con Docker (recomendado):

```bash
cp .env.example .env
# edita .env: como mínimo, genera ENCRYPTION_KEY y JWT_SECRET_KEY
docker compose up --build
```

Esto levanta PostgreSQL, Redis, el backend, el worker, el scheduler y el frontend. La primera vez necesitas además ejecutar las migraciones y el seed (ver abajo).

Sin Docker, en local:

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload

# Worker (en otra terminal, con el venv activo)
celery -A app.workers.celery_app worker --loglevel=info

# Scheduler (en otra terminal)
celery -A app.workers.celery_app beat --loglevel=info

# Frontend (en otra terminal)
cd frontend
npm install
npm run dev
```

## Migraciones de base de datos

Las migraciones viven en `backend/app/db/migrations/` y se gestionan con Alembic.

```bash
# Dentro del contenedor/backend
alembic upgrade head              # aplicar migraciones
alembic revision --autogenerate -m "descripción"   # crear una nueva migración tras cambiar modelos
```

Con Docker Compose:

```bash
docker compose exec backend alembic upgrade head
```

## Usuario inicial (seed)

```bash
docker compose exec backend python -m scripts.seed
# o, para tener también datos de ejemplo en el historial:
docker compose exec backend python -m scripts.seed --with-demo-data
```

El script crea (de forma idempotente):

- El usuario administrador definido por `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`.
- El prompt base de la aplicación, marcado como prompt activo.
- (Opcional, con `--with-demo-data`) un buzón, un correo y un borrador de ejemplo para poder ver el historial sin esperar a que llegue correo real.

## Acceso al frontend

Con la configuración por defecto: [http://localhost:5173](http://localhost:5173).

Inicia sesión con el usuario creado por el seed (`INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`).

## Cómo funcionan los buzones

Desde **Buzones** puedes dar de alta un buzón indicando host/puerto IMAP, usuario, contraseña, si usa SSL y las carpetas de entrada y borradores. La contraseña se cifra antes de guardarse (`Mailbox.encrypted_imap_password`) y nunca se devuelve por la API. "Probar conexión" hace un login IMAP real para verificar las credenciales sin descargar correo.

Solo los buzones marcados como **activos** son revisados por el worker.

## Cómo funciona el worker

Cada `MAIL_POLL_INTERVAL_SECONDS` (60s por defecto), Celery Beat dispara la tarea `poll_active_mailboxes`, que:

1. Obtiene todos los buzones activos.
2. Para cada uno, se conecta por IMAP y descarga hasta `MAX_EMAILS_PER_RUN` correos nuevos (los que no tengan ya un UID o Message-ID registrado en base de datos — así se evita procesar el mismo correo dos veces).
3. Cada correo nuevo se guarda como `EmailMessage` (y se agrupa en un `EmailThread` si el hilo ya existe) y se encola como una tarea `process_email` independiente.

`process_email` (por correo):

1. Carga el prompt activo y los documentos activos.
2. Construye el contexto (documentos + historial del hilo).
3. Llama al LLM configurado.
4. Guarda el `Draft` generado y su traza (`LLMTrace`).
5. Intenta crear el borrador en el buzón (best-effort, ver limitaciones).
6. Registra cada paso en `ProcessingLog`, visible desde el detalle de procesamiento en el frontend.

Si algo falla, se reintenta hasta `MAX_RETRY_ATTEMPTS` veces (backoff exponencial en las llamadas IMAP/LLM/creación de borrador); superado ese límite, el correo se marca como `ignored` y no se vuelve a reprocesar automáticamente.

## Cómo funciona la generación de borradores

El prompt activo (editable desde **Prompts**) contiene tres marcadores que Walli sustituye antes de llamar al LLM:

- `{{company_documents_context}}` → texto de los documentos activos (ver `KnowledgeContextService`), truncado a `MAX_KNOWLEDGE_CONTEXT_CHARS`.
- `{{email_body}}` → cuerpo del correo recibido.
- `{{email_thread_context}}` → mensajes previos del mismo hilo, si los hay.

No hay RAG todavía: los documentos se concatenan tal cual (con límite de tamaño), no se buscan fragmentos relevantes. La arquitectura (`KnowledgeContextService`) está preparada para sustituir esa concatenación por una búsqueda semántica sin tocar el resto del pipeline.

## Langfuse (trazabilidad de IA)

Langfuse es completamente opcional. Con `LANGFUSE_ENABLED=false` (por defecto) la aplicación funciona igual y simplemente no se registran trazas externas.

Para activarlo:

1. Pon `LANGFUSE_ENABLED=true`.
2. Rellena `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` y `LANGFUSE_HOST`.
3. Cada llamada al LLM registrará en Langfuse el modelo, el prompt, tokens de entrada/salida, latencia y errores; el `trace_id` devuelto se guarda también en `LLMTrace.langfuse_trace_id`.

Si Langfuse no está bien configurado (activado pero sin claves, o el SDK falla), Walli lo registra en logs y continúa sin trazas — nunca bloquea la generación del borrador.

## Tests, lint y formato

```bash
cd backend
pip install -e ".[dev]"
pytest                 # tests unitarios de servicios críticos (auth, encriptación, prompts, procesamiento, etc.)
ruff check app scripts # lint + orden de imports
black app scripts      # formato
```

```bash
cd frontend
npm run typecheck
npm run build
npm run lint
```

## Limitaciones actuales

- **No se envían correos automáticamente.** Walli solo genera y (si el servidor lo permite) guarda borradores; el envío siempre lo hace una persona.
- **La creación de borradores por IMAP es best-effort.** Se implementa añadiendo (`APPEND`) el mensaje con el flag `\Draft` en la carpeta de borradores configurada, que es el mecanismo estándar más cercano a "crear un borrador" en IMAP. No se ha podido verificar el comportamiento exacto del servidor de Nominalia (algunos servidores IMAP aceptan el mensaje pero no lo muestran como borrador editable). Si falla, el borrador queda igualmente disponible y revisable desde el frontend (`draft_generated` sin `draft_created_in_mailbox`).
- **Sin RAG todavía.** El contexto de documentos se construye por concatenación simple con límite de caracteres, no por búsqueda semántica.
- **Sin envío de WhatsApp, formularios web ni CRM** (fase 3 del roadmap).
- **Un único rol de "empresa"**: no hay multiempresa ni roles avanzados todavía (solo `admin` / `agent`).

## Roadmap

### Fase 1 — MVP estable (esta versión)

- Aplicación web con login.
- Gestión de buzones, prompts y documentos.
- Historial de borradores y detalle de procesamiento.
- Worker programado cada minuto, lectura de correos por IMAP.
- Generación de borradores con LLM y creación en el buzón cuando el servidor lo permite.
- Logs estructurados, control de errores y reintentos.
- Langfuse opcional.

### Fase 2 — Mejora de conocimiento

- RAG: embeddings, base de datos vectorial, búsqueda semántica y ranking de fragmentos relevantes.
- Control avanzado de contexto (selección inteligente de qué incluir según el correo).

### Fase 3 — Canales adicionales

- WhatsApp Business, formularios web, integración con CRM y otras automatizaciones internas.

### Fase 4 — Producto más avanzado

- Multiempresa, roles avanzados, métricas de productividad.
- Revisión y aprobación de borradores desde el frontend.
- Envío controlado desde la propia aplicación.
- Analítica de costes de IA.

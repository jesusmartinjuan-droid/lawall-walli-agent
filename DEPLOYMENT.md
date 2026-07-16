# Despliegue en producción (VPS + auto-deploy desde `main`)

Guía paso a paso para poner Walli en un VPS con HTTPS gratuito y despliegue
automático en cada `push`/merge a `main`. Se hace **una vez**; a partir de
ahí, `.github/workflows/deploy.yml` se encarga de todo.

## Arquitectura

- `docker-compose.prod.yml` levanta: `postgres`, `redis`, `backend`, `worker`,
  `scheduler` y `frontend` (imagen basada en Caddy que sirve el frontend
  estático y hace de reverse proxy/TLS hacia `backend`).
- Las imágenes de `backend` y `frontend` se construyen en GitHub Actions y se
  publican en GitHub Container Registry (GHCR); el VPS solo hace `pull`.
- Backups: snapshots automáticos diarios del VPS (a nivel de proveedor).

## 1. Crear el VPS (Hetzner Cloud)

1. Crea una cuenta en [console.hetzner.cloud](https://console.hetzner.cloud).
2. Crea un proyecto y dentro un servidor:
   - Imagen: **Ubuntu 22.04**.
   - Tipo: **CX22** (2 vCPU / 4 GB RAM, ~€4.5/mes) — de sobra para este tráfico.
   - Ubicación: Falkenstein o Nuremberg (más cerca de España).
   - Añade tu **clave SSH pública** en el paso de creación (no uses contraseña).
3. Anota la **IP pública** del servidor. 
4. En la pestaña **Backups** del servidor, activa los **snapshots automáticos**
   (~+20% del coste del servidor). Es la protección ante pérdida total del VPS.
5. En la pestaña **Firewalls** (del proyecto o del propio servidor, según la
   consola), crea uno nuevo con reglas de entrada TCP `22`, `80` y `443`
   (deniega el resto por defecto) y asígnalo al servidor. Es una capa extra
   antes de que el tráfico llegue siquiera al sistema operativo — 1 minuto y
   gratis.
6. Activa **2FA** en tu cuenta de Hetzner (Account → Security). Es la cuenta
   que controla el servidor y sus snapshots; si te la roban, da igual lo
   demás.

## 2. Configurar el dominio (DuckDNS, gratis)

1. Entra en [duckdns.org](https://www.duckdns.org) y accede con tu cuenta de
   GitHub/Google.
2. Crea un subdominio, por ejemplo `walli` → te da `walli-lawall.duckdns.org`.
3. En el campo "IP", pon la IP pública del VPS del paso 1 y guarda.
   Como Hetzner asigna una IP fija al servidor, no hace falta ningún proceso
   que actualice la IP periódicamente (solo actualízala a mano si algún día
   cambias de servidor).

## 3. Preparar el servidor

Ejecuta el script de bootstrap ([infra/setup-server.sh](infra/setup-server.sh))
**una sola vez**, como `root`. Instala Docker, crea un usuario `deploy` sin
privilegios de root por SSH, activa el firewall del propio SO (`ufw`),
`fail2ban` (bloquea intentos de fuerza bruta) y actualizaciones de seguridad
automáticas, y deshabilita el login de `root` por SSH:

```bash
scp infra/setup-server.sh root@<IP-del-VPS>:/root/
ssh root@<IP-del-VPS> "bash /root/setup-server.sh"
```

Al terminar, **usa siempre `deploy` en vez de `root`** para conectarte:

```bash
ssh deploy@<IP-del-VPS>
```

Copia a `/opt/walli/docker-compose.prod.yml` el contenido del archivo del
mismo nombre en este repo:

```bash
scp docker-compose.prod.yml deploy@<IP-del-VPS>:/opt/walli/
```

Crea `/opt/walli/.env` con los valores reales de producción (parte de
`.env.example`, pero con secretos generados de verdad, nunca los de
desarrollo):

```bash
JWT_SECRET_KEY=<genera uno nuevo y aleatorio>
ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
POSTGRES_PASSWORD=<contraseña fuerte>
OPENAI_API_KEY=<tu clave real>
DOMAIN=walli-lawall.duckdns.org
CORS_ALLOWED_ORIGINS=https://walli-lawall.duckdns.org
DATABASE_URL=postgresql+psycopg://walli:<POSTGRES_PASSWORD>@postgres:5432/walli
# ...resto de variables de .env.example con sus valores de producción
```

Restringe los permisos del archivo, ya que contiene todos los secretos:

```bash
chmod 600 /opt/walli/.env
```

## 4. Configurar GitHub

En el repo (`Settings → Secrets and variables → Actions`):

**Secrets** (valores sensibles):
- `VPS_HOST`: IP pública del VPS.
- `VPS_USER`: `deploy` (el usuario creado por `infra/setup-server.sh` —
  **no** `root`, que ya tiene el login SSH deshabilitado).
- `VPS_SSH_KEY`: clave **privada** SSH que tenga acceso al servidor (par de la
  pública añadida en Hetzner). Genera un par dedicado solo para el CI si
  prefieres no reutilizar tu clave personal.

**Variables** (no sensibles):
- `VITE_API_BASE_URL`: `https://walli-lawall.duckdns.org/api` (se hornea en el build
  del frontend, no se lee en runtime).

No hace falta ningún secret para GHCR: el workflow usa el `GITHUB_TOKEN`
automático para publicar las imágenes. Tras el primer `push` a `main`, entra
en la pestaña **Packages** del repo/organización y marca `walli-backend` y
`walli-frontend` como **públicos** para que el VPS pueda hacer `pull` sin
autenticación.

Activa también **2FA en tu cuenta de GitHub**: quien tenga acceso a los
secrets del repo puede desplegar lo que quiera en el servidor a través de
este workflow, así que es tan crítica como la cuenta del VPS.

## 5. Primer despliegue manual

La primera vez, hazlo a mano desde el servidor para verificar que todo
arranca antes de depender del workflow:

```bash
cd /opt/walli
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed
```

## 6. Verificación

- Abre `https://walli-lawall.duckdns.org` en el navegador: debe cargar el frontend
  con candado TLS válido (Caddy lo obtiene solo de Let's Encrypt).
- Inicia sesión con el usuario creado por el seed
  (`INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`).

A partir de aquí, cada merge a `main` dispara `.github/workflows/deploy.yml`:
construye las imágenes, las publica en GHCR y redespliega solo en el VPS.

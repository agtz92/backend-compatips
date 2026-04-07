# CLAUDE.md - Backend Compatips

## Project Overview

Django 5.2 backend for **Compatips** (compatips.com), a product deals/offers aggregation platform. Exposes a GraphQL API (Strawberry) for a Next.js frontend and receives product data via webhooks. Deployed on Render with a PostgreSQL database.

## Tech Stack

- **Python 3.10** / **Django 5.2**
- **Strawberry GraphQL** (strawberry-graphql + strawberry-graphql-django) for the API layer
- **PostgreSQL** via `psycopg2-binary` + `dj-database-url`
- **gunicorn** as WSGI server (see `Procfile`)
- **django-cors-headers** for CORS
- **python-dotenv** for environment variables

## Project Structure

```
backend-compatips/
├── manage.py              # Django management entry point
├── Procfile               # Render deployment: `web: gunicorn backend.wsgi`
├── runtime.txt            # Python version (3.10.12)
├── requirements.txt       # pip dependencies
├── ads-analyst.html       # Standalone HTML tool served at /ads-analyst
├── backend/               # Django project settings
│   ├── settings.py        # Main config (DB, CORS, middleware, logging)
│   ├── urls.py            # URL routing
│   ├── wsgi.py
│   └── asgi.py
└── api/                   # Main Django app
    ├── models.py          # Post, ProductoOferta
    ├── types.py           # Strawberry GraphQL types (PostType, ProductoOfertaType)
    ├── schema.py          # GraphQL queries + mutations (strawberry.Schema)
    ├── views.py           # REST views: health check, webhook, ads-analyst proxy
    ├── webhooks.py        # Async Botize webhook notification (fire-and-forget)
    ├── admin.py           # Django admin registration
    └── migrations/        # Database migrations (0001–0005)
```

## Key URLs

| Path | Handler | Description |
|------|---------|-------------|
| `/` | `health_check` | Returns `{"status": "ok"}` |
| `/graphql/` | Strawberry GraphQLView | GraphQL endpoint (CSRF exempt) |
| `/webhook/` | `recibir_webhook` | POST — creates a ProductoOferta from JSON |
| `/admin/` | Django admin | Standard admin interface |
| `/ads-analyst` | `ads_analyst_html` | Serves ads-analyst.html |
| `/ads-analyst/api/chat` | `ads_analyst_chat` | Proxy to Anthropic API (auth required) |

## Data Models

### ProductoOferta (primary model)
- `titulo`, `precio_original`, `descuento`, `precio_oferta`, `url_imagen`, `link_referidos`, `fecha` (date), `categoria`
- Indexed on: `titulo`, `fecha`, `categoria`
- Dates use `DD-MM-YYYY` format in API input, stored as Python `date`

### Post (secondary/legacy)
- Simple `title`, `content`, `created_at`

## GraphQL Schema

**Queries:**
- `posts(limit, offset)` — paginated posts
- `productos(limit, offset)` — all products, ordered by date desc
- `productosFiltrados(categoria, search, ordenarPor, limit, offset)` — filtered products (last 2 weeks only)
- `productoPorId(id)` — single product lookup
- `categoriasUnicas` — cached (10 min) distinct category list

**Mutations:**
- `createPost(title, content)` — creates a Post
- `createProducto(...)` — creates a ProductoOferta, invalidates category cache, fires Botize webhook

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server
python manage.py runserver

# Run migrations
python manage.py migrate

# Create new migration after model changes
python manage.py makemigrations

# Production server (what Render uses)
gunicorn backend.wsgi
```

## Environment Variables

Required in `.env` (never commit):
- `DATABASE_URL` — PostgreSQL connection string
- `WEBHOOK_SECRET` — secret for webhook authentication
- `ANTHROPIC_API_KEY` — API key for ads-analyst chat proxy
- `APP_PASSWORD` — Bearer token for ads-analyst chat endpoint

## Conventions & Patterns

- **Language**: Model fields and API names use **Spanish** (titulo, precio_original, categoria, fecha, etc.). Code comments and logs mix Spanish and English.
- **GraphQL types**: Defined in `api/types.py` using `@strawberry_django.type(Model)` decorator pattern. Keep types in sync with models.
- **Webhook flow**: When a product is created (via GraphQL mutation or webhook endpoint), a Botize notification is sent asynchronously via a background thread (`webhooks.py`).
- **CORS**: Currently `CORS_ALLOW_ALL_ORIGINS = True`. CSRF trusted origins are explicitly listed.
- **Caching**: Django default cache used for `categorias_unicas` (10 min TTL). Cache is invalidated on product creation.
- **No tests**: The test file (`api/tests.py`) is empty. Be cautious with changes.
- **Date format**: Input dates arrive as `DD-MM-YYYY` strings, parsed via `datetime.strptime(fecha, "%d-%m-%Y")`.

## Deployment

- **Platform**: Render (backend-compatips.onrender.com)
- **Frontend**: Next.js on Vercel (frontend-compatips.vercel.app / www.compatips.com)
- **Process**: Push to main triggers deploy via Render
- **Python runtime**: 3.10.12 (pinned in `runtime.txt`)

## Common Pitfalls

- `CommonMiddleware` is listed twice in `MIDDLEWARE` — be aware if modifying middleware order.
- `DEBUG = False` even in development settings — set to `True` locally if needed.
- The `SECRET_KEY` in settings.py is the Django default insecure key; production should override via env var.
- `productosFiltrados` only returns products from the last 2 weeks by design.

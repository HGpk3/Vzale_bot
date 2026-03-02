import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import init_runtime_schema, purge_refresh_tokens
from app.routers import admin, auth, matches, teams, tournaments, users

app = FastAPI(title=settings.app_name, version='0.2.0')
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list if settings.app_env != 'dev' else ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def on_startup() -> None:
    if settings.database_url:
        init_runtime_schema()
        purge_refresh_tokens(retention_days=settings.refresh_token_retention_days)


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={'ok': False, 'error': {'detail': exc.detail}})


@app.exception_handler(Exception)
async def unhandled_exc_handler(_: Request, exc: Exception):
    logger.exception("Unhandled application error", exc_info=exc)
    detail = 'Internal server error'
    if settings.app_env == 'dev':
        detail = str(exc)
    return JSONResponse(status_code=500, content={'ok': False, 'error': {'detail': detail}})


@app.get('/health')
def health() -> dict:
    return {
        'ok': True,
        'data': {
            'status': 'ok',
            'env': settings.app_env,
            'postgres_enabled': bool(settings.database_url),
        },
    }


app.include_router(auth.router, prefix='/v1/auth', tags=['auth'])
app.include_router(users.router, prefix='/v1/me', tags=['me'])
app.include_router(tournaments.router, prefix='/v1/tournaments', tags=['tournaments'])
app.include_router(teams.router, prefix='/v1/teams', tags=['teams'])
app.include_router(matches.router, prefix='/v1/matches', tags=['matches'])
app.include_router(admin.router, prefix='/v1/admin', tags=['admin'])

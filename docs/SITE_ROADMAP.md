# Site Roadmap (Bot Parity + More)

## Goal
Build a web platform that fully covers bot functionality and extends it with admin-grade operations, analytics, and public tournament pages.

## Product Model
- Website: primary product (user + admin workflows)
- Bot: notifications and quick actions
- Shared Postgres: single source of truth

## Phase 0 (Done/Started)
- PostgreSQL schema and migration script prepared
- Canonical bot file selected
- Repo baseline cleanup started

## Phase 1 (Bot Parity MVP)
- Authentication and profile management
- Tournament listing and selection
- Team creation/join by invite code
- Team roster management (captain controls)
- Tournament info sections
- Match list, results, standings
- Suggestion/report submission

## Phase 2 (Admin Core)
- Admin tournament CRUD and statuses
- Team payment status management
- Match creation/edit/finish flows
- Poll creation, vote collection, result views
- Suggestion inbox with response workflow

## Phase 3 (Extended Capabilities)
- Live match panel with realtime updates
- Public tournament pages
- Achievement management UI (grant/revoke/backfill)
- Full statistics dashboards

## Phase 4 (Platform)
- RBAC (admin/captain/player/viewer)
- Audit logs
- Exports (CSV/XLSX)
- Observability and SLO dashboards

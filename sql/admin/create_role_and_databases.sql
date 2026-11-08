-- One-time admin setup for the ForgeLake source databases (design D7).
-- Run as the PostgreSQL superuser from Windows, in the repository directory:
--   psql -U postgres -h 127.0.0.1 -f sql/admin/create_role_and_databases.sql
-- \password prompts with hidden input and sends only a SCRAM hash, so the
-- plain-text password never appears in this file, the shell history or the server log.

\set ON_ERROR_STOP on

CREATE ROLE forgelake LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;

\echo
\echo 'Choose a password for the new role "forgelake" (input is hidden):'
\password forgelake

CREATE DATABASE forgelake_source      OWNER forgelake ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE forgelake_source_test OWNER forgelake ENCODING 'UTF8' TEMPLATE template0;

-- Only the owner (and superusers) may connect or create temp tables.
REVOKE CONNECT, TEMPORARY ON DATABASE forgelake_source      FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE forgelake_source_test FROM PUBLIC;

\echo
\du forgelake
\l forgelake_source*

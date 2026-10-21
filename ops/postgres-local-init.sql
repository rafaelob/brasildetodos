-- Local PostgreSQL stack only. Trust authentication is scoped to the internal
-- Compose network; never reuse this file for an internet-facing database.
CREATE ROLE bdt_app
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;

CREATE DATABASE bdt_app OWNER bdt_app;

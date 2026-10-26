-- Perfil somente leitura para a API. A senha NÃO fica neste arquivo: é definida fora do Git.
-- Rode como o dono do banco, depois do 001_esquema.sql. Pode ser repetido sem erro.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parfum_api') THEN
        CREATE ROLE parfum_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO parfum_api', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO parfum_api;
GRANT SELECT ON vendedores, clientes, produtos, fila_semanal, contexto_cliente, sugestoes_cliente, carga_log
    TO parfum_api;

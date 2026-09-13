-- Fecha o acesso direto às tabelas pela API REST do Supabase.
--
-- ============================ POR QUE ISTO EXISTE ============================
--
-- O Supabase publica automaticamente todo o schema `public` como uma API REST
-- (PostgREST) em https://<projeto>.supabase.co/rest/v1/. Quem chama essa API
-- com a anon key entra no banco como o papel `anon`.
--
-- A anon key é pública por design: ela está no bundle JavaScript que qualquer
-- visitante do site baixa. Isso é normal e não é o problema.
--
-- O problema é que as tabelas do Sentavos foram criadas pelo SQLModel
-- (`create_all`), conectado como dono do banco — e não pela interface do
-- Supabase. Tabela criada assim **não vem com RLS ligado**, e o Supabase tem um
-- GRANT padrão que dá acesso a `anon` e `authenticated` sobre o que aparece em
-- `public`. O resultado é que:
--
--     curl 'https://<projeto>.supabase.co/rest/v1/transactions?select=*' \
--          -H "apikey: <a anon key que está no seu bundle>"
--
-- devolveria seus lançamentos inteiros — sem passar pelo FastAPI, sem token do
-- Supabase, sem encostar na checagem de SENTAVOS_ALLOWED_USER_ID. Toda a auth
-- da API seria contornada por uma porta lateral que ninguém abriu de propósito.
--
-- ============================== POR QUE FUNCIONA =============================
--
-- Ligar RLS **sem criar nenhuma policy** significa "ninguém pode nada". Não
-- existe policy permissiva, então `anon` e `authenticated` não leem nem
-- escrevem nada por essa porta.
--
-- A API do Sentavos não é afetada: ela conecta como o papel dono da tabela, e
-- no Postgres o dono não é submetido a RLS (só seria com FORCE ROW LEVEL
-- SECURITY, que não é usado aqui justamente pra API continuar funcionando).
--
-- Ou seja: a única porta que continua aberta é o FastAPI, que já valida token e
-- confere o dono. É exatamente o desenho pretendido.
--
-- ================================ COMO RODAR ================================
--
-- Painel do Supabase > SQL Editor > cole este arquivo inteiro > Run.
-- É idempotente: rodar duas vezes não faz mal.

begin;

alter table public.transactions     enable row level security;
alter table public.categories       enable row level security;
alter table public.budgets          enable row level security;
alter table public.assets           enable row level security;
alter table public.asset_snapshots  enable row level security;

-- Cinto e suspensório. O RLS acima já basta, mas revogar o GRANT tira o acesso
-- uma camada antes: se um dia alguém criar uma policy permissiva "só pra
-- testar" e esquecer, isto ainda segura.
revoke all on public.transactions    from anon, authenticated;
revoke all on public.categories      from anon, authenticated;
revoke all on public.budgets         from anon, authenticated;
revoke all on public.assets          from anon, authenticated;
revoke all on public.asset_snapshots from anon, authenticated;

-- As sequences dos ids seguem o mesmo raciocínio.
revoke all on all sequences in schema public from anon, authenticated;

-- E o mais importante pro futuro: o GRANT padrão do Supabase é o que dá acesso
-- automático a tabela nova. Sem mexer nele, a próxima tabela que o create_all
-- criar nasceria exposta de novo — e este arquivo teria que ser lembrado na
-- hora certa, que é justamente quando não se lembra.
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

commit;

-- ============================ COMO CONFERIR DEPOIS ===========================
--
-- Esta consulta tem que listar as 5 tabelas com rowsecurity = true:
--
--   select tablename, rowsecurity
--     from pg_tables
--    where schemaname = 'public'
--    order by tablename;
--
-- E o curl lá de cima deve passar a responder 401/permission denied em vez de
-- devolver dado.

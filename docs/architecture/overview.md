# Arquitetura

O VagaNexo AI separa a interface, a API e a infraestrutura.

- `frontend/` é uma aplicação Next.js com App Router. Os módulos de tela ficam em `src/features/` e ainda não têm regras de negócio.
- `backend/` é uma API FastAPI. `app/main.py` sobe a aplicação e publica `GET /health`. O módulo `app/profile/` implementa o Profile Engine, com modelos SQLAlchemy, schemas Pydantic, serviços e rotas REST em `/api/v1/profiles`. Configuração, banco, modelos e o processo Celery já têm um ponto de entrada, sem fluxos de currículo, vaga ou candidatura.
- `infrastructure/compose.yaml` sobe PostgreSQL 17 com pgvector e Redis 7. Os dois serviços aceitam conexão apenas a partir de `127.0.0.1`.
- O volume Docker `vaganexo_postgres_data` guarda os dados do PostgreSQL fora do diretório do OneDrive.
- `storage/` reserva pastas para uploads, currículos, arquivos gerados e temporários. O conteúdo dessas pastas fica fora do Git.

A integração com modelos de linguagem fica reservada às variáveis `AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL` e `AI_API_KEY`. O SDK da OpenAI e o Sentence Transformers estão instalados para uso futuro. Nenhum modelo é baixado nesta etapa.

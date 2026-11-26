# Relatório técnico — VagaNexo Resume Importer v1.0

## Resumo

- **Objetivo**: implementar o módulo **Resume Importer v1.0** para importação, validação binária, deduplicação por SHA-256, armazenamento privado e extração/normalização de currículos em PDF e DOCX, além de corrigir definitivamente a infraestrutura de testes com Alembic no banco `vaganexo_test`.
- **Data e horário**: 26/11/2026, 16:53 −03:00.
- **Branch**: `feat/resume-import`.
- **Commit-base**: `f4d3fff` (`Merge pull request #1 from lucasn782/feat/profile-engine`, contendo `6584f0a`).

## Implementação

### Arquivos criados

- `backend/app/api/routes/resume_documents.py`
- `backend/app/models/resume_extraction.py`
- `backend/app/parsers/base.py`
- `backend/app/parsers/docx_parser.py`
- `backend/app/parsers/file_validator.py`
- `backend/app/parsers/pdf_parser.py`
- `backend/app/parsers/text_normalizer.py`
- `backend/app/resume_import/__init__.py`
- `backend/app/resume_import/exceptions.py`
- `backend/app/resume_import/hashing.py`
- `backend/app/resume_import/service.py`
- `backend/app/resume_import/storage.py`
- `backend/app/resume_import/validators.py`
- `backend/app/schemas/resume_import.py`
- `backend/alembic/versions/c8d9e0f1a2b3_add_resume_importer_tables.py`
- `backend/tests/unit/test_pdf_parser.py`
- `backend/tests/unit/test_docx_parser.py`
- `backend/tests/unit/test_file_validator.py`
- `backend/tests/unit/test_text_normalizer.py`
- `backend/tests/unit/test_resume_import_service.py`
- `backend/tests/unit/test_test_infrastructure.py`
- `backend/tests/integration/test_resume_import_api.py`
- `docs/architecture/RESUME_IMPORTER.md`
- `docs/development/RESUME_IMPORTER_REPORT.md`
- `storage/extracted/.gitkeep`

### Arquivos modificados

- `backend/app/main.py`: registro de `resume_documents.router` e handler de `ResumeImportError`.
- `backend/app/core/config.py`: variáveis `storage_root`, `resume_upload_dir`, `resume_extracted_dir`, `resume_temp_dir`, `max_resume_upload_bytes` (`10485760`) e limites de segurança de arquivos/texto.
- `backend/app/models/__init__.py`, `backend/app/models/enums.py`, `backend/app/models/resume_document.py`: novos estados `completed` e `completed_with_warnings` em `ParsingStatus`, campo `failure_reason` e relacionamento 1:1 com `ResumeExtraction`.
- `backend/app/schemas/__init__.py`, `backend/app/schemas/resume_document.py`: inclusão de `failure_reason` e reexports de `resume_import`.
- `backend/app/api/routes/profiles.py`: remoção das rotas antigas de `resume-documents` movidas para `resume_documents.py`.
- `backend/app/parsers/__init__.py`: registro do dicionário `PARSERS`.
- `backend/alembic/env.py`: suporte a conexão externa em `config.attributes["connection"]`.
- `backend/tests/conftest.py`: substituição de `drop_all`/`create_all` por `alembic.command.upgrade(..., "head")` e validação das tabelas antes do `TRUNCATE`.
- `.gitignore`: adição de `storage/extracted/*` preservando `.gitkeep`.
- `backend/.env.example`: documentação das variáveis de armazenamento e limite de upload.

### Bibliotecas utilizadas

- `pymupdf` (importação atual `import pymupdf`, sem uso de `fitz`)
- `python-docx`
- `zipfile` (stdlib, validação estrutural e proteção contra ZIP bombs)
- `hashlib` (stdlib, SHA-256 incremental)
- `FastAPI`, `SQLAlchemy 2`, `Alembic`, `Pydantic`, `Pytest`, `Ruff`, `Mypy`.

## Documentos

- **Formatos suportados**: `.pdf` e `.docx`.
- **Limites de tamanho**: `MAX_RESUME_UPLOAD_BYTES = 10485760` (10 MB) verificado durante o streaming em chunks de 1 MB.
- **Validação binária**: assinatura `%PDF-` + `pymupdf.open` (rejeita criptografados `needs_pass` e 0 páginas); assinatura ZIP + `[Content_Types].xml` + `word/document.xml` + limite de entradas e bytes descompactados + prevenção de path traversal em entradas ZIP.
- **Armazenamento**: privado em `storage/uploads/{profile_uuid}/{document_uuid}.{ext}` e espelho em `storage/extracted/{profile_uuid}/{document_uuid}.txt`, com gravação atômica (`os.replace`) e remoção de temporários em falhas.
- **Deduplicação**: SHA-256 por perfil com consulta prévia e constraint `uq_resume_documents_profile_sha256` (HTTP `409`).
- **Extração**: PDF página a página preservando `\f` e detectando PDFs digitalizados (`scanned_pdf_no_text`); DOCX preservando parágrafos, títulos, tabelas, cabeçalhos e rodapés; normalização preservando Unicode e acentos sem reescrita.

## Banco de dados

- **Migrações**: `bdd3fb3a0174` (Profile Engine) -> `c8d9e0f1a2b3` (`add_resume_importer_tables`, incremental).
- **Campos adicionados em `resume_documents`**: `failure_reason` (`VARCHAR(200)`) e ampliação de `parsing_status` para `VARCHAR(32)` com novos valores permitidos.
- **Nova tabela**: `resume_extractions` (`id`, `resume_document_id`, `extracted_text`, `page_count`, `word_count`, `character_count`, `parser_name`, `parser_version`, `warnings`, `extracted_storage_key`, `created_at`, `updated_at`).
- **Relacionamentos e Constraints**: 1:1 com `resume_documents` (`ON DELETE CASCADE`, `uq_resume_extractions_resume_document_id`), checks não negativos para contadores e índice `ix_resume_extractions_resume_document_id`.

## APIs

Prefixo: `/api/v1/profiles/{profile_id}/resume-documents`

- `POST /upload` → `201` (ou `404`, `409`, `413`, `422`, `500`)
- `GET /` → `200` (metadados sem `extracted_text`)
- `POST /` → `201` (registro de metadados preservado)
- `GET /{document_id}` → `200` (metadados + resumo da extração sem `extracted_text`)
- `GET /{document_id}/extraction` → `200` (texto extraído e estatísticas)
- `PATCH /{document_id}` → `200`
- `DELETE /{document_id}` → `204` (remove registros e arquivos físicos preservando proveniência com `ON DELETE SET NULL`)

## Testes

| Categoria | Resultado |
|---|---|
| PDF | APROVADO |
| DOCX | APROVADO |
| Validação | APROVADO |
| SHA-256 | APROVADO |
| Duplicidade | APROVADO |
| Armazenamento | APROVADO |
| Segurança | APROVADO |
| API | APROVADO |
| PostgreSQL | APROVADO |
| Alembic | APROVADO |
| Pytest | APROVADO |
| Ruff | APROVADO |
| Mypy | APROVADO |
| Frontend | APROVADO |

Detalhes das execuções:
- `uv run pytest -v --cov=app --cov-report=term-missing`: **90 passed** em duas execuções consecutivas (`4.41s` e `4.87s`), cobertura total de **92%** em `app`.
- `uv run ruff check .`: `All checks passed!`.
- `uv run ruff format --check .`: `78 files already formatted`.
- `uv run mypy app`: `Success: no issues found in 62 source files`.
- Teste ao vivo com `uvicorn app.main:app --host 127.0.0.1 --port 8000` contra `vaganexo_test`: `LIVE_API_OK` (`/health`, `/docs`, `/openapi.json`, upload PDF/DOCX, listagem, extração e exclusão).
- Frontend: `npm run lint`, `npx tsc --noEmit` e `npm run build` aprovados (código 0).

### Correção da infraestrutura de testes

- **Causa raiz**: `backend/tests/conftest.py` utilizava `Base.metadata.drop_all(engine)` e `Base.metadata.create_all(engine)` no fixture `test_engine`, removendo todas as tabelas gerenciadas pelos modelos SQLAlchemy ao final dos testes e mantendo apenas `alembic_version` com o marcador `bdd3fb3a0174`.
- **Problema provocado por `drop_all`/`create_all`**: o banco `vaganexo_test` ficou com a tabela `alembic_version` apontando para `bdd3fb3a0174`, porém sem nenhuma tabela de aplicação, impedindo migrações incrementais e ocultando divergências reais com o Alembic.
- **Alteração do `conftest.py`**: remoção completa de `Base.metadata.drop_all()` e `Base.metadata.create_all()`, substituição por `_run_test_migrations(engine)` executando `alembic.command.upgrade(config, "head")` via caminho resolvido por `Path(__file__).resolve()`, verificação prévia de existência das tabelas esperadas em `db_session` e encerramento apenas com `engine.dispose()`.
- **Alteração do `alembic/env.py`**: adição de `_run_migrations_with_connection()` e suporte à conexão externa via `config.attributes.get("connection")`, preservando `target_metadata`, `compare_type=True`, modo offline e o comportamento padrão com `engine_from_config()`.
- **Recuperação controlada do `vaganexo_test`**: após confirmar fisicamente que `vaganexo_test` continha exclusivamente `alembic_version` (`bdd3fb3a0174`) e nenhuma tabela de aplicação, a conexão Alembic foi direcionada temporariamente para `vaganexo_test`, executando `alembic stamp base` e `alembic upgrade head`.
- **Revisão Alembic final**: `c8d9e0f1a2b3 (head)` no banco `vaganexo_test`, com todas as 11 tabelas presentes (`alembic_version`, `candidate_profiles`, `certifications`, `educations`, `job_preferences`, `languages`, `projects`, `resume_documents`, `resume_extractions`, `skills`, `work_experiences`).
- **Testes de regressão**: `backend/tests/unit/test_test_infrastructure.py` valida a exigência do sufixo `_test`, aplicação das migrações Alembic até `head`, presença de todas as tabelas e preservação de `alembic_version` após `TRUNCATE` entre execuções consecutivas da suíte.
- **Confirmação de preservação do banco principal**: o banco `vaganexo` permaneceu intacto na revisão `bdd3fb3a0174` com suas 10 tabelas originais (`alembic_version` + 9 tabelas do Profile Engine), sem execução de `upgrade`, `downgrade`, `stamp` ou limpeza.

## Problemas

- **Docker Desktop parado inicialmente**: impediu a execução inicial contra o PostgreSQL até que o daemon fosse iniciado pelo usuário. Resolvido após a inicialização do Docker Desktop, com todos os testes de banco, Alembic e Uvicorn executados com sucesso.
- **Tipagem do `pymupdf.Document` no Mypy**: `for page in document` falhou no `mypy`; substituído por `document.load_page(index)` com `range(document.page_count)`.
- **Inconsistência `drop_all`/`create_all` no `vaganexo_test`**: corrigida definitivamente com Alembic em `conftest.py` e `alembic/env.py`.

## Conclusão

O **Resume Importer v1.0** e a **correção da infraestrutura de testes com Alembic** foram **concluídos** com sucesso na branch `feat/resume-import`, atendendo a todos os critérios funcionais, de segurança, migração e qualidade.

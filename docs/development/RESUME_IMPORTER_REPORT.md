# Relatório técnico — VagaNexo Resume Importer v1.0

## Resumo

- **Objetivo**: implementar o módulo **Resume Importer v1.0** para importação, validação binária, deduplicação por SHA-256, armazenamento privado e extração/normalização de currículos em PDF e DOCX, além de corrigir definitivamente a infraestrutura de testes com Alembic no banco `vaganexo_test`.
- **Data e horário**: 26/11/2026, 23:04 −03:00.
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
- `uv run pytest -v --cov=app --cov-report=term-missing`: **103 passed** (`7.40s`), cobertura total de **89%** em `app`, sem avisos de depreciação do Alembic após `path_separator = os` em `backend/alembic.ini`.
- `uv run ruff check .`: `All checks passed!`.
- `uv run ruff format --check .`: `79 files already formatted`.
- `uv run mypy app`: `Success: no issues found in 62 source files`.
- Teste de downgrade e re-upgrade Alembic (`backend/tests/integration/test_migration_downgrade.py` em banco descartável `vaganexo_migration_test`): **APROVADO**.
- Testes de integração entre perfis (`test_resume_import_api.py`): **APROVADO**.
- Testes de segurança do armazenamento (`test_resume_import_service.py`): **APROVADO** (incluindo symlinks, symlinks quebrados, junctions NTFS reais via `mklink /J` nos 3 diretórios principais, raiz e subdiretórios de perfil, e ausência de arquivos órfãos).
- Teste ao vivo com `uvicorn app.main:app --host 127.0.0.1 --port 8019` contra `vaganexo_test`: **LIVE_API_HARDENING_OK** (upload PDF/DOCX, deduplicação `409`, listagem, detalhes, extração, isolamento `404`, proteção contra exclusão cruzada via registro manual e exclusão legítima `204`).
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

## Endurecimento de segurança e integridade (Revisão PR #2)

### 1. Problemas identificados e causa raiz

1. **Exclusão cruzada via registro manual de metadados**: `POST /api/v1/profiles/{profile_id}/resume-documents` aceita `storage_key` fornecido pelo cliente. `ResumeImportService.delete_document()` repassava `document.storage_key` e `extraction.extracted_storage_key` diretamente para `ResumeStorage.delete_key()`, sem verificar se pertenciam ao par `(profile_id, document_id)` e ao tipo do documento.
2. **Proteção contra symlinks e caminhos manipulados em `ResumeStorage`**: `resolve()` chamava `.resolve()` antes de verificar links simbólicos intermediários, permitindo que um symlink interno apontasse para outro arquivo dentro do próprio diretório de armazenamento; além disso, faltava rejeição explícita de separadores Windows (`\`), letras de unidade (`:`), bytes nulos e componentes vazios (`//`).
3. **Falha no `downgrade()` da migração `c8d9e0f1a2b3`**: `downgrade()` recriava a constraint legada `parsing_status IN ('pending', 'processing', 'parsed', 'failed')` e reduzia a coluna para `VARCHAR(16)` sem converter antes os estados `completed` e `completed_with_warnings`.
4. **Ausência de autenticação e autorização multiusuário**: os módulos Profile Engine e Resume Importer ainda não possuem camada de identidade/autenticação.

### 2. Alterações realizadas e arquivos modificados

- `backend/app/resume_import/storage.py`:
  - Adicionadas regras canônicas `canonical_upload_key()`, `canonical_extracted_key()`, `owned_upload_key()` e `owned_extracted_key()` (comparação com `hmac.compare_digest`).
  - `resolve()`, `relative_key()`, `delete_key()` e `_ensure_within()` agora validam estritamente caminhos relativos POSIX (`_validate_relative_key`), rejeitam separadores `\`, `:`, bytes nulos e segmentos vazios/`.`/`..`, proíbem exclusão de diretórios ou fora de `uploads/` e `extracted/`, e percorrem cada componente verificando `is_symlink()` (`_assert_no_symlinks`) antes de qualquer operação física.
- `backend/app/resume_import/service.py`:
  - `delete_document()` agora só remove arquivos físicos cujo `storage_key` e `extracted_storage_key` correspondam exatamente aos caminhos canônicos gerados pelos UUIDs confiáveis do servidor (`uploads/{profile_id}/{document_id}.{pdf|docx}` e `extracted/{profile_id}/{document_id}.txt`).
  - Registros manuais com chaves não canônicas continuam sendo removidos do PostgreSQL quando válidos, mas não disparam exclusão física e registram aviso em log sem expor caminhos absolutos.
- `backend/app/profile/validators.py`:
  - `validate_storage_key()` endurecido contra separadores Windows, bytes nulos, letras de unidade, barras finais/duplicadas e segmentos `.`/`..`.
- `backend/alembic/versions/c8d9e0f1a2b3_add_resume_importer_tables.py`:
  - `downgrade()` ajustado para: (1) remover a constraint atual de `parsing_status`, (2) converter `completed` e `completed_with_warnings` para `parsed` (conversão intencional com perda de granularidade preservando os registros), (3) recriar a constraint legada, (4) reduzir a coluna para `VARCHAR(16)`, e (5) remover `ix_resume_extractions_resume_document_id`, `resume_extractions` (**com perda esperada dos dados de extração durante a reversão**) e `failure_reason`.
- `backend/alembic.ini`: adicionado `path_separator = os` na seção `[alembic]`, eliminando os 5 avisos de depreciação do Alembic.
- `backend/tests/unit/test_resume_import_service.py`: adicionados testes de travessia de caminho, separadores Windows, proteção contra symlinks (com fallback determinístico quando o SO restringe criação de symlinks), exclusão cruzada (upload e extração), compatibilidade de registros manuais e exclusão legítima.
- `backend/tests/integration/test_resume_import_api.py`: adicionado teste de integração rejeitando travessia no cadastro manual (`422`) e comprovando preservação dos arquivos do perfil B após exclusão de registro manual no perfil A.
- `backend/tests/integration/test_migration_downgrade.py`: teste isolado em banco descartável `vaganexo_migration_test` validando `upgrade head`, inserção de todos os 6 estados, `downgrade` para `bdd3fb3a0174` (conversão de `completed` e `completed_with_warnings` para `parsed`, preservação dos demais registros e perda esperada de `resume_extractions`) e re-`upgrade` até `head`.
- `docs/architecture/PROFILE_ENGINE.md` e `docs/architecture/RESUME_IMPORTER.md`: adicionada a seção **Segurança, autenticação e limites de implantação**.

## Hardening final dos diretórios principais de armazenamento

1. **Problema identificado**: `ResumeStorage.ensure_ready()` executava `directory.mkdir(parents=True, exist_ok=True)` sem verificar se a raiz ou os diretórios principais (`uploads/`, `extracted/`, `temporary/`) já existiam como symlink, junction do Windows ou reparse point. Além disso, `ResumeStorage.__init__()` executava `.resolve()` prematuramente sobre a raiz configurada.
2. **Causa raiz**: resolução simbólica antes da inspeção de componentes e confiança implícita em `mkdir(exist_ok=True)` como validação estrutural.
3. **Alterações realizadas**:
   - Criação de `_is_link_or_reparse_point()` combinando `Path.is_symlink()`, `Path.is_junction()` (Python 3.12+/Windows) e `os.lstat()` (`stat.S_ISLNK` + `FILE_ATTRIBUTE_REPARSE_POINT`).
   - `ResumeStorage.__init__()` passa a preservar o caminho léxico (`os.path.abspath`) e rejeitar raiz que seja symlink, reparse point ou arquivo comum, sem restringir diretórios pais legítimos do sistema operacional.
   - `ensure_ready()` valida a raiz e os três diretórios principais (`uploads/`, `extracted/`, `temporary/`) antes e depois da criação.
   - `stage()`, `commit()` e `write_extracted_text()` validam o diretório de origem temporária, os subdiretórios de perfil (`uploads/{profile_id}`, `extracted/{profile_id}`) e o caminho-alvo antes de qualquer escrita ou `os.replace()`, impedindo sobrescrita de arquivos existentes e derivando `storage_key` dos UUIDs confiáveis antes da movimentação atômica.
   - Em sistemas POSIX, `_open_pinned_dir()` utiliza `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` e `os.open`/`os.replace` com `dir_fd`.
4. **Arquivos modificados**: `backend/app/resume_import/storage.py`, `backend/tests/unit/test_resume_import_service.py`, `docs/architecture/RESUME_IMPORTER.md`, `docs/development/RESUME_IMPORTER_REPORT.md`.
5. **Testes criados**: suíte parametrizada cobrindo `uploads/`, `extracted/` e `temporary/` como symlinks, symlinks quebrados e junctions NTFS reais (`mklink /J`), raiz e subdiretórios de perfil manipulados, arquivos comuns ocupando diretórios e verificação de ausência de arquivos órfãos.
6. **Resultados reais**: **103 passed** (`89%` de cobertura), `ruff check`, `ruff format --check` (`79 files`), `mypy` (`62 files`), `LIVE_API_HARDENING_OK` e frontend (`lint`, `tsc`, `build`) aprovados.
7. **Comportamento em Windows**: junctions reais via `mklink /J` e reparse points foram detectados e rejeitados via `Path.is_junction()` e `FILE_ATTRIBUTE_REPARSE_POINT`; quando o SO restringe `os.symlink` sem privilégio, os testes executam fallback determinístico documentado.
8. **Comportamento em Linux**: protegido adicionalmente por descritores fixados (`O_DIRECTORY | O_NOFOLLOW` e `dir_fd` em `os.open`/`os.replace`).
9. **Limitações conhecidas (TOCTOU)**: no Windows, como `os.open` e `os.replace` não suportam `dir_fd`, permanece uma janela residual mínima entre a verificação prévia de reparse point e a chamada física ao sistema operacional. Em Linux, o uso de `dir_fd` com `O_DIRECTORY | O_NOFOLLOW` fecha a janela de troca de diretório.

## Segurança, autenticação e limites de implantação

- **Ausência de autenticação e autorização multiusuário**: o Profile Engine e o Resume Importer ainda não implementam autenticação nem controle de acesso por usuário. Conhecer o UUID de um perfil permite acessar e operar suas rotas.
- **Endpoints com dados pessoais**: rotas sob `/api/v1/profiles` e `/api/v1/profiles/{profile_id}/resume-documents` (incluindo `GET /{document_id}/extraction`, que retorna o texto integral do currículo) manipulam dados pessoais sensíveis.
- **Exposição proibida e bloqueio de produção**: os endpoints de perfil e currículo **não devem ser expostos diretamente à internet**, e a implantação pública ou SaaS está **bloqueada** até a implementação formal de identidade, autenticação e autorização baseada em propriedade.
- **Armazenamento privado vs. controle de acesso**: manter os arquivos fora de `frontend/` e sem rota estática pública impede acesso direto por URL de arquivo, mas não substitui autenticação na API.
- **Próximos passos**: implementar autenticação/autorização multiusuário antes de qualquer exposição pública, além dos módulos futuros (OCR, AI Profile Analyzer e CV Engine).

## Conclusão

O **Resume Importer v1.0**, a **correção da infraestrutura de testes com Alembic** e as **correções de segurança e reversão de migração da revisão do PR #2** foram **concluídos** na branch `feat/resume-import`. O sistema permanece bloqueado para implantação pública até a implementação de autenticação e autorização multiusuário.

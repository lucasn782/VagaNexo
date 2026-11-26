# VagaNexo Resume Importer v1.0

## 1. Arquitetura

O **Resume Importer** é a camada de entrada documental do VagaNexo AI. Ele recebe arquivos PDF e DOCX, valida sua estrutura binária, calcula o hash SHA-256 para deduplicação por perfil, persiste os arquivos em armazenamento privado fora do frontend e extrai o texto normalizado para uso futuro pelo AI Profile Analyzer.

Nenhum texto extraído é convertido automaticamente em experiências, competências ou formações nesta etapa.

```text
backend/app/
├── api/routes/resume_documents.py  Rotas REST sob /api/v1/profiles/{profile_id}/resume-documents
├── core/config.py                  STORAGE_ROOT, diretórios privados e MAX_RESUME_UPLOAD_BYTES
├── models/
│   ├── enums.py                    ParsingStatus (pending, processing, parsed, completed, completed_with_warnings, failed)
│   ├── resume_document.py          Metadados do arquivo e failure_reason
│   └── resume_extraction.py        Entidade 1:1 com o texto extraído e estatísticas
├── parsers/
│   ├── base.py                     Contrato ResumeParser, ParsedDocument e ResumeFileKind
│   ├── file_validator.py           Validação binária de PDF e DOCX (incluindo proteção contra ZIP bombs)
│   ├── pdf_parser.py               Extração por página com PyMuPDF (import pymupdf)
│   ├── docx_parser.py              Extração de parágrafos, títulos, tabelas, cabeçalhos e rodapés
│   └── text_normalizer.py          Normalização de quebras, espaços e caracteres de controle
├── resume_import/
│   ├── exceptions.py               Exceções de domínio traduzidas para HTTP
│   ├── hashing.py                  Acumulador incremental SHA-256
│   ├── storage.py                  Armazenamento privado com gravação atômica e prevenção de path traversal
│   ├── validators.py               Sanitização do nome original do arquivo
│   └── service.py                  Orquestração transacional entre banco e storage
└── schemas/resume_import.py        Contratos Pydantic de upload, detalhe e extração
```

## 2. Fluxo de upload

1. Verifica se `CandidateProfile` existe (`404` se inexistente).
2. Sanitiza o nome original do arquivo removendo diretórios e caracteres não imprimíveis.
3. Faz streaming do upload para `storage/temporary/{uuid}.part`, calculando SHA-256 e aplicando `MAX_RESUME_UPLOAD_BYTES` durante a leitura (`413` se excedido, `422` se vazio).
4. Valida extensão, MIME type declarado e assinatura/estrutura binária (`422` se inválido ou criptografado).
5. Verifica duplicidade por `(candidate_profile_id, sha256_hash)` (`409` se já existir no mesmo perfil).
6. Extrai e normaliza o texto do documento.
7. Move o arquivo temporário atomicamente (`os.replace`) para `storage/uploads/{profile_uuid}/{document_uuid}.{ext}` e grava o espelho UTF-8 em `storage/extracted/{profile_uuid}/{document_uuid}.txt`.
8. Persiste `ResumeDocument` e `ResumeExtraction` em transação única no PostgreSQL.
9. Em qualquer falha antes da conclusão, descarta o arquivo temporário e remove arquivos já gravados.

## 3. Validação dos formatos

- **PDF**: extensão `.pdf`, cabeçalho `%PDF-`, abertura válida via `pymupdf.open`, verificação `needs_pass` (rejeita criptografados com `422`) e mínimo de 1 página.
- **DOCX**: extensão `.docx`, assinatura ZIP (`PK\x03\x04` etc.), presença obrigatória de `[Content_Types].xml` e `word/document.xml`, verificação de path traversal nos nomes das entradas, limite de entradas (`max_resume_archive_entries`, padrão `2000`) e limite de tamanho descompactado (`max_resume_uncompressed_bytes`, padrão `50 MB`). Nenhum ZIP é extraído arbitrariamente para o disco.

## 4. Limites de tamanho

- `MAX_RESUME_UPLOAD_BYTES`: padrão `10485760` (10 MB), configurável em `backend/.env` ou variáveis de ambiente.
- A verificação ocorre por chunk de 1 MB durante o streaming, evitando carregar arquivos ilimitados em memória.
- `max_resume_text_characters`: padrão `2_000_000`; conteúdos acima do limite são truncados com o aviso `content_truncated`.

## 5. Armazenamento

Estrutura privada sob `STORAGE_ROOT` (fora de `frontend/` e ignorada pelo `.gitignore`):

```text
storage/
├── uploads/{profile_uuid}/{document_uuid}.{pdf|docx}
├── extracted/{profile_uuid}/{document_uuid}.txt
├── temporary/
├── resumes/
└── generated/
```

Somente chaves relativas (`storage_key` e `extracted_storage_key`) são gravadas no banco. Caminhos absolutos nunca são expostos nas respostas da API.

## 6. SHA-256 e deduplicação

- O hash SHA-256 (64 hexadecimais minúsculos) é calculado incrementalmente durante o staging.
- A unicidade é aplicada por perfil via consulta prévia e constraint `UNIQUE (candidate_profile_id, sha256_hash)` no PostgreSQL, garantindo proteção contra concorrência.
- O mesmo arquivo pode ser importado em perfis diferentes sem conflito, mantendo isolamento completo entre perfis.

## 7. Extração PDF

- Utiliza `import pymupdf` (API atual, sem uso de `fitz`).
- Extrai texto página a página preservando quebras de página com form feed (`\f`).
- Registra `page_count`, `word_count` e `character_count`.
- PDFs sem texto extraível (digitalizados) recebem o estado `completed_with_warnings` e o aviso `scanned_pdf_no_text`, sinalizando necessidade futura de OCR (não implementado nesta versão).

## 8. Extração DOCX

- Utiliza `python-docx` sem modificar o arquivo original.
- Extrai parágrafos, títulos, linhas de tabelas (células separadas por ` | `), cabeçalhos e rodapés.
- Documentos vazios recebem `completed_with_warnings` e o aviso `empty_extracted_content`.

## 9. Normalização

- Padroniza `\r\n` e `\r` para `\n`.
- Remove caracteres de controle inválidos preservando `\t`, `\n` e `\f`.
- Colapsa espaços inline repetidos e mais de duas quebras de linha consecutivas.
- Preserva acentos, caracteres Unicode e o conteúdo profissional original sem reescrita ou correção gramatical.

## 10. Estados de processamento

- `pending`: registro inicial ou metadado sem processamento.
- `processing`: em processamento.
- `parsed`: mantido por compatibilidade com registros legados do Profile Engine.
- `completed`: texto extraído sem avisos.
- `completed_with_warnings`: extração concluída com avisos (ex.: `scanned_pdf_no_text`, `empty_extracted_content`, `content_truncated`).
- `failed`: falha na extração (`failure_reason` registrado sem expor stack trace).

## 11. Persistência

- `resume_documents`: reutiliza a tabela existente, adicionando `failure_reason` (`VARCHAR(200)`) e ampliando `parsing_status` para `VARCHAR(32)` com os novos estados.
- `resume_extractions`: tabela 1:1 com `resume_documents` (`ON DELETE CASCADE`, `UNIQUE (resume_document_id)`), armazenando `extracted_text`, `page_count`, `word_count`, `character_count`, `parser_name`, `parser_version`, `warnings` (`JSONB`) e `extracted_storage_key`.
- Fatos profissionais (`educations`, `work_experiences`, `skills`, `certifications`, `languages`, `projects`) mantêm `source_document_id` com `ON DELETE SET NULL`.

## 12. Endpoints

Prefixo: `/api/v1/profiles/{profile_id}/resume-documents`

| Método | Caminho | Status | Descrição |
| --- | --- | --- | --- |
| `POST` | `/upload` | `201` | Upload, validação, armazenamento e extração de PDF/DOCX |
| `GET` | `/` | `200` | Lista metadados dos documentos (sem `extracted_text`) |
| `POST` | `/` | `201` | Registra metadados sem arquivo (compatibilidade Profile Engine) |
| `GET` | `/{document_id}` | `200` | Detalhes do documento e resumo da extração (sem `extracted_text`) |
| `GET` | `/{document_id}/extraction` | `200` | Retorna o texto extraído e estatísticas |
| `PATCH` | `/{document_id}` | `200` | Atualiza metadados |
| `DELETE` | `/{document_id}` | `204` | Remove registro, extração e arquivos físicos |

## 13. Tratamento de erros

| Situação | HTTP |
| --- | ---: |
| Upload realizado | `201` |
| Documento / extração encontrado | `200` |
| Exclusão concluída | `204` |
| Perfil, documento ou extração inexistente / outro perfil | `404` |
| Documento duplicado no mesmo perfil | `409` |
| Arquivo excede `MAX_RESUME_UPLOAD_BYTES` | `413` |
| Arquivo inválido, vazio, extensão/MIME incompatível ou criptografado | `422` |
| Falha interna de armazenamento ou extração | `500` |

## 14. Segurança

- Validação binária independente da extensão e MIME informados pelo cliente.
- Nomes físicos baseados em UUID; prevenção de path traversal em uploads, storage keys e entradas ZIP.
- Proteção contra ZIP bombs (contagem de entradas e tamanho descompactado).
- Isolamento estrito por `profile_id` em todas as consultas, extrações e exclusões.
- Nenhum conteúdo de currículo, dado pessoal ou caminho absoluto é registrado em logs ou exposto em erros.

## 15. Instruções de testes

```powershell
cd backend
uv sync
uv run alembic upgrade head
uv run pytest -v --cov=app --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

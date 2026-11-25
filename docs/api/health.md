# GET /health

Verifica se o processo da API está no ar. O endpoint não consulta banco, Redis ou provedores de IA.

## Resposta

`200 OK`

```json
{
  "status": "healthy",
  "application": "VagaNexo AI"
}
```

## Exemplo

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

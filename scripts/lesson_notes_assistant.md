# `lesson_notes_assistant.py`

Assistente de terminal para adicionar notas de aula à página GitHub Pages do portal.

Ele analisa uma pasta de aula ou uma pasta com várias aulas, identifica HTML, PDF, respostas `resp-*.pdf`, destino em `content/aulas/...`, disciplina correspondente no `config.yaml`, executa um `dry-run` obrigatório, publica quando você confirma, roda build, faz commit e pode fazer push para o GitHub.

## Relação com os scripts existentes

- `publish_lesson.py` é o motor de publicação: publica uma aula, copia HTML/assets, envia PDF ao Google Drive, atualiza `config.yaml`, roda build e tem opções de commit/push.
- `publish_lesson_full.py` é a conversa em lote: descobre várias aulas, mostra uma tabela, pergunta por respostas, força um `dry-run`, publica cada aula sem build individual, roda build uma vez e pergunta por commit/push.
- `lesson_notes_assistant.py` consolida os dois fluxos: usa o motor seguro de `publish_lesson.py`, herda a conversa em lote do `full`, melhora a inferência por `config.yaml` e fecha o fluxo com commit/push.

## Requisitos

- Python 3.
- Repositório do portal disponível localmente.
- Pasta de configuração do Google Drive usada por `publish_lesson.py`:
  - `/home/jefferson/Documentos/Gdrive/config/sync_config.json`
  - `/home/jefferson/Documentos/Gdrive/config/client_secret.json`
  - `/home/jefferson/Documentos/Gdrive/config/token.json`
- Pasta de aula já compilada com HTML e PDF principais.

## Uso recomendado

Analise uma pasta de disciplina com várias aulas:

```bash
./scripts/lesson_notes_assistant.py \
  "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas"
```

Analise uma única aula:

```bash
./scripts/lesson_notes_assistant.py \
  "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05"
```

O assistente vai:

1. mostrar o estado atual do Git e, se houver pendências, oferecer uma ação;
2. listar as aulas encontradas;
3. indicar se cada aula já existe no `config.yaml` e em `content/`;
4. sugerir publicar apenas aulas ausentes ou incompletas;
5. perguntar se deve incluir respostas;
6. executar `publish_lesson.py --dry-run`;
7. perguntar antes da publicação real;
8. rodar build;
9. mostrar `git status`;
10. perguntar por commit;
11. perguntar por push.

## Segurança

Por padrão, o assistente exige repositório limpo. Se o repositório já tiver alterações pendentes e você quiser apenas continuar a análise/publicação sem commit automático, use:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --allow-dirty
```

Se o repositório já estava sujo antes do assistente, ele oferece quatro caminhos:

- fazer um commit preparatório do estado atual e continuar;
- continuar sem commit/push automático no final;
- continuar e incluir as alterações antigas no commit final;
- parar para revisão manual.

Em uso não interativo, `--allow-dirty` continua disponível. Para incluir todo o estado atual no commit final, use também `--commit-existing-changes`.

## Simular sem alterar nada

Para analisar e parar depois do plano:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --plan-only
```

Para simular inclusive os comandos do assistente:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --dry-run
```

## Publicar com menos perguntas

Publicar após o dry-run, mantendo as confirmações interativas:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish
```

Publicar, aceitar as confirmações, commitar e fazer push:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --yes
```

Se já houver alterações pendentes e você quiser que o assistente faça um commit preparatório antes de publicar as notas:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --commit-current-state \
  --current-state-message "Atualiza portal antes das novas aulas"
```

Selecionar aulas específicas:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --select 1,3,4
```

Publicar todas:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --select todas \
  --publish
```

## Respostas

Incluir automaticamente o único `resp-*.pdf` encontrado em cada pasta:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --include-answers
```

Enviar respostas para uma pasta única no Drive:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --include-answers \
  --answers-drive-folder Respostas
```

Liberar o botão de respostas no portal:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --include-answers \
  --release-answers
```

Sem `--release-answers`, o YAML recebe `answers_released: false`.

## Build

Por padrão, cada publicação chama o build pelo `publish_lesson.py`.

Para publicar várias aulas e rodar um único build completo no fim:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --build-after
```

Para não rodar build:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --skip-build
```

## Commit e push

O fluxo padrão, com repositório limpo, pergunta antes de fazer commit e antes de fazer push.

Definir a mensagem de commit:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --message "Publica aulas de Termodinâmica"
```

Publicar e commitar, mas não fazer push:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --no-push
```

Publicar sem commit:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --publish \
  --no-commit
```

Se o repositório já tiver alterações pendentes e você quiser incluir tudo no commit final:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --allow-dirty \
  --commit-existing-changes \
  --publish
```

Fazer um commit separado do estado atual antes de iniciar a publicação:

```bash
./scripts/lesson_notes_assistant.py \
  "/caminho/para/aulas" \
  --commit-current-state
```

## Inferência de disciplina

O assistente primeiro lê o `config.yaml` e tenta associar o caminho da aula aos grupos já usados em `content/aulas/...`.

Também há atalhos embutidos para:

- `FM1` -> `Física Moderna 1` / `ES-FM1`
- `MecFlu` -> `Mecânica dos Fluidos` / `ES-MecFlu`
- `Termo1` -> `Termodinâmica` / `EM-Termo1`
- `Termo2` -> `Termodinâmica` / `EM-Termo2`
- `Ondas` -> `Ondulatória` / `EM-Ondas`

Se a disciplina não for inferida, o assistente para antes de publicar. Nesse caso, ajuste o nome da pasta, inclua uma entrada inicial em `config.yaml`, ou use `publish_lesson.py` diretamente com `--discipline-name`, `--content-group` e `--content-html`.

# `publish_lesson.py`

Script para publicar uma aula no portal, atualizar o link do PDF no `config.yaml`, gerar o site e opcionalmente fazer `commit` e `push`.

## O que ele faz

1. Encontra o HTML principal e o PDF principal da pasta da aula.
2. Copia o HTML para o caminho correspondente em `content/`.
3. Copia os assets locais referenciados no HTML, como imagens.
4. Envia ou atualiza o PDF no Google Drive.
5. Opcionalmente envia ou atualiza o PDF de respostas `resp-*.pdf` no mesmo diretório do Drive.
6. Atualiza o `config.yaml` com os novos links de PDF.
7. Executa `build.py`.
8. Opcionalmente faz `git commit` e `git push`.

## Requisitos

- Python 3
- Dependências do projeto instaladas
- A pasta de configuração do Drive em:
  - `/home/jefferson/Documentos/Gdrive/config/`
- Arquivos esperados nessa pasta:
  - `sync_config.json`
  - `client_secret.json`
  - `token.json`

## Fluxo esperado da aula

O script foi pensado para trabalhar em uma pasta de aula que já tenha sido compilada com `make.sh`, por exemplo:

```bash
/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05/
```

Ele procura automaticamente:

- um PDF principal
- um HTML principal

Arquivos de apoio como `resp-*`, `*-auto.html` e `*.backup.*` são ignorados na autodetecção.

Quando a aula ainda não existe no `config.yaml`, o script também cria a entrada nova de forma automática, desde que consiga inferir a disciplina pela pasta da aula. Para isso, ele usa:

- `FM1` -> `Física Moderna 1` / `ES-FM1`
- `MecFlu` -> `Mecânica dos Fluidos` / `ES-MecFlu`
- `EM/Termo1` -> `Termodinâmica` / `EM-Termo1`

Se quiser um nome mais descritivo para a aula nova, use `--lesson-name`.

## Uso básico

Publicar uma aula sem fazer commit nem push:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05"
```

Simular tudo sem alterar arquivos:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05" \
  --dry-run
```

Publicar e fazer commit:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05" \
  --commit
```

Publicar, commitar e dar push:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05" \
  --push
```

## Fluxo interativo em lote

Para publicar várias aulas seguindo uma conversa no terminal, use:

```bash
./scripts/publish_lesson_full.py
```

Ou informe a pasta da disciplina diretamente:

```bash
./scripts/publish_lesson_full.py \
  --base-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas"
```

O fluxo interativo:

1. lista as aulas encontradas;
2. mostra quais ainda não estão completas no `content/` ou no `config.yaml`;
3. faz `dry-run` obrigatório antes de alterar arquivos;
4. publica aula e, se você confirmar, cadastra respostas sem liberar automaticamente;
5. roda o build;
6. mostra `git status`;
7. pergunta antes de fazer commit;
8. pergunta antes de fazer push.

Por segurança, ele exige repositório limpo para commit/push automático. Com `--allow-dirty`, ele permite analisar/publicar, mas desativa commit/push automáticos.

## Opcoes principais

- `--lesson-dir`: pasta da aula
- `--html`: HTML principal, se a autodetecção não for suficiente
- `--pdf`: PDF principal, se houver mais de um PDF na pasta
- `--answers-pdf`: PDF de respostas/soluções, normalmente `resp-*.pdf`
- `--auto-answers`: publica automaticamente o único `resp-*.pdf` encontrado na pasta da aula
- `--answers-released`: libera o botão de respostas no portal; sem essa opção, grava `answers_released: false`
- `--answers-drive-folder`: pasta do Drive para PDFs de respostas, relativa ao `drive_folder_id` (ex.: `Respostas/FM1`)
- `--content-html`: caminho exato no `content/` para o HTML de destino; se ainda não existir no `config.yaml`, será usado na criação da entrada nova
- `--lesson-name`: nome da aula quando a entrada for nova
- `--discipline-name`: nome da disciplina quando a entrada for nova
- `--content-group`: subpasta em `content/aulas/` quando a entrada for nova
- `--skip-drive`: não envia PDF para o Drive; só deve ser usado para aulas que já existem no `config.yaml`
- `--skip-build`: não executa `build.py`
- `--build-mode full|incremental`: modo do build do site
- `--dry-run`: mostra o que faria sem alterar nada
- `--commit`: faz `git commit`
- `--push`: faz `git commit` e `git push`
- `--allow-dirty`: permite trabalhar com repositório já sujo

## Cuidados importantes

- O repositório já pode ter alterações pendentes. Por segurança, o script não faz commit automaticamente nesses casos sem `--allow-dirty`.
- Se a aula tiver mais de um HTML ou mais de um PDF principal, use `--html` e `--pdf`.
- Se a aula ainda não estiver no `config.yaml`, o script cria a entrada nova com o link do PDF enviado ao Drive.
- Para aula nova, `--skip-drive` é bloqueado: sem URL de PDF, a aula não entraria corretamente no `config.yaml`.
- O PDF precisa estar dentro do `local_folder` definido em `/home/jefferson/Documentos/Gdrive/config/sync_config.json`; caso contrário, o script interrompe para evitar envio na pasta errada do Drive.
- O PDF de respostas, quando usado, é gravado no YAML como `answers_pdf` e só aparece no portal quando `answers_released: true`.
- Sem `--answers-drive-folder`, o PDF de respostas precisa estar na mesma pasta local da aula principal e é enviado para a mesma pasta no Drive.
- Com `--answers-drive-folder`, o PDF de respostas é enviado para essa pasta única no Drive.
- O link do PDF é escrito no `config.yaml`, então esse arquivo passa a fazer parte do fluxo normal de publicação.

## Publicar respostas

Publicar a aula e o PDF de respostas ao mesmo tempo:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05" \
  --answers-pdf resp-fmi-aula-05.pdf \
  --answers-drive-folder Respostas
```

Esse comando cadastra o PDF, mas deixa `answers_released: false`.

Se houver exatamente um `resp-*.pdf` na pasta, você pode usar:

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/FM1/Aulas/Aula-05" \
  --auto-answers \
  --answers-released
```

## Exemplo real

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/MecFlu/Aulas/Aula-04" \
  --push \
  --allow-dirty
```

## Observacao

O script foi pensado para automação via terminal. Para esse fluxo, CLI é mais consistente do que GUI, porque reduz erro manual e deixa a publicação repetível.

# `publish_lesson.py`

Script para publicar uma aula no portal, atualizar o link do PDF no `config.yaml`, gerar o site e opcionalmente fazer `commit` e `push`.

## O que ele faz

1. Encontra o HTML principal e o PDF principal da pasta da aula.
2. Copia o HTML para o caminho correspondente em `content/`.
3. Copia os assets locais referenciados no HTML, como imagens.
4. Envia ou atualiza o PDF no Google Drive.
5. Atualiza o `config.yaml` com o novo link do PDF.
6. Executa `build.py`.
7. Opcionalmente faz `git commit` e `git push`.

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

## Opcoes principais

- `--lesson-dir`: pasta da aula
- `--html`: HTML principal, se a autodetecção não for suficiente
- `--pdf`: PDF principal, se houver mais de um PDF na pasta
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
- O link do PDF é escrito no `config.yaml`, então esse arquivo passa a fazer parte do fluxo normal de publicação.

## Exemplo real

```bash
./scripts/publish_lesson.py \
  --lesson-dir "/home/jefferson/Área de trabalho/IFSP/2026/MecFlu/Aulas/Aula-04" \
  --push \
  --allow-dirty
```

## Observacao

O script foi pensado para automação via terminal. Para esse fluxo, CLI é mais consistente do que GUI, porque reduz erro manual e deixa a publicação repetível.

# Publicar no GitHub quando SSH estiver bloqueado

Algumas redes publicas bloqueiam conexoes SSH, tanto na porta 22 quanto na
porta 443. Nessa situacao, o Git pode publicar pelo protocolo HTTPS.

O `lesson_notes_assistant.py` ja faz isso automaticamente: quando o `git push`
falha por rede na porta SSH 22, ele tenta SSH na porta 443 e, se essa tambem
estiver bloqueada, tenta HTTPS. Essa tentativa nao altera permanentemente o
remoto nem a configuracao do Git.

## Quando usar

Se o terminal mostrar mensagens como estas, a rede bloqueou SSH:

```text
ssh: connect to host github.com port 22: Network is unreachable
ssh: connect to host ssh.github.com port 443: Network is unreachable
```

O fallback HTTPS so funcionara se a rede permitir acesso normal ao GitHub pela
web. Se a rede nao permitir nenhum acesso externo, conecte-se a outra rede.

## Token para HTTPS

HTTPS nao usa a chave SSH. Para enviar alteracoes, o GitHub pede um *Personal
Access Token* (PAT) no lugar da senha da conta.

Um token existente pode ser reutilizado se ainda estiver valido, tiver acesso
ao repositorio `profjeffersonro.github.io` e permitir escrita. Uma chave SSH
existente nao substitui o token HTTPS.

Para criar um token novo:

1. No GitHub, abra **Settings** > **Developer settings** > **Personal access tokens** > **Fine-grained tokens**.
2. Clique em **Generate new token**.
3. Em **Resource owner**, selecione `profjeffersonro`.
4. Em **Repository access**, selecione somente o repositorio `profjeffersonro.github.io`.
5. Em **Repository permissions**, defina **Contents: Read and write**.
6. Escolha uma data de expiracao e clique em **Generate token**.
7. Copie o token imediatamente. O GitHub o exibe apenas uma vez.

Quando o Git solicitar credenciais durante o push HTTPS, informe:

```text
Username: seu usuario do GitHub
Password: o Personal Access Token
```

Nao use a senha da conta do GitHub e nao cole o token em comandos, scripts,
arquivos ou conversas. Um gerenciador de credenciais do Git pode guardar o
token para os proximos pushes.

## Enviar o commit pendente

Depois de conectar-se a uma rede com acesso ao GitHub, na pasta do repositorio,
execute:

```bash
git push
```

Se estiver usando `lesson_notes_assistant.py`, confirme a opcao de push ao fim
do processo. O assistente tentara HTTPS somente se as tentativas SSH forem
bloqueadas por rede.

## Referencias

- [GitHub Docs: Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [GitHub Docs: About authentication to GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)

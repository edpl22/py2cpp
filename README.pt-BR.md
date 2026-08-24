# py2cpp

*Leia isto em outros idiomas: [English](README.md).*

Este é um projeto "vibe-coded", motivado pela curiosidade sobre as
capacidades da IA.

Um transpilador que traduz um subconjunto bem definido de **Python 3.10+**
para **C++17** legível e compilável. O py2cpp é ele próprio escrito
inteiramente em Python; C++ é sempre apenas um formato de saída, além de um
pequeno runtime de compatibilidade somente-header (`pyrt`) vinculado ao
código gerado.

> **Status:** M0–M7 completos (o polimento da v0.1.0 foi concluído; ainda
> não publicado no PyPI — veja [Instalação](#instalação)). O py2cpp
> compila funções com `int`/`bool`/`str`/`list`/`dict`/`set`/`tuple`
> anotados, aritmética (incluindo `//` com verificação de overflow),
> comparações, `and`/`or`/`not`, variáveis locais, `if`/`elif`/`else`,
> `while`, `for ... in range(...)` e `for ... in <container>`,
> concatenação de strings, f-strings, literais de list/dict/set/tuple,
> indexação, list comprehensions, classes com herança simples e despacho
> virtual, e `try`/`except`/`raise` contra uma hierarquia de exceções
> curada — tudo para C++17 compilável e sem warnings, verificado em
> ubuntu/macos/windows × Python 3.10–3.13 no CI, e contra `g++`,
> `clang++` e o `cl` do MSVC. Mutação de containers (`.append(...)`,
> `d[k] = v`), `in`/`not in`, dict/set comprehensions, iteração/
> desempacotamento de tuplas, e subclasses de exceção definidas pelo
> usuário ainda não são suportados. Veja [Restrições](#restrições) e o
> roteiro abaixo para o que ainda falta.

## Por que não simplesmente usar Python?

Você não está escolhendo o py2cpp em vez do Python; você o escolhe para os
casos específicos em que precisa de um subconjunto pequeno e estaticamente
tipado de um programa Python compilado para um binário C++17 nativo. Não é
uma implementação Python de propósito geral.

## Não-objetivos

O py2cpp deliberadamente **não** tenta suportar:

- metaclasses, decoradores arbitrários, descritores ou mutação dinâmica de classes
- generators / `yield`, corrotinas, `async`/`await`
- `eval`, `exec`, ou outra execução dinâmica de código
- duck typing irrestrito, monkey patching, ou reflexão
- imports arbitrários/dinâmicos ou módulos de extensão de terceiros para CPython
- compatibilidade total com o modelo de objetos ou ABI do CPython

Programas que exigem essas construções são rejeitados com um diagnóstico,
não traduzidos incorretamente em silêncio. Veja
[`docs/architecture.md`](docs/architecture.md) (em inglês) para a
justificativa completa de design, e
[`docs/adding-python-feature.md`](docs/adding-python-feature.md) (em
inglês) se você quiser contribuir com uma nova funcionalidade.

## Instalação

O py2cpp ainda não foi publicado. Quando for lançado:

```bash
pip install py2cpp
```

## Configuração de desenvolvimento

```bash
git clone https://github.com/edpl22/py2cpp.git
cd py2cpp

python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Todas as dependências Python são instaladas apenas através do
`requirements.txt` — nunca com comandos `pip install <pacote>`
individuais.

Execute as verificações:

```bash
ruff check .
mypy --strict src tests
pytest
```

## Começando rapidamente

```bash
py2cpp examples/classify.py -o build/ --emit-runtime
g++ -std=c++17 build/classify.cpp -o build/classify
./build/classify
```

Para apenas as instruções de instalação e da CLI, sem todo o contexto do
projeto que está nesta página, veja [`USAGE.md`](USAGE.md) (em inglês).

Veja [`examples/`](examples/) para mais exemplos:
[`strings.py`](examples/strings.py), [`containers.py`](examples/containers.py),
[`classes.py`](examples/classes.py), e [`exceptions.py`](examples/exceptions.py)
— cada um focado em uma área do subconjunto suportado. Todo exemplo é
compilado com `g++ -Wall -Wextra` e sua saída é comparada com a do CPython
puro, como parte de manter este README honesto.

## Restrições

A regra central do py2cpp é que ele nunca "adivinha" quando a semântica do
Python não pode ser reproduzida com segurança em C++ — ele rejeita o
programa com um diagnóstico em vez disso. As restrições abaixo são limites
de escopo reais e deliberados, não descuidos; cada uma pode ser removida
em uma milestone futura. As mais notáveis:

- Ainda sem mutação de containers (`.append(...)`, `d[k] = v`,
  `.add(...)`) — containers são construídos via literais/comprehensions e
  lidos apenas via indexação/iteração.
- Sem `in`/`not in`.
- Apenas list comprehensions (sem dict/set comprehensions), uma única
  cláusula `for` e no máximo uma cláusula `if` em cada.
- Indexação de tuplas exige um literal inteiro em tempo de compilação;
  tuplas não podem ser iteradas nem desempacotadas.
- Sem pontos de `return` antecipados ou múltiplos — `return` só pode ser
  a última instrução de nível superior de uma função.
- Comparações encadeadas (`a < b < c`) são rejeitadas, não traduzidas
  incorretamente.
- Sem `Optional`/`None` para valores do tipo classe, então uma estrutura
  genuinamente terminada em nulo ou cíclica ainda não pode ser construída.
- Subclasses de exceção definidas pelo usuário não são suportadas; as
  exceções são comparadas contra uma hierarquia fixa e curada
  (`ValueError`/`TypeError`/`RuntimeError`/`LookupError` →
  `IndexError`/`KeyError`/`ArithmeticError` →
  `ZeroDivisionError`/`OverflowError`).
- `try` suporta cláusulas `except`, mas não `finally` nem `try`/`else`.
- Apenas herança simples; sem variáveis de classe, métodos
  estáticos/de classe, properties, ou dunders de sobrecarga de operadores.

Veja [`docs/architecture.md`](docs/architecture.md) (em inglês) para a
justificativa de design por trás dessas restrições, e abra uma issue
usando o template de solicitação de funcionalidade se alguma delas estiver
te bloqueando.

## Roteiro

| Milestone | Escopo |
|---|---|
| M0 | Estrutura inicial do repositório, esqueleto da CLI, CI — **concluído** |
| M1 | Pipeline mínimo de funções/aritmética: Python → AST → IR → C++ → compilado → executado — **concluído** |
| M2 | Fluxo de controle (`if`/`while`/`for`) e inferência estática de tipos — **concluído** |
| M3 | Strings e f-strings — **concluído** |
| M4 | Containers (`list`/`dict`/`set`/`tuple`) e comprehensions — **concluído** |
| M5 | Classes e herança simples — **concluído** |
| M6 | Exceções — **concluído** |
| M7 | Polimento da v0.1.0: documentação, exemplos, CI multi-compilador, empacotamento — **concluído** |

## Contribuindo

Issues e pull requests são bem-vindos. Por favor leia
[`docs/adding-python-feature.md`](docs/adding-python-feature.md) (em
inglês) antes de propor uma nova funcionalidade de linguagem, e observe as
[Restrições](#restrições) acima — muitas lacunas são decisões de escopo
deliberadas, não descuidos, então ajuda verificar se alguma já está sendo
acompanhada antes de abrir uma issue. Este projeto segue o
[Contributor Covenant](CODE_OF_CONDUCT.md) (em inglês).

## Licença

[MIT](LICENSE)

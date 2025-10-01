# 🛰️ Protocolo de Roteamento Dinâmico com Métrica Composta

Este projeto implementa um protocolo de roteamento dinâmico baseado em **estado de enlace (Link-State)** em Python, projetado para ser executado no emulador de redes **Mininet**.

O objetivo do protocolo é superar as métricas de roteamento simples (como contagem de saltos) utilizando uma **métrica composta** que leva em consideração a **largura de banda** e a **latência** dos enlaces. Isso permite que a rede tome decisões mais inteligentes, escolhendo não apenas o caminho mais curto, mas o caminho de maior qualidade para o fluxo de dados.

---

## ⚙️ Como Funciona

O protocolo é dividido em quatro componentes principais:

1. **Descoberta de Vizinhança**  
   Roteadores enviam pacotes `HELLO` (via UDP) para se descobrirem.

2. **Disseminação de Topologia**  
   As informações sobre os links e suas qualidades (banda, delay) são compartilhadas com toda a rede através de **Anúncios de Estado de Enlace (LSAs)**, montando um mapa completo da rede (LSDB) em cada roteador.

3. **Algoritmo de Roteamento**  
   Utilizando o mapa completo, o algoritmo de Dijkstra (`compute_cspf`) calcula a melhor rota para todos os destinos com base na métrica composta.

4. **Gerenciamento da Rota**  
   A melhor rota calculada é inserida na tabela de roteamento do **Kernel do Linux**, tornando a decisão efetiva para o tráfego de pacotes.

---

## 📂 Estrutura do Projeto

```
protocolo-roteamento-dinamico/
└── ospf_comparacao/
    ├── topologia_ospf.py            
    ├── roteador            
        ├── r1.conf
        ├── r2.conf
        └── r3.conf             
├── estado_enlace_rot.py    # O daemon do protocolo de roteamento
├── topologia.py            # Define a topologia da rede no Mininet
└── roteador/
    ├── r1.json             # Arquivos de configuração para cada
    ├── r2.json             # roteador, definindo vizinhos
    └── r3.json             # e redes locais.
```

---

## ⚡ Requisitos

- Linux com Mininet instalado  
- Python **3.8+**

---

## 🚀 Como Usar

### 1. Inicie a topologia no Mininet
O script `topologia.py` já está configurado para iniciar a rede e o daemon de roteamento (`estado_enlace_rot.py`) em cada roteador automaticamente.

```bash
sudo python3 topologia.py
```

Ao iniciar, você verá o log de criação da rede e, em seguida, o prompt do Mininet (`mininet>`). A rede já estará convergindo.

---

### 2. Verificando o Estado do Protocolo

#### A. Verificando os Logs (o que o protocolo está pensando)
Os arquivos `r1.log`, `r2.log` e `r3.log` são criados na mesma pasta onde você executou o comando `sudo`. Eles contêm informações valiosas sobre a troca de mensagens e a instalação de rotas.

```bash
# Em um novo terminal, fora do Mininet
cat r1.log
```

#### B. Verificando a Tabela de Roteamento (a decisão final)
No prompt do Mininet:

```bash
# Exibe a tabela de roteamento completa do roteador r1
r1 ip route

# Exibe a rota específica que r1 usaria para chegar em h3 (10.0.3.10)
r1 ip route get 10.0.3.10
```

---

## 🧪 Experimento: Influenciando a Rota com as Métricas

Vamos forçá-lo a mudar de uma rota boa para uma rota "pior" (com mais saltos), mas que se torna a melhor opção devido a uma **mudança na latência**.

### Passo 1: Entenda a métrica
No arquivo `estado_enlace_rot.py`, a decisão de qual caminho é melhor é baseada nesta fórmula:

```python
metric = cost + (delay / 100.0) + (1.0 / max(avail, 1))
```

Isso significa que o protocolo prefere links com **baixo delay** e **alta banda disponível**.

---

### Passo 2: Cenário base — A rota óbvia
1. Inicie a topologia normalmente: 
   ```bash
   sudo python3 topologia.py
   ```
2. Aguarde 10 segundos para a rede convergir. 
3. Verifique a rota de `h1` para `h3`: 
   ```bash
   r1 ip route get 10.0.3.10
   ```
   **Resultado esperado:** a rota será via `10.1.13.3 dev r1-eth2`, pois o link direto `r1 -> r3` é excelente (100 Mbps de banda, 1 ms de delay).

---

### Passo 3: Modifique a Métrica — A "Armadilha da Latência"
1. Saia do Mininet (`exit`). 
2. Abra o arquivo `topologia.py`. 
3. Localize a linha que define o link entre `r1` e `r3`:

```python
# Linha original
net.addLink(r1, r3, bw=100, delay='1ms')
```

4. Altere o delay de `1ms` para `100ms`:

```python
# Linha modificada
net.addLink(r1, r3, bw=100, delay='100ms')
```

5. Salve o arquivo.

---

### Passo 4: Verifique o novo comportamento
1. Inicie novamente a topologia modificada: 
   ```bash
   sudo python3 topologia.py
   ```
2. Aguarde 10 segundos. 
3. Verifique a rota de `h1` para `h3`: 
   ```bash
   r1 ip route get 10.0.3.10
   ```
   **Resultado esperado:** a rota agora será via `10.1.12.2 dev r1-eth1`.

---

### Autoras:
1. Gabriela Bley Rodrigues
2. Luisa Becker dos Santos
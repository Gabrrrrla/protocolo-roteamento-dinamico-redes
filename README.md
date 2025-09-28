# 🛰️ Protocolo de Roteamento Dinâmico com QoS

Este projeto implementa um **protocolo de roteamento dinâmico baseado em estado de enlace (Link-State)**, inspirado em OSPF, mas com **métrica composta** e **roteamento ciente de capacidade**.  

O objetivo é selecionar não apenas o **caminho mais curto**, mas sim o **melhor caminho viável** que satisfaça os requisitos de largura de banda e qualidade de serviço (QoS) de cada aplicação.

---

## Características

- **Link-State Routing**: cada roteador constrói um mapa completo da topologia.
- **Flooding de LSAs**: troca de mensagens com vizinhos para manter a LSDB.
- **Métrica composta**: combina largura de banda, atraso, confiabilidade e carga.
- **CSPF (Constrained Shortest Path First)**:
  1. **Viabilidade**: elimina caminhos que não atendem ao requisito de largura de banda.
  2. **Qualidade**: escolhe o melhor caminho restante com base na métrica composta.
- **Reservas de largura de banda**: cada fluxo aceito reduz a capacidade disponível nos enlaces.
- **API HTTP**: interface para consultar estado, solicitar rotas e liberar fluxos.

---

## 📂 Estrutura do Projeto

```
protocolo-roteamento-dinamico/
├── roteador.py
├── topologia.py
├── README.md 
└── tests.sh
```

---

## ⚙️ Requisitos

- Linux com [Mininet](http://mininet.org/) instalado
- Python 3.8+
- Dependências Python:
  ```bash
  pip3 install aiohttp networkx
  ```

---

## Como usar

### 1. Inicie a topologia no Mininet

```bash
sudo python3 topologia.py
```

A topologia de exemplo cria 3 roteadores (`r1`, `r2`, `r3`) e 2 hosts (`h1`, `h2`).

---

### 2. Inicie o daemon em cada roteador

No prompt do Mininet:

```bash
r1 python3 roteador.py --id R1 --ip 10.0.0.1 --http-port 8001 --neighbors 10.0.0.2,10.0.0.3 &
r2 python3 roteador.py --id R2 --ip 10.0.0.2 --http-port 8002 --neighbors 10.0.0.1,10.0.0.3 &
r3 python3 roteador.py --id R3 --ip 10.0.0.3 --http-port 8003 --neighbors 10.0.0.1,10.0.0.2 &
```

---

### 3. Consultar o estado

Ver a base de dados de estado de enlace (LSDB):

```bash
curl http://10.0.0.1:8001/lsdb
```

Ver status de reservas:

```bash
curl http://10.0.0.1:8001/status
```

---

### 4. Solicitar um caminho para um fluxo

Exemplo: requisitar rota de `10.0.0.1 → 10.0.0.3` para um fluxo de **5 Mbps**:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"src":"10.0.0.1","dst":"10.0.0.3","bw":5}' \
     http://10.0.0.1:8001/request_path
```

---

### 5. Gerar tráfego de teste

No Mininet:

```bash
h1 iperf3 -s &
h2 iperf3 -c 10.0.1.1 -b 5M
```

---

### 6. Simular falha de enlace

```bash
link r1 r3 down
```

O protocolo deve recalcular o caminho alternativo automaticamente.

---

## 🧪 Experimentos sugeridos

- **Admissão de fluxo**: tente requisitar mais banda do que disponível → deve ser rejeitado.
- **Qualidade vs Hops**: verificar se caminhos de maior largura de banda são preferidos.
- **Falhas**: derrubar links e medir tempo de convergência.
- **Overhead de controle**: monitorar LSAs com `tcpdump`.

---

## 👥 Autoras

- Luisa Becker dos Santos: Design e implementação do protocolo (algoritmos, LSAs, CSPF).
- Gabriela BLey Rodrigues: Integração no Mininet, testes, análise de métricas.

---

## 📜 Licença

Projeto acadêmico para a disciplina de **Redes de Computadores: Internetworking, Roteamento e Transmissão (Unisinos)**.

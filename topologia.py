from mininet.net import Mininet
from mininet.node import Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time # Importa a biblioteca time

def build():
    net = Mininet(link=TCLink)

    print(">>> Adicionando roteadores e hosts...")
    # roteadores
    r1 = net.addHost('r1', ip='10.0.1.1/24') # IP da interface r1-eth0
    r2 = net.addHost('r2', ip='10.0.2.1/24') # IP da interface r2-eth0
    r3 = net.addHost('r3', ip='10.0.3.1/24') # IP da interface r3-eth0
    
    # hosts de borda com seus IPs
    h1 = net.addHost('h1', ip='10.0.1.10/24')
    h2 = net.addHost('h2', ip='10.0.2.10/24')
    h3 = net.addHost('h3', ip='10.0.3.10/24')

    print(">>> Criando links entre os nós...")
    # links host <> roteador
    net.addLink(h1, r1)
    net.addLink(h2, r2)
    net.addLink(h3, r3)

    net.addLink(r1, r2, bw=50, delay='5ms')   # r1-r2 50Mbps
    net.addLink(r2, r3, bw=10, delay='20ms')  # r2-r3 10Mbps (gargalo)
    net.addLink(r1, r3, bw=100, delay='1ms')  # r1-r3 100Mbps

    print(">>> Iniciando a rede Mininet...")
    net.start()

    print(">>> Habilitando encaminhamento IP nos roteadores...")
    for r in (r1, r2, r3):
        r.cmd('sysctl -w net.ipv4.ip_forward=1')

    print(">>> Configurando endereços IP nas interfaces...")
    # IPs das interfaces dos roteadores viradas para os hosts
    r1.cmd('ifconfig r1-eth0 10.0.1.1/24')   # para h1
    r2.cmd('ifconfig r2-eth0 10.0.2.1/24')   # para h2
    r3.cmd('ifconfig r3-eth0 10.0.3.1/24')   # para h3

    # IPs das interfaces entre os roteadores
    r1.cmd('ifconfig r1-eth1 10.1.12.1/24')  # para r2
    r2.cmd('ifconfig r2-eth1 10.1.12.2/24')  # de r1
    
    r2.cmd('ifconfig r2-eth2 10.1.23.2/24')  # para r3
    r3.cmd('ifconfig r3-eth1 10.1.23.3/24')  # de r2
    
    r1.cmd('ifconfig r1-eth2 10.1.13.1/24')  # para r3
    r3.cmd('ifconfig r3-eth2 10.1.13.3/24')  # de r1

    print(">>> Configurando rotas padrão nos hosts...")
    # rotas padrão para os hosts apontarem para seus roteadores
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.2.1')
    h3.cmd('ip route add default via 10.0.3.1')

    print(">>> Configuração de rede base concluída. Aguardando 1 segundo...")
    time.sleep(1)

    # só dps da rede estar configurada, iniciamos os daemons
    print(">>> Iniciando daemons de roteamento dinâmico...")
    
    # caminhos para os arquivos de configuração
    r1_config = "./roteador/r1.json"
    r2_config = "./roteador/r2.json"
    r3_config = "./roteador/r3.json"

    r1.popen(f"python3 estado_enlace_rot.py --config {r1_config} > r1.log 2>&1 &", shell=True)
    r2.popen(f"python3 estado_enlace_rot.py --config {r2_config} > r2.log 2>&1 &", shell=True)
    r3.popen(f"python3 estado_enlace_rot.py --config {r3_config} > r3.log 2>&1 &", shell=True)

    print(">>> Topologia pronta. Iniciando CLI.")
    CLI(net)

    print(">>> Parando a rede...")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    build()
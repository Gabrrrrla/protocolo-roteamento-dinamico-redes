from mininet.net import Mininet
from mininet.node import Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time 

def build():
    net = Mininet(link=TCLink)

    print(">>> Adicionando roteadores e hosts...")
    # roteadores
    r1 = net.addHost('r1', ip='10.0.1.1/24')
    r2 = net.addHost('r2', ip='10.0.2.1/24')
    r3 = net.addHost('r3', ip='10.0.3.1/24')
    
    # hosts de borda
    h1 = net.addHost('h1', ip='10.0.1.10/24')
    h2 = net.addHost('h2', ip='10.0.2.10/24')
    h3 = net.addHost('h3', ip='10.0.3.10/24')

    print(">>> Criando links entre os nós...")
    # hosts <> roteadores
    net.addLink(h1, r1)
    net.addLink(h2, r2)
    net.addLink(h3, r3)

    # links roteador <> roteador
    net.addLink(r1, r2, bw=50, delay='5ms',
                intfName1='r1-eth1', params1={'ip': '10.1.12.1/24'},
                intfName2='r2-eth1', params2={'ip': '10.1.12.2/24'})
    
    net.addLink(r2, r3, bw=10, delay='20ms',
                intfName1='r2-eth2', params1={'ip': '10.1.23.2/24'},
                intfName2='r3-eth1', params2={'ip': '10.1.23.3/24'})
    
    net.addLink(r1, r3, bw=100, delay='100ms',
                intfName1='r1-eth2', params1={'ip': '10.1.13.1/24'},
                intfName2='r3-eth2', params2={'ip': '10.1.13.3/24'})

    print(">>> Iniciando a rede Mininet...")
    net.start()
    time.sleep(1)

    print(">>> Habilitando encaminhamento IP nos roteadores...")
    for r in (r1, r2, r3):
        r.cmd('sysctl -w net.ipv4.ip_forward=1')

    print(">>> Configurando rotas padrão nos hosts...")
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.2.1')
    h3.cmd('ip route add default via 10.0.3.1')

    print(">>> Configuração de rede base concluída. Aguardando 1 segundo...")
    time.sleep(1)

    # só depois da rede estar configurada, iniciamos os daemons
    print(">>> Iniciando daemons de roteamento dinâmico...")
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

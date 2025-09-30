from mininet.net import Mininet
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time
import os

def build():
    net = Mininet(link=TCLink)

    print(">>> Adicionando roteadores e hosts...")
    r1 = net.addHost('r1', ip='10.0.1.1/24')
    r2 = net.addHost('r2', ip='10.0.2.1/24')
    r3 = net.addHost('r3', ip='10.0.3.1/24')

    h1 = net.addHost('h1', ip='10.0.1.10/24')
    h2 = net.addHost('h2', ip='10.0.2.10/24')
    h3 = net.addHost('h3', ip='10.0.3.10/24')

    print(">>> Criando links entre os nós...")
    net.addLink(h1, r1)
    net.addLink(h2, r2)
    net.addLink(h3, r3)

    # cenário A: 
    net.addLink(r1, r2, bw=50, delay='20ms') # aumentei um pouco o delay para o Cenário B ficar mais claro
    net.addLink(r2, r3, bw=10, delay='20ms')
    net.addLink(r1, r3, bw=100, delay='1ms')

    print(">>> Iniciando a rede Mininet...")
    net.start()

    print(">>> Habilitando encaminhamento IP nos roteadores...")
    for r in (r1, r2, r3):
        r.cmd('sysctl -w net.ipv4.ip_forward=1')

    print(">>> Configurando endereços IP nas interfaces restantes...")
    r1.cmd('ifconfig r1-eth1 10.1.12.1/24')
    r2.cmd('ifconfig r2-eth1 10.1.12.2/24')
    r2.cmd('ifconfig r2-eth2 10.1.23.2/24')
    r3.cmd('ifconfig r3-eth1 10.1.23.3/24')
    r1.cmd('ifconfig r1-eth2 10.1.13.1/24')
    r3.cmd('ifconfig r3-eth2 10.1.13.3/24')

    print(">>> Configurando rotas padrão nos hosts...")
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.2.1')
    h3.cmd('ip route add default via 10.0.3.1')

    print(">>> Iniciando daemons FRR nos roteadores...")
    config_path = os.getcwd()

    for r_name in ['r1', 'r2', 'r3']:
        r = net.get(r_name)
        # -d: modo daemon, -f: arquivo de config, -z: socket do zebra, -i: arquivo de PID
        r.cmd(f'/usr/lib/frr/zebra -d -f {config_path}/{r_name}.conf -z /tmp/{r_name}.zebra.sock -i /tmp/{r_name}.zebra.pid')
        time.sleep(1) # Dê tempo para o zebra iniciar
        r.cmd(f'/usr/lib/frr/ospfd -d -f {config_path}/{r_name}.conf -z /tmp/{r_name}.zebra.sock -i /tmp/{r_name}.ospfd.pid')

    print(">>> Topologia pronta com OSPF. Aguardar ~15s pra convergência.")
    CLI(net)

    print(">>> Parando a rede...")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    build()
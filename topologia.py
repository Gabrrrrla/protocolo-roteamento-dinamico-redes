from mininet.net import Mininet
from mininet.node import Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time # Importa a biblioteca time


def build():
   net = Mininet(link=TCLink)


   print(">>> Adicionando roteadores e hosts...")
   r1 = net.addHost('r1', ip='10.0.1.1/24') # interface r1-eth0
   r2 = net.addHost('r2', ip='10.0.2.1/24') # interface r2-eth0
   r3 = net.addHost('r3', ip='10.0.3.1/24') # interface r3-eth0
  
   # hosts de borda e seus IPs
   h1 = net.addHost('h1', ip='10.0.1.10/24')
   h2 = net.addHost('h2', ip='10.0.2.10/24')
   h3 = net.addHost('h3', ip='10.0.3.10/24')


   print(">>> Criando links entre os nós...")
   net.addLink(h1, r1)
   net.addLink(h2, r2)
   net.addLink(h3, r3)


   net.addLink(r1, r2, bw=50, delay='5ms')   # r1-r2 50Mbps
   net.addLink(r2, r3, bw=10, delay='20ms')  # r2-r3 10Mbps (aqui vai ter um gargalo)
   net.addLink(r1, r3, bw=100, delay='1ms')  # r1-r3 100Mbps




   print(">>> Iniciando a rede Mininet...")
   net.start()


   print(">>> Habilitando encaminhamento IP nos roteadores...")
   for r in (r1, r2, r3):
       r.cmd('sysctl -w net.ipv4.ip_forward=1')


   print(">>> Configurando endereços IP nas interfaces...")
   r1.cmd('ifconfig r1-eth0 10.0.1.1/24')   # para h1
   r2.cmd('ifconfig r2-eth0 10.0.2.1/24')   # para h2
   r3.cmd('ifconfig r3-eth0 10.0.3.1/24')   # para h3


   r1.cmd('ifconfig r1-eth1 10.1.12.1/24')  # para r2
   r2.cmd('ifconfig r2-eth1 10.1.12.2/24')  # de r1
  
   r2.cmd('ifconfig r2-eth2 10.1.23.2/24')  # para r3

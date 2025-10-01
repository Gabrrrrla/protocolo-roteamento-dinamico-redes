#!/usr/bin/env python3
import argparse
import json
import socket
import threading
import time
import heapq
import subprocess
import ipaddress
import traceback
from pprint import pprint

HELLO_INTERVAL = 2.0
LSA_FLOOD_PORT = 50000
BUFFER_SIZE = 65535
NEIGHBOR_DEAD_INTERVAL = HELLO_INTERVAL * 4

def load_config(path):
    with open(path) as f:
        return json.load(f)

class RouterDaemon:
    def __init__(self, cfg):
        self.neighbors_last_seen = {}
        self.cfg = cfg
        self.id = cfg['router_id']
        self.local_ip = cfg.get('local_ip', None)
        self.port = cfg.get('port', LSA_FLOOD_PORT)

        # LSDB: dict key -> link_id, value -> {...}
        self.lsdb = {}
        self.lsdb_lock = threading.Lock()

        # reservations: (link_id -> reserved_bw)
        self.reservations = {}

        # seen LSAs to avoid reprocessing (origin, seq)
        self.seen_lsas = set()

        # UDP socket bound to port on all interfaces
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.port))

        # quick map: neighbor id -> neighbor dict from config
        self.neigh_by_id = { n['id']: n for n in self.cfg.get('neighbors', []) }

        # ensure attached_networks exists
        self.attached_networks = list(self.cfg.get('attached_networks', []))

    # --------------------- start / background tasks ---------------------
    def start(self):
        threading.Thread(target=self.recv_loop, daemon=True).start()
        threading.Thread(target=self.hello_loop, daemon=True).start()
        threading.Thread(target=self.check_neighbors_loop, daemon=True).start()

        # mandando o advertise imediatamente pra que os vizinhos se conheçam
        time.sleep(0.5)
        self.advertise_links()

        # esperar um pouco pro lsa se proparar e entao tentar instalar as rotas nas redes conhecidas
        threading.Thread(target=self.bootstrap_install_routes, daemon=True).start()

        print(f"[{self.id}] Daemon started (port={self.port})")

    # manda REQUEST/INSTALL dps de um tempo 
    def bootstrap_install_routes(self):
        time.sleep(2.0)   # tempo pro hello
        self.advertise_links()
        time.sleep(1.0)

        # pega as redes da lsdb + proprias redes adjacentes
        networks = set(self.attached_networks)
        with self.lsdb_lock:
            for lid, link in list(self.lsdb.items()):
                if 'network' in link:
                    networks.add(link['network'])

        # pra cada, pega um ip de host e tenta instalar a rota
        for net in networks:
            try:
                # pula a si proprio
                if net in self.attached_networks:
                    continue
                netobj = ipaddress.ip_network(net)
                try:
                    candidate = str(list(netobj.hosts())[0])
                except Exception:
                    candidate = str(netobj.network_address + 1)
                # computa o caminho
                path = self.compute_cspf(candidate, bw_required=0)
                if path:
                    print(f"[{self.id}] bootstrap installing route to network of {candidate} via path {path}")
                    self.install_path(path, candidate, bw=0)
                else:
                    print(f"[{self.id}] bootstrap: no path to network {net}")
            except Exception as e:
                print(f"[{self.id}] bootstrap error for net {net}: {e}")
                traceback.print_exc()

    # --------------------- networking I/O ---------------------
    def recv_loop(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                try:
                    msg = json.loads(data.decode())
                except Exception as e:
                    print(f"[{self.id}] bad msg decode from {addr}: {e}")
                    continue
                try:
                    self.handle_msg(msg, addr)
                except Exception as e:
                    print(f"[{self.id}] handle_msg exception: {e}")
                    traceback.print_exc()
            except Exception as e:
                print(f"[{self.id}] recv_loop exception: {e}")
                traceback.print_exc()
                time.sleep(0.5)

    def send_msg(self, msg, dest_ip, dest_port=None):
        if dest_port is None:
            dest_port = self.port
        try:
            self.sock.sendto(json.dumps(msg).encode(), (dest_ip, dest_port))
        except Exception as e:
            print(f"[{self.id}] send_msg err to {dest_ip}:{dest_port} - {e}")

    def hello_loop(self):
        while True:
            for n in self.cfg.get('neighbors', []):
                msg = {"type":"HELLO", "from":self.id}
                try:
                    self.send_msg(msg, n['ip'], n.get('port', self.port))
                except Exception as e:
                    print(f"[{self.id}] hello send err to {n.get('ip')}: {e}")
            time.sleep(HELLO_INTERVAL)

    # --------------------- LSA flood / advertise ---------------------
    def flood_lsa(self, lsa, exclude_ip=None):
        # inunda lsa pra todos os vizinhos 
        for n in self.cfg.get('neighbors', []):
            if exclude_ip and n.get('ip') == exclude_ip:
                continue
            try:
                # usa send_msg p/ centralizar tratamento de erros/porta
                self.send_msg(lsa, n.get('ip'), n.get('port', self.port))
            except Exception as e:
                print(f"[{self.id}] flood err to {n.get('ip')}: {e}")

    def advertise_links(self):
        # cria o lsa com links locais e as attached networks
        lsa = {
            "type":"LSA_LINK",
            "origin":self.id,
            "seq": int(time.time()),
            "links":[]
        }
        for n_config in self.cfg.get('neighbors', []):
            neighbor_id = n_config['id']
            # Só anuncia se o vizinho foi visto recentemente (está "vivo")
            if neighbor_id in self.neighbors_last_seen:
                local_iface_ip = n_config.get('local_ip', self.local_ip)
                remote_iface_ip = n_config['ip']
                link = {
                    "id": f"{self.id}-{neighbor_id}",
                    "a": self.id,
                    "b": neighbor_id,
                    "capacity": n_config.get('capacity', 100),
                    "delay": n_config.get('delay_ms', 1),
                    "cost": n_config.get('cost', 1),
                    "ip_a": local_iface_ip,
                    "ip_b": remote_iface_ip
                }
                lsa['links'].append(link)
        for net in self.attached_networks:
            lsa['links'].append({
                "id": f"{self.id}-net-{net}",
                "a": self.id,
                "b": "NET",
                "network": net
            })
        # manda pros vizinhos
        print(f"[{self.id}] advertising LSA (links={len(lsa['links'])})")
        self.flood_lsa(lsa)

    # --------------------- message handling ---------------------
    def handle_msg(self, msg, addr):
        mtype = msg.get('type')

        if mtype == 'HELLO':
            origin_id = msg.get('from')
            if origin_id:
                self.neighbors_last_seen[origin_id] = time.time()
            # reply ACK and advertise
            reply = {"type":"HELLO_ACK", "from":self.id}
            # envia ACK para quem mandou o HELLO
            self.send_msg(reply, addr[0], addr[1])
            # advertise on HELLO to allow faster discovery
            self.advertise_links()
            return

        if mtype == 'HELLO_ACK':
            # ignore for now
            return

        if mtype == 'LSA_LINK':
            origin = msg.get('origin')
            seq = msg.get('seq', 0)
            key = (origin, seq)
            if key in self.seen_lsas:
                return
            # marca como visto antes de processar para evitar loops em caso de reentrância
            self.seen_lsas.add(key)
            lsdb_changed = False
            try:
                # update LSDB
                with self.lsdb_lock:
                    for link in msg.get('links', []):
                        lid = link.get('id')
                        # se não existir ou for diferente, atualiza e marca mudança
                        if lid not in self.lsdb or self.lsdb[lid] != link:
                            self.lsdb[lid] = link
                            lsdb_changed = True

                    print(f"--- LSDB atualizado em {self.id} ---")
                    pprint(self.lsdb)
            except Exception as e:
                print(f"[{self.id}] erro ao atualizar LSDB: {e}")
                traceback.print_exc()

            # re-flood to others (except where it veio)
            try:
                self.flood_lsa(msg, exclude_ip=addr[0])
            except Exception as e:
                print(f"[{self.id}] flood after LSA err: {e}")

            if lsdb_changed:
                print(f"[{self.id}] LSDB mudou. Reavaliando todas as rotas para garantir otimalidade.")
                threading.Thread(target=self.bootstrap_install_routes, daemon=True).start()
            return
        

        if mtype == 'REQUEST_ROUTE':
            dest = msg.get('dest')
            bw = msg.get('bw', 0)
            # requester may be addr[0]; we ignore requester origin and install locally + inform others
            path = self.compute_cspf(dest, bw)
            if path:
                self.install_path(path, dest, bw)
                # reply to requester (optional)
                resp = {"type":"REQUEST_REPLY", "path": path}
                # if requester ip present, send back
                try:
                    self.send_msg(resp, addr[0])
                except Exception:
                    pass
            else:
                resp = {"type":"REQUEST_REPLY", "path": None}
                try:
                    self.send_msg(resp, addr[0])
                except Exception:
                    pass
            return

        if mtype == 'INSTALL_ROUTE':
            dest_network = msg.get('dest')
            next_hop = msg.get('next')
            print(f"[{self.id}] INSTALL_ROUTE received: install {dest_network} via {next_hop}")
            self.install_kernel_route(dest_network, next_hop)
            return

        print(f"[{self.id}] unknown msg type: {mtype} from {addr}")

    # --------------------- CSPF / path computation ---------------------
    def compute_cspf(self, dest_ip, bw_required):
        # acha o destino procurando na lsdb das attached networks
        dest_router = None
        with self.lsdb_lock:
            for lid, link in self.lsdb.items():
                if link.get('b') == 'NET' and 'network' in link:
                    try:
                        net = ipaddress.ip_network(link['network'])
                        if ipaddress.ip_address(dest_ip) in net:
                            dest_router = link['a'] 
                            break
                    except Exception:
                        continue
            # verifica se nao esta talvez nas attached
            if not dest_router:
                for net in self.attached_networks:
                    try:
                        if ipaddress.ip_address(dest_ip) in ipaddress.ip_network(net):
                            dest_router = self.id
                            break
                    except Exception:
                        pass

        if not dest_router:
            # print(f"[{self.id}] destination router not found in LSDB for {dest_ip}")
            return None

        # Build adjacency with weights and include per-link IPs for constructing next-hop IPs
        graph = {}
        with self.lsdb_lock:
            for lid, link in self.lsdb.items():
                # skip attached network entries
                if link.get('b') == 'NET' or 'network' in link:
                    continue
                a = link.get('a'); b = link.get('b')
                cap = link.get('capacity', 100)
                reserved = self.reservations.get(lid, 0)
                avail = cap - reserved
                if avail < bw_required:
                    continue
                cost = link.get('cost', 1)
                delay = link.get('delay', 1)
                metric = cost + (delay / 100.0) + (1.0 / max(avail, 1))
                ip_a = link.get('ip_a')
                ip_b = link.get('ip_b') 
                # store edges carrying also the interface IP to use as next-hop
                graph.setdefault(a, []).append((b, metric, lid, ip_b))  # to reach b, next hop ip is ip_b
                graph.setdefault(b, []).append((a, metric, lid, ip_a))  # to reach a, next hop ip is ip_a

        # aplica o Dijkstra a partir do roteador atual 
        dist = {self.id: 0}
        prev = {}
        heap = [(0, self.id)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == dest_router:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w, lid, next_ip in graph.get(u, []):
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = (u, lid, next_ip)  # from v go back to u via lid; next_ip is v-side IP on that link
                    heapq.heappush(heap, (nd, v))

        if dest_router not in prev and dest_router != self.id:
            return None

        # Reconstruct path: produce list of tuples (router_id, link_id_to_prev, iface_ip_of_router_towards_prev)
        path = []
        cur = dest_router
        while cur != self.id:
            p = prev[cur]
            # p = (previous_router, link_id, ip_of_cur_on_link)
            path.append((cur, p[1], p[2]))
            cur = p[0]
        # append start router entry: determine interface IP of self towards next hop if possible
        if path:
            # path[-1] is first hop router after self
            first_hop = path[-1]
            # find in lsdb the link between self.id and first_hop[0] to obtain our local interface IP
            our_iface_ip = self.local_ip
            with self.lsdb_lock:
                for lid, link in self.lsdb.items():
                    if link.get('a') == self.id and link.get('b') == first_hop[0]:
                        our_iface_ip = link.get('ip_a', our_iface_ip)
                        break
                    if link.get('b') == self.id and link.get('a') == first_hop[0]:
                        our_iface_ip = link.get('ip_b', our_iface_ip)
                        break
            path.append((self.id, None, our_iface_ip))
        else:
            # destination is local
            path.append((self.id, None, self.local_ip))

        path.reverse()
        return path

    # --------------------- install path / kernel routes ---------------------
    def install_path(self, path, dest_ip, bw):
        # reserva largura de banda nas arestas do caminho
        for i in range(len(path)-1):
            cur = path[i]
            nxt = path[i+1]
            lid = None
            lid1 = f"{cur[0]}-{nxt[0]}"
            lid2 = f"{nxt[0]}-{cur[0]}"
            with self.lsdb_lock:
                if lid1 in self.lsdb:
                    lid = lid1
                elif lid2 in self.lsdb:
                    lid = lid2
                else:
                    lid = nxt[1]
            if lid:
                self.reservations[lid] = self.reservations.get(lid, 0) + bw

        for i in range(len(path)-1):
            this_router_id = path[i][0]
            next_hop_ip = path[i+1][2]

            # converte o IP de destino para o endereço da rede (ex: 10.0.3.10 -> 10.0.3.0/24)
            try:
                # tenta inferir máscara se dest_ip já for uma rede
                if '/' in str(dest_ip):
                    dest_net = ipaddress.ip_network(dest_ip, strict=False)
                else:
                    # fallback: assume /24
                    dest_net = ipaddress.ip_interface(f"{dest_ip}/24").network
            except Exception:
                dest_net = ipaddress.ip_interface(f"{dest_ip}/24").network

            if this_router_id == self.id:
                print(f"[{self.id}] install local route to {dest_net} -> via {next_hop_ip}")
                self.install_kernel_route(str(dest_net), next_hop_ip) # Envia a rede
            else:
                # manda um INSTALL_ROUTE pro roteador
                target_ip = None
                # olha nas config dos neighbors pelo id
                n = self.neigh_by_id.get(this_router_id)
                if n:
                    target_ip = n.get('ip')
                if not target_ip:
                    # fallback: procura lsdb por um link onde a==roteador_id e b==self.id (or inverse)
                    with self.lsdb_lock:
                        for lid, link in self.lsdb.items():
                            if link.get('a') == this_router_id and link.get('b') == self.id:
                                target_ip = link.get('ip_a')
                                break
                            if link.get('b') == this_router_id and link.get('a') == self.id:
                                target_ip = link.get('ip_b')
                                break
                if target_ip:
                    msg = {"type":"INSTALL_ROUTE", "dest": str(dest_net), "next": next_hop_ip}
                    print(f"[{self.id}] sending INSTALL_ROUTE to {this_router_id} ({target_ip}) instructing install {dest_net} via {next_hop_ip}")
                    self.send_msg(msg, target_ip)
                else:
                    print(f"[{self.id}] cannot find reachable IP to instruct router {this_router_id} to install route for {dest_ip}")

    def install_kernel_route(self, dest_network, next_hop):
        # instala a rota para a rede inteira
        try:
            proc = subprocess.run(["ip","route","replace", dest_network, "via", next_hop], capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"[{self.id}] ip route command failed: {proc.returncode} stdout={proc.stdout} stderr={proc.stderr}")
            else:
                print(f"[{self.id}] route installed: {dest_network} via {next_hop}")
        except Exception as e:
            print(f"[{self.id}] route install exception for {dest_network} via {next_hop}: {e}")
            traceback.print_exc()

    def check_neighbors_loop(self):
        while True:
            now = time.time()
            dead_neighbors = []
            for neighbor_id, last_seen_time in list(self.neighbors_last_seen.items()):
                if now - last_seen_time > NEIGHBOR_DEAD_INTERVAL:
                    print(f"[{self.id}] Vizinho {neighbor_id} considerado MORTO! (Timeout)")
                    dead_neighbors.append(neighbor_id)

            if dead_neighbors:
                # Chame uma função para limpar os links desse vizinho
                self.handle_dead_neighbors(dead_neighbors)

            time.sleep(HELLO_INTERVAL)

    def handle_dead_neighbors(self, dead_neighbors):
        links_to_remove = []
        # 1. Encontrar todos os links que envolvem o(s) vizinho(s) morto(s)
        with self.lsdb_lock:
            for link_id, link_data in list(self.lsdb.items()):
                # Um link é considerado morto se uma de suas pontas for um dos vizinhos caídos
                if link_data.get('a') in dead_neighbors or link_data.get('b') in dead_neighbors:
                    links_to_remove.append(link_id)

            # 2. Remover os links mortos da base de dados local (LSDB) e limpar reservas
            for link_id in links_to_remove:
                if link_id in self.lsdb:
                    print(f"[{self.id}] Removendo link morto {link_id} do LSDB.")
                    del self.lsdb[link_id]
                # também remover qualquer reserva associada
                if link_id in self.reservations:
                    print(f"[{self.id}] Limpando reserva associada ao link {link_id}.")
                    del self.reservations[link_id]

        # 3. Se alguma mudança foi feita no LSDB, reagir à mudança de topologia
        if links_to_remove:
            # Primeiro, removemos oficialmente o vizinho da nossa lista de vizinhos "vivos"
            for neighbor_id in dead_neighbors:
                if neighbor_id in self.neighbors_last_seen:
                    del self.neighbors_last_seen[neighbor_id]

            # Anuncia para a rede nosso novo estado de links (agora sem os links para o vizinho caído)
            self.advertise_links()

            # Recalcula e reinstala todas as nossas rotas com base no novo mapa da rede
            print(f"[{self.id}] Recalculando todas as rotas devido à queda de vizinho...")
            threading.Thread(target=self.bootstrap_install_routes, daemon=True).start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    # cfg precisa ter um local_ip, e se nao tiver pega um default do primeiro mapeamento vizinho
    if 'local_ip' not in cfg or not cfg.get('local_ip'):
        # tentar setar baseado no local_ip dos neighbors
        if cfg.get('neighbors'):
            sample = cfg['neighbors'][0].get('local_ip')
            if sample:
                cfg['local_ip'] = sample
    d = RouterDaemon(cfg)
    d.start()
    while True:
        time.sleep(1)
